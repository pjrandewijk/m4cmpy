# m4cmpy - standalone figures from M4 Circuit Macros files
# Copyright (C) 2026 Peter Jan Randewijk
# SPDX-License-Identifier: GPL-3.0-or-later
"""Python scripting facade for Circuit Macros.

Build a circuit in Python and get readable Circuit Macros (.m4cm) source, which the
``m4cm`` command turns into PDF, PNG, JPG, SVG or EPS::

    import m4cmpy.cm as cm

    with cm.Drawing() as d:                  # lengths in mm by default
        O = d.point("O", (0, 0))
        vs = d.source("sinusoid", up=12.5, start=O, label=r"\\mathbf{V}_s")
        d.inductor(right=25, label="jX_s")
        d.ebox(down_to=O, label=r"\\mathbf{Z}_l")
        d.line(end=O)
        d.dot()
        d.ground()
    d.render(pdf=True, png=True)             # writes figure.m4cm, figure.pdf, ...

or in the pyplot style, on an implicit current drawing::

    cm.source("voltage", up=12.5)
    cm.resistor(right=25, label="R_1")
    cm.save("fig.m4cm")

Element methods carry the Circuit Macros macro names and arguments (``source(type,
diameter, R, attributes, name)``); readable aliases such as ``"voltage"`` translate to
the macro codes (``V``), and any macro without a method is reached through
:meth:`Drawing.element`. Elements are placed

* by a relative direction: ``up=12.5``, ``right=True`` (default length ``elen_``),
  ``dir="up", length=12.5`` or ``dir=30`` (degrees),
* by coordinates or terminals: ``start=(0, 0), end=(0, 12.5)``, ``start=v1.end``,
* by a direction until a level: ``down_to=O`` (down to the height of O).

Without placement an element continues from the end of the previous one in the
current direction, as in Circuit Macros. Terminals of an element are positions:
``e.start``, ``e.end``, ``e.center``, and the named points of [] blocks such as
``opamp.Out`` or ``busbar.P2``. Wires are best drawn between terminals
(:meth:`Drawing.wire`) rather than computed coordinates.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Iterable, Union

__all__ = ["Expr", "Pos", "Element", "Drawing", "HERE", "gcd", "new"]


# ------------------------------------------------------------------ expressions


def _fmt(value) -> str:
    """A number, Expr or string as pic text."""
    if isinstance(value, bool):
        raise TypeError("a boolean is not a pic value")
    if isinstance(value, float):
        text = f"{value:.10g}"
        return text if "e" not in text else f"{value:.10f}".rstrip("0").rstrip(".")
    return str(value)


class Expr:
    """A pic scalar expression, e.g. ``v1.end.x`` or a variable set by :meth:`Drawing.var`."""

    def __init__(self, text) -> None:
        self.text = _fmt(text)

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return f"Expr({self.text!r})"

    def _op(self, op: str, other, reverse: bool = False) -> Expr:
        a, b = self.text, _fmt(other)
        return Expr(f"({b}{op}{a})" if reverse else f"({a}{op}{b})")

    def __add__(self, other): return self._op("+", other)
    def __radd__(self, other): return self._op("+", other, True)
    def __sub__(self, other): return self._op("-", other)
    def __rsub__(self, other): return self._op("-", other, True)
    def __mul__(self, other): return self._op("*", other)
    def __rmul__(self, other): return self._op("*", other, True)
    def __truediv__(self, other): return self._op("/", other)
    def __rtruediv__(self, other): return self._op("/", other, True)
    def __neg__(self): return Expr(f"(-{self.text})")


_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*\Z")


class Pos:
    """A pic position: a name such as ``V1.end``, a coordinate pair, or an expression."""

    def __init__(self, text: str, xy: tuple | None = None) -> None:
        self.text = text
        self._xy = xy

    @staticmethod
    def of(value: PosLike) -> Pos:
        if isinstance(value, Pos):
            return value
        if isinstance(value, Element):
            raise TypeError(f"use a terminal of {value!r}, e.g. .start or .end, as a position")
        if isinstance(value, (tuple, list)) and len(value) == 2:
            return Pos(f"({_fmt(value[0])},{_fmt(value[1])})", tuple(value))
        if isinstance(value, str):
            return Pos(value)
        raise TypeError(f"not a position: {value!r}")

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return f"Pos({self.text!r})"

    def _part(self, axis: str) -> Expr:
        if self._xy is not None:
            return Expr(self._xy[axis == "y"])
        return Expr(f"{self.text}.{axis}" if _NAME.match(self.text) else f"({self.text}).{axis}")

    @property
    def x(self) -> Expr:
        return self._part("x")

    @property
    def y(self) -> Expr:
        return self._part("y")

    def __add__(self, other) -> Pos:
        return Pos(f"{self.text}+{Pos.of(other)}")

    def __sub__(self, other) -> Pos:
        return Pos(f"{self.text}-{Pos.of(other)}")

    def with_x(self, x) -> Pos:
        """This position moved horizontally to x (a number, Expr or position)."""
        return Pos.of((x.x if isinstance(x, Pos) else x, self.y))

    def with_y(self, y) -> Pos:
        """This position moved vertically to y (a number, Expr or position)."""
        return Pos.of((self.x, y.y if isinstance(y, Pos) else y))

    def between(self, other: PosLike, fraction=0.5) -> Pos:
        return Pos(f"{_fmt(fraction)} between {self} and {Pos.of(other)}")


PosLike = Union[Pos, tuple, list, str]
HERE = Pos("Here")


# ------------------------------------------------------------------ m4 arguments


def _keys(value: dict) -> str:
    """{'name': 'G1', 'text': '"G"'} -> 'name=G1; text="G"' (Circuit Macros key=value lists)."""
    return "; ".join(f"{k}={_arg(v)}" for k, v in value.items())


def _balanced(text: str) -> bool:
    depth = 0
    for char in text:
        depth += {"(": 1, ")": -1}.get(char, 0)
        if depth < 0:
            return False
    return depth == 0


def _top_level_comma(text: str) -> bool:
    depth = 0
    for char in text:
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char == "," and depth == 0:
            return True
    return False


def _arg(value) -> str:
    """One m4 macro argument; m4-quoted only when a comma or parenthesis would split it."""
    if value is None or value is False:
        return ""
    if value is True:
        raise TypeError("a boolean is not a macro argument")
    if isinstance(value, dict):
        value = _keys(value)
    text = _fmt(value)
    if _top_level_comma(text) or not _balanced(text):
        if "`" in text or "'" in text:
            raise ValueError(f"cannot quote {text!r} for m4: it has a comma or parenthesis and a quote; "
                             "use Drawing.raw() for this statement")
        return f"`{text}'"
    return text


def _call(macro: str, args: Iterable) -> str:
    args = [_arg(a) for a in args]
    while args and args[-1] == "":
        args.pop()
    return f"{macro}({','.join(args)})" if args else macro


# ------------------------------------------------------------------ placement

_DIRECTIONS = {"up": "up_", "down": "down_", "left": "left_", "right": "right_",
               "u": "up_", "d": "down_", "l": "left_", "r": "right_"}
_PLACEMENT = ("dir", "length", "start", "end", "up", "down", "left", "right",
              "up_to", "down_to", "left_to", "right_to", "spec")


def _linespec(dir=None, length=None, start=None, end=None, up=None, down=None, left=None, right=None,
              up_to=None, down_to=None, left_to=None, right_to=None, spec=None) -> str:
    """Circuit Macros linespec from the placement keywords (see the module docstring)."""
    if spec is not None:
        return spec
    for name, value in (("up", up), ("down", down), ("left", left), ("right", right)):
        if value is not None and value is not False:
            if dir is not None:
                raise ValueError(f"give either dir= or {name}=, not both")
            dir, length = name, (None if value is True else value)
    until = [(n, v) for n, v in (("up", up_to), ("down", down_to), ("left", left_to), ("right", right_to))
             if v is not None]
    if len(until) > 1 or (until and (dir is not None or end is not None)):
        raise ValueError("give one of up_to/down_to/left_to/right_to, without dir= or end=")
    base = Pos.of(start) if start is not None else HERE
    parts = []
    if until:
        name, level = until[0]
        level = Pos.of(level) if isinstance(level, (Pos, tuple, list)) else level
        target = base.with_y(level) if name in ("up", "down") else base.with_x(level)
        parts.append(f"{_DIRECTIONS[name]} to {target}")
    elif isinstance(dir, (int, float)) and not isinstance(dir, bool):
        if end is not None:
            raise ValueError("an angle and end= cannot both be given")
        parts.append(f"to {base}+(Rect_({_fmt(length) if length is not None else 'elen_'},{_fmt(dir)}))")
    elif dir is not None:
        word = _DIRECTIONS.get(str(dir).lower())
        if word is None:
            raise ValueError(f"unknown direction {dir!r}: use up, down, left, right or an angle in degrees")
        parts.append(word if length is None else f"{word} {_fmt(length)}")
    elif length is not None:
        parts.append(f"to {base}+vec_({_fmt(length)},0)")
    if start is not None:
        parts.append(f"from {Pos.of(start)}")
    if end is not None:
        parts.append(f"to {Pos.of(end)}")
    return " ".join(parts)


def _split(kwargs: dict, names: Iterable[str]) -> dict:
    return {n: kwargs.pop(n) for n in list(names) if n in kwargs}


# ------------------------------------------------------------------ aliases

SOURCE_TYPES = {
    "voltage": "V", "current": "I", "ac": "AC", "generator": "G", "dc_voltage": "dcv", "dc_current": "dci",
    "sinusoid": "S", "sine": "S", "pulse": "P", "ramp": "R", "step": "H", "triangle": "T", "square": "U",
    "lamp": "L", "bulb": "B", "fluorescent": "F", "neon": "N", "charge": "Q", "x": "X",
}
CONSOURCE_TYPES = {"voltage": "V", "current": "I", "proximity": "P"}
GROUND_TYPES = {"normal": "N", "frame": "F", "chassis": "F", "signal": "S", "low_noise": "L",
                "protective": "P", "european": "E"}


def _alias(table: dict, value):
    return table.get(value.lower(), value) if isinstance(value, str) else value


# ------------------------------------------------------------------ elements


_CORNERS = {"n", "s", "e", "w", "ne", "nw", "se", "sw", "c", "t", "b", "l", "r"}


class Element:
    """A drawn object; its terminals and named points are positions (:class:`Pos`).

    Two-terminal elements have ``start``, ``end`` and ``center``; [] blocks have their
    Circuit Macros points as attributes, e.g. ``opamp.Out`` or ``busbar.P1``, and the
    compass points ``n``, ``s``, ``e``, ``w``, ``ne`` ... An element gets a pic label
    (``R1:``) automatically when one of its positions is used.
    """

    def __init__(self, drawing: Drawing, prefix: str, body: str, name: str | None = None) -> None:
        self._drawing = drawing
        self._prefix = prefix
        self._body = body
        self._name = drawing._claim(name) if name else None
        self._labels: list[str] = []
        self._aliases: dict[str, str] = {}

    @property
    def name(self) -> str:
        if self._name is None:
            self._name = self._drawing._auto_name(self._prefix)
        return self._name

    def __repr__(self) -> str:
        return f"<Element {self._name or self._prefix + '?'}: {self._body}>"

    def __getattr__(self, attr: str) -> Pos:
        # named points of [] blocks start with a capital (In1, Out, P1); pic corners are lower case
        aliases = self.__dict__.get("_aliases", {})
        if attr in aliases:
            return Pos(f"{self.name}.{aliases[attr]}")
        if attr[:1].isupper() or attr in _CORNERS:
            return Pos(f"{self.name}.{attr}")
        raise AttributeError(f"{type(self).__name__} has no attribute {attr!r}")

    @property
    def start(self) -> Pos:
        return Pos(f"{self.name}.start")

    @property
    def end(self) -> Pos:
        return Pos(f"{self.name}.end")

    @property
    def center(self) -> Pos:
        return Pos(f"{self.name}.c")

    def label(self, *text, side: str = "l", block: str | None = None) -> Element:
        """Label the element: one text goes at the middle, three go at start, middle and end.

        side: ``l`` (left of the drawing direction), ``r`` (right) or ``c`` (centre).
        block: the [] block to label around, if not the element's last one (e.g. ``"Body"``).
        As in Circuit Macros, the text is set in LaTeX math mode unless it begins with a
        double quote (``'"plain text"'``) or ``sprintf``.
        """
        if side not in ("l", "r", "c"):
            raise ValueError("side must be 'l', 'r' or 'c'")
        if len(text) == 1:
            text = (None, text[0], None)
        if len(text) != 3:
            raise ValueError("give one text (middle) or three texts (start, middle, end)")
        self._labels.append(_call(f"{side}label", [*text, None, block]))
        return self

    def _lines(self) -> list[str]:
        head = f"{self._name}: " if self._name else ""
        return [head + self._body + "".join(f"; {label}" for label in self._labels)]


def _with_leads(body: str, pins: dict[str, int], lead, axis: tuple[str, str], exports: Iterable[str]) -> str:
    """Wrap a [] element in a block with a lead at each pin; the pin names become the lead ends.

    A lead points along the body axis (from axis[0] to axis[1]) for +1, against it for -1,
    so it stays correct in any drawing direction.
    """
    a, b = axis
    lines = [f"Body: {body}", f"pinlen = {_fmt(lead)}", f"axlen = distance(Body.{a},Body.{b})"]
    for pin, sign in pins.items():
        s = "" if sign > 0 else "-"
        lines += [f"{pin}: Body.{pin}+({s}pinlen*(Body.{b}.x-Body.{a}.x)/axlen,"
                  f"{s}pinlen*(Body.{b}.y-Body.{a}.y)/axlen)",
                  f"line from Body.{pin} to {pin}"]
    lines += [f"{p}: Body.{p}" for p in exports]
    return "[ " + "\n  ".join(lines) + " ]"


class _Raw:
    def __init__(self, text: str) -> None:
        self.text = text

    def _lines(self) -> list[str]:
        return self.text.splitlines()


# ------------------------------------------------------------------ drawing

_UNITS = {"mm": "25.4", "cm": "2.54", "in": None, "inch": None}
_current: list[Drawing] = []


class Drawing:
    """A Circuit Macros picture built in Python.

    unit: ``mm`` (default, ``scale=25.4``), ``cm`` or ``in`` (Circuit Macros native).
    libraries: extra m4 libraries to include, e.g. ``["libSLD.m4"]``; the SLD methods
    include libSLD.m4 themselves.
    """

    def __init__(self, unit: str = "mm", libraries: Iterable[str] = ()) -> None:
        if unit not in _UNITS:
            raise ValueError(f"unknown unit {unit!r}: use mm, cm or in")
        self.unit = unit
        self.libraries = list(libraries)
        self._items: list = []
        self._names: set[str] = set()
        self._counters: dict[str, int] = {}

    # -------------------------------------------------- context / current drawing

    def __enter__(self) -> Drawing:
        _current.append(self)
        return self

    def __exit__(self, *exc) -> None:
        _current.remove(self)

    # -------------------------------------------------- names

    def _claim(self, name: str) -> str:
        if not re.fullmatch(r"[A-Z][A-Za-z0-9_]*", name):
            raise ValueError(f"pic labels start with a capital letter: {name!r}")
        if name in self._names:
            raise ValueError(f"the name {name!r} is already used in this drawing")
        self._names.add(name)
        return name

    def _auto_name(self, prefix: str) -> str:
        n = self._counters.get(prefix, 0)
        while True:
            n += 1
            if f"{prefix}{n}" not in self._names:
                break
        self._counters[prefix] = n
        return self._claim(f"{prefix}{n}")

    # -------------------------------------------------- generic statements

    def raw(self, text: str) -> None:
        """Add pic or m4 text unchanged, for anything the facade does not cover."""
        self._items.append(_Raw(text))

    def include(self, library: str) -> None:
        if library not in self.libraries:
            self.libraries.append(library)

    def var(self, name: str, value) -> Expr:
        """Define a pic variable, ``dx = 12.5``, and return it as an expression."""
        if not re.fullmatch(r"[a-z][A-Za-z0-9_]*", name):
            raise ValueError(f"pic variables start with a lower-case letter: {name!r}")
        self._items.append(_Raw(f"{name} = {_fmt(value)}"))
        return Expr(name)

    def point(self, name: str, at: PosLike = HERE) -> Pos:
        """Name a position, ``O: (0,0)``, and return it."""
        self._items.append(_Raw(f"{self._claim(name)}: {Pos.of(at)}"))
        return Pos(name)

    @property
    def here(self) -> Pos:
        return HERE

    def element(self, macro: str, *args, prefix: str = "E", name: str | None = None, kind: str = "line",
                at: PosLike | None = None, anchor: str | None = None, label=None, llabel=None, rlabel=None,
                clabel=None, label_block: str | None = None, pins: dict[str, int] | None = None,
                lead=None, axis: tuple[str, str] = ("W", "E"), exports: Iterable[str] = (),
                **kwargs) -> Element:
        """Any Circuit Macros element macro.

        kind ``line``: the first macro argument is a linespec, built from the placement
        keywords (two-terminal elements and stems). kind ``block``: a [] block whose
        linespec only sets its direction; it is put with ``anchor`` (a point of the
        block, e.g. ``"In1"``, default its centre) at ``at``. Remaining keyword
        arguments are not allowed; give macro arguments positionally.

        Pins (kind ``block``): ``pins`` maps points of the macro's body to -1 (a lead drawn
        backwards along the body ``axis``, e.g. inputs) or +1 (forwards, e.g. outputs).
        With a nonzero ``lead`` length, the body is wrapped in a block named ``Body``
        with a lead at each pin, and the pin names then mean the lead ends, where wires
        connect. ``exports`` re-exports other body points (``W``, ``N`` ...) on the wrapper.
        """
        place = _split(kwargs, _PLACEMENT)
        if kwargs:
            raise TypeError(f"{macro}: unknown keyword(s) {', '.join(kwargs)}")
        if kind == "line":
            if at is not None and "start" not in place:
                place["start"] = at
            body = _call(macro, [_linespec(**place) or None, *args])
        elif kind == "block":
            body = _call(macro, [_linespec(**place) or None, *args])
            if pins and lead:
                body = _with_leads(body, pins, lead, axis, exports)
            if at is not None:
                body += f" with .{anchor or 'c'} at {Pos.of(at)}"
        else:
            raise ValueError("kind must be 'line' or 'block'")
        e = Element(self, prefix, body, name)
        for side, text in (("l", label), ("l", llabel), ("r", rlabel), ("c", clabel)):
            if text is not None:
                e.label(*(text if isinstance(text, (tuple, list)) else (text,)), side=side, block=label_block)
        self._items.append(e)
        return e

    # -------------------------------------------------- wires

    def line(self, *points: PosLike, arrow: bool = False, name: str | None = None, attrs: str = "",
             **place) -> Element:
        """A line through the given points, or placed like an element (``up=10``, ``end=P``)."""
        if len(points) > 1 and place:
            raise ValueError("give points or placement keywords, not both")
        if len(points) == 1:
            place["end"] = points[0]
            points = ()
        if points:
            spec = f"from {Pos.of(points[0])} " + " then ".join(f"to {Pos.of(p)}" for p in points[1:])
        else:
            spec = _linespec(**place)
        body = ("arrow" if arrow else "line") + (f" {spec}" if spec else "") + (f" {attrs}" if attrs else "")
        e = Element(self, "W", body, name)
        self._items.append(e)
        return e

    def wire(self, a: PosLike, b: PosLike, route: str = "-|", via: Iterable[PosLike] = (),
             dot: bool | str = False, name: str | None = None) -> Element:
        """Orthogonal wire from a to b, so that no diagonal is drawn.

        route ``-|``: horizontal first, then vertical; ``|-``: vertical first;
        ``-``/``|``: straight (the end is projected onto a's level). ``via`` adds
        bend points; ``dot`` puts a junction dot at ``"start"``, ``"end"`` or both (True).
        """
        a, b = Pos.of(a), Pos.of(b)
        corners = [Pos.of(p) for p in via]
        if not corners:
            if route == "-|":
                corners = [a.with_x(b)]
            elif route == "|-":
                corners = [a.with_y(b)]
            elif route == "-":
                b = a.with_x(b)
            elif route == "|":
                b = a.with_y(b)
            else:
                raise ValueError("route must be '-|', '|-', '-' or '|'")
        w = self.line(a, *corners, b, name=name)
        if dot in (True, "start"):
            self.dot(a)
        if dot in (True, "end"):
            self.dot(b)
        return w

    def move(self, **place) -> None:
        """Move the current position without drawing (``move(end=P)``, ``move(right=5)``)."""
        self._items.append(_Raw("move " + _linespec(**place)))

    def dot(self, at: PosLike | None = None) -> None:
        """Junction dot, at the current position or at ``at``."""
        self._items.append(_Raw(_call("dot", [f"at {Pos.of(at)}" if at is not None else None])))

    def ground(self, at: PosLike | None = None, kind: str = "normal", dir: str | float | None = None,
               stem=None) -> None:
        """Ground symbol; kind: normal, frame, signal, low_noise, protective, european (or N, F, ...)."""
        direction = {"up": "U", "down": "D", "left": "L", "right": "R"}.get(dir, dir)
        args = [f"at {Pos.of(at)}" if at is not None else None, "T" if stem is True else stem,
                _alias(GROUND_TYPES, kind) if kind != "normal" else None, direction]
        self._items.append(_Raw(_call("ground", args)))

    # -------------------------------------------------- two-terminal elements (libcct.m4)

    def source(self, type: str = "voltage", diameter=None, reversed: bool = False, attributes=None,
               body_name=None, **kw) -> Element:
        """Independent source, ``source(linespec, type, diameter, R, attributes, name)``.

        type: voltage, current, ac, generator, dc_voltage, dc_current, sinusoid, pulse,
        ramp, step, triangle, square, lamp, ... or a Circuit Macros code (V, I, AC, S, ...).
        """
        return self.element("source", _alias(SOURCE_TYPES, type), diameter, "R" if reversed else None,
                            attributes, body_name, prefix="V", **kw)

    def consource(self, type: str = "voltage", reversed: bool = False, attributes=None, **kw) -> Element:
        """Controlled (dependent) source; type: voltage, current, proximity or V, I, v, tv, i, ti, P."""
        return self.element("consource", _alias(CONSOURCE_TYPES, type), "R" if reversed else None,
                            attributes, prefix="V", **kw)

    def resistor(self, cycles=None, chars=None, cycle_wid=None, **kw) -> Element:
        """Resistor; chars: E (box), Q, H, T (thermistor), V (varistor), ... (Circuit Macros manual)."""
        return self.element("resistor", cycles, chars, cycle_wid, prefix="R", **kw)

    def capacitor(self, chars=None, reversed: bool = False, height=None, wid=None, **kw) -> Element:
        """Capacitor; chars: F (flat, default), C (polarized curved), E, K, M, N, P, CP, + ..."""
        return self.element("capacitor", chars, "R" if reversed else None, height, wid, prefix="C", **kw)

    def inductor(self, shape=None, cycles=None, core=None, loop_wid=None, **kw) -> Element:
        """Inductor; shape W (wide) or L (looped); core M[n] (metal), P[n] (powder), K[n]."""
        return self.element("inductor", shape, cycles, core, loop_wid, prefix="L", **kw)

    def ebox(self, keys: dict | str | None = None, **kw) -> Element:
        """Box element (impedance); keys e.g. ``{"lgth": 8, "wdth": 4, "text": '"Z"'}``."""
        return self.element("ebox", keys, prefix="Z", **kw)

    def diode(self, type=None, reversed: bool = False, enclosure: bool = False, **kw) -> Element:
        """Diode; type: a Circuit Macros code (S, V, v, w, B, b, G, D, z, Z, K, CR, L, F, Sh, U, T, P, LE,
        ...: see the Diodes figure of the Circuit Macros manual); ``enclosure`` draws the envelope."""
        flags = ("R" if reversed else "") + ("E" if enclosure else "")
        return self.element("diode", type, flags or None, prefix="D", **kw)

    def battery(self, cells=None, reversed: bool = False, **kw) -> Element:
        return self.element("battery", cells, "R" if reversed else None, prefix="B", **kw)

    def switch(self, side=None, chars=None, kind=None, attribs=None, **kw) -> Element:
        """Switch, ``switch(linespec, L|R, [O|C][D], L|B|D, attribs)``."""
        return self.element("switch", side, chars, kind, attribs, prefix="S", **kw)

    def fuse(self, chars=None, wid=None, ht=None, attributes=None, **kw) -> Element:
        return self.element("fuse", chars, wid, ht, attributes, prefix="F", **kw)

    # -------------------------------------------------- [] blocks (libcct.m4)

    def opamp(self, minus=None, plus=None, size=None, chars=None, lead="dimen_/4", **kw) -> Element:
        """Operational amplifier with pins.

        The terminals are the ends of short leads of length ``lead``: ``In1`` (inverting,
        alias ``inv``), ``In2`` (non-inverting, ``noninv``) and ``Out`` (``out``); the body
        points ``W``, ``N``, ``E``, ``S``, ``E1``, ``E2`` (and ``V1``, ``V2`` with chars ``P``)
        are kept. ``lead=0`` gives the plain Circuit Macros op-amp, terminals on the body.

        Put it with ``at=`` and ``anchor=`` (e.g. ``anchor="In1", at=r1.end``); ``dir``
        sets its direction. Blank ``minus``/``plus`` draw the standard signs at the inputs;
        other input labels are pic text with a position, e.g. ``'"$v_n$" at In1+(1,0)'``.
        """
        exports = ["W", "N", "E", "S", "E1", "E2"] + (["V1", "V2"] if chars and "P" in str(chars) else [])
        e = self.element("opamp", minus, plus, size, chars, prefix="A", kind="block",
                         pins={"In1": -1, "In2": -1, "Out": 1}, lead=lead, exports=exports, **kw)
        e._aliases.update(inv="In1", noninv="In2", out="Out")
        return e

    def transformer(self, side=None, np=None, chars=None, ns=None, **kw) -> Element:
        """Two-winding transformer (a [] block with P1, P2, S1, S2)."""
        return self.element("transformer", side, np, chars, ns, prefix="T", kind="block", **kw)

    # -------------------------------------------------- single-line diagrams (libSLD.m4)

    def _sld(self, macro: str, *args, prefix: str, **kw) -> Element:
        self.include("libSLD.m4")
        return self.element(macro, *args, prefix=prefix, **kw)

    def busbar(self, ports: int = 2, keys: dict | str | None = None, **kw) -> Element:
        """SLD busbar with points P1 ... Pn, ``sl_busbar(linespec, np, keys)``."""
        return self._sld("sl_busbar", ports, keys, prefix="Bus", **kw)

    def sl_transformer(self, keys: dict | str | None = None, breaker_in=None, breaker_out=None,
                       symbol_in=None, symbol_out=None, **kw) -> Element:
        """SLD transformer; keys type=I|S|A, ...; breaker_in/out: C, O, X, S:... ; symbol_in/out: Y, YN, Delta.

        Labels go around the transformer body (the block ``Body``, or the key ``name``),
        not around its breakers. With breakers the element needs room for them: at the
        default sizes about 30 mm; shorter, a breaker is drawn beyond the start point.
        """
        body = keys.get("name", "Body") if isinstance(keys, dict) else "Body"
        kw.setdefault("label_block", body)
        return self._sld("sl_transformer", keys, breaker_in, breaker_out, symbol_in, symbol_out, prefix="T", **kw)

    def sl_breaker(self, keys: dict | str | None = None, **kw) -> Element:
        """SLD circuit breaker; keys type=[A|C][D]; ..."""
        return self._sld("sl_breaker", keys, prefix="Br", **kw)

    def sl_generator(self, keys: dict | str | None = None, breaker=None, **kw) -> Element:
        """SLD generator at the end of a stem (placement as for two-terminal elements)."""
        return self._sld("sl_generator", keys, breaker, prefix="G", **kw)

    def sl_load(self, keys: dict | str | None = None, breaker=None, **kw) -> Element:
        """SLD load arrow at the end of a stem."""
        return self._sld("sl_load", keys, breaker, prefix="Ld", **kw)

    def sl_disk(self, keys: dict | str | None = None, breaker=None, **kw) -> Element:
        return self._sld("sl_disk", keys, breaker, prefix="D", **kw)

    def sl_box(self, keys: dict | str | None = None, breaker=None, **kw) -> Element:
        return self._sld("sl_box", keys, breaker, prefix="X", **kw)

    def sl_ttbox(self, keys: dict | str | None = None, breaker_in=None, breaker_out=None, **kw) -> Element:
        """Two-terminal SLD box (e.g. converter); keys text="..."; ..."""
        return self._sld("sl_ttbox", keys, breaker_in, breaker_out, prefix="X", **kw)

    # -------------------------------------------------- output

    def to_m4(self) -> str:
        """The drawing as Circuit Macros source."""
        lines = [".PS", "include(pstricks.m4)"]
        lines += [f"include({lib})" for lib in self.libraries]
        if _UNITS[self.unit]:
            lines.append(f"scale={_UNITS[self.unit]}")
        lines.append("cct_init")
        lines.append("")
        for item in self._items:
            lines += item._lines()
        lines.append(".PE")
        return "\n".join(lines) + "\n"

    def __str__(self) -> str:
        return self.to_m4()

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.write_text(self.to_m4(), encoding="utf-8", newline="\n")
        return path

    def render(self, path: str | Path = "figure.m4cm", *, pdf: bool = False, png: bool = False,
               jpg: bool = False, svg: bool = False, eps: bool = True, resolution: int | None = None,
               output_dir: str | Path | None = None, options: Iterable[str] = ()) -> list[Path]:
        """Save the source to ``path`` and run ``m4cm`` on it; return the files made.

        ``eps=False`` deletes the EPS when another format is made (``m4cm -d``);
        ``options`` passes further ``m4cm`` options, e.g. ``["-t", "my.ltx"]``.
        """
        from . import main  # here, to keep this module importable on its own

        src = self.save(path)
        flags = [f for f, on in (("-p", pdf), ("-n", png), ("-j", jpg), ("-s", svg)) if on]
        argv = ["-Q", *flags, *([] if eps else ["-d"]), *options]
        if resolution:
            argv += ["-r", str(resolution)]
        if output_dir:
            argv += ["-o", str(output_dir)]
        if main([*argv, str(src)]):
            raise RuntimeError(f"m4cm could not render {src}; run 'm4cm {' '.join(argv)} {src}' to see why")
        out = Path(output_dir) if output_dir else src.parent
        exts = [e for e, on in (("eps", eps or not flags), ("pdf", pdf), ("png", png), ("jpg", jpg), ("svg", svg))
                if on]
        return [out / f"{src.stem}.{e}" for e in exts]

    def _repr_svg_(self) -> str | None:
        """Inline display in Jupyter (needs the TeX tools)."""
        with tempfile.TemporaryDirectory() as tmp:
            try:
                files = self.render(Path(tmp) / "figure.m4cm", svg=True, eps=False)
            except (RuntimeError, OSError):
                return None
            return files[-1].read_text(encoding="utf-8")


# ------------------------------------------------------------------ pyplot-style interface


def gcd() -> Drawing:
    """The current drawing: the innermost ``with Drawing()``, else one made by :func:`new`."""
    if not _current:
        _current.append(Drawing())
    return _current[-1]


def new(unit: str = "mm", libraries: Iterable[str] = ()) -> Drawing:
    """Start a new current drawing for the module-level functions."""
    _current.clear()
    _current.append(Drawing(unit, libraries))
    return _current[-1]


def _forward(name: str):
    method = getattr(Drawing, name)

    def function(*args, **kwargs):
        return getattr(gcd(), name)(*args, **kwargs)

    function.__name__ = function.__qualname__ = name
    function.__doc__ = method.__doc__
    function.__wrapped__ = method
    return function


raw = _forward("raw")
include = _forward("include")
var = _forward("var")
point = _forward("point")
element = _forward("element")
line = _forward("line")
wire = _forward("wire")
move = _forward("move")
dot = _forward("dot")
ground = _forward("ground")
source = _forward("source")
consource = _forward("consource")
resistor = _forward("resistor")
capacitor = _forward("capacitor")
inductor = _forward("inductor")
ebox = _forward("ebox")
diode = _forward("diode")
battery = _forward("battery")
switch = _forward("switch")
fuse = _forward("fuse")
opamp = _forward("opamp")
transformer = _forward("transformer")
busbar = _forward("busbar")
sl_transformer = _forward("sl_transformer")
sl_breaker = _forward("sl_breaker")
sl_generator = _forward("sl_generator")
sl_load = _forward("sl_load")
sl_disk = _forward("sl_disk")
sl_box = _forward("sl_box")
sl_ttbox = _forward("sl_ttbox")
to_m4 = _forward("to_m4")
save = _forward("save")
render = _forward("render")
