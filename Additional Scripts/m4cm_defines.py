#!/usr/bin/env python3
"""Regenerate the m4cm syntax highlighting from the Circuit Macros documentation.

The Circuit Macros names are the \\macrodef entries of doc/defines.tex, the m4
names are the GNU m4 builtins (as in pym4) and the pic keywords come from pppic.
The script updates the keyword lists in ../Syntax Highlighting (Kate/Kile,
Notepad++, Programmer's Notepad 2), regenerates the VS Code grammar and .vsix,
and writes the plain word lists in ./defines.

Usage:  python m4cm_defines.py [CIRCUIT_MACROS_DIR | defines.tex]

Without an argument it uses the copy downloaded by "m4cm --get-cm",
else ./defines/defines.tex.
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from pppic import DOTWORDS, FUNC1, FUNC2, KEYWORDS, OPTION_VARS, SCALED_ENV, UNSCALED_ENV

HERE = Path(__file__).resolve().parent
SYNTAX = HERE.parent / "Syntax Highlighting"
VSCODE = SYNTAX / "VS Code"

M4_BUILTINS = sorted("""builtin changecom changequote debugfile debugmode decr define defn divert divnum dnl
    dumpdef errprint esyscmd eval format ifdef ifelse include incr index indir len m4exit m4wrap maketemp
    mkstemp patsubst popdef pushdef regexp shift sinclude substr syscmd sysval traceoff traceon translit
    undefine undivert""".split())
ORDINALS = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th"]
PIC_CONTROL = {"if", "then", "else", "for", "do", "define", "undef", "undefine", "copy", "reset", "exec",
               "sh", "command", "print"}
PIC_PRIMITIVES = {"box", "circle", "ellipse", "arc", "line", "arrow", "move", "spline"}


def by_name(words) -> list[str]:
    return sorted(set(words), key=lambda w: (w.lower(), w))


def find_defines(arg: str | None) -> Path:
    if arg:
        path = Path(arg)
        return path if path.is_file() else path / "doc" / "defines.tex"
    try:
        from m4cmpy import cache_dir
        cached = cache_dir() / "circuit_macros" / "doc" / "defines.tex"
        if cached.is_file():
            return cached
    except ImportError:
        pass
    return HERE / "defines" / "defines.tex"


def circuit_macros(defines: Path) -> list[str]:
    names = []
    for entry in re.findall(r"\\macrodef\{([^}]*)\}", defines.read_text(encoding="latin-1")):
        # some entries document several macros, e.g. "And, Or, Not, Nand, Nor, Xor, Nxor, Buffer"
        names += [n.strip() for n in entry.replace("\\_", "_").split(",")]
    return by_name(n for n in names if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n))


def cm_version(defines: Path) -> str:
    readme = defines.parent.parent / "README"
    match = re.search(r"Version\s+([\d.]+)", readme.read_text(errors="replace")) if readme.is_file() else None
    return match.group(1).rstrip(".") if match else "unknown"


def pic_keywords() -> list[str]:
    return by_name([w for w in KEYWORDS if w not in ("st", "nd", "rd", "th")] + list(OPTION_VARS))


def replace_block(text: str, start: str, end: str, body: str) -> str:
    pattern = re.compile(f"({start})(.*?)({end})", re.S)
    if not pattern.search(text):
        raise ValueError(f"{start!r} not found")
    return pattern.sub(lambda m: m.group(1) + body + m.group(3), text, count=1)


def rewrite(path: Path, update) -> None:
    text = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in text else "\n"
    path.write_bytes(update(text, eol).encode("utf-8"))
    print(f"updated {path.relative_to(HERE.parent)}")


def update_kate(version: str, m4: list[str], pic: list[str], cm: list[str]) -> None:
    def update(text: str, eol: str) -> str:
        items = lambda words: "".join(f"{eol}      <item> {w} </item>" for w in words)  # noqa: E731
        text = replace_block(text, r'<list name="builtinfuncs">', r'\r?\n[ \t]*</list>', items(m4))
        text = replace_block(text, r'<list name="keywords">', r'\r?\n[ \t]*</list>', items(ORDINALS + pic))
        text = replace_block(text, r'<list name="specialvars">', r'\r?\n[ \t]*</list>', items(cm))
        text = re.sub(r"<!-- M4 Circuit Macro .*?-->", f"<!-- M4 Circuit Macros {version} syntax highlighting, "
                      "see https://ctan.org/pkg/circuit-macros -->", text, count=1)
        text = re.sub(r"<!-- The M4 Circuit Macros [^>]*-->", f"<!-- The M4 Circuit Macros {version} -->", text)
        # Kate reads the version as an integer: 11.1 -> 1101
        major, minor = (version.split(".") + ["0"])[:2] if version != "unknown" else ("0", "0")
        return re.sub(r'(<language name="M4 Circuit Macros" version=")[^"]*',
                      lambda m: m.group(1) + str(int(major) * 100 + int(minor)), text, count=1)
    rewrite(SYNTAX / "Katepart" / "m4cm.xml", update)


def update_notepad_plus_plus(m4: list[str], pic: list[str], cm: list[str]) -> None:
    def update(text: str, eol: str) -> str:
        crlf = "&#x000D;&#x000A;"
        for name, words in (("Keywords1", m4), ("Keywords2", sorted(DOTWORDS) + ORDINALS + pic), ("Keywords3", cm)):
            text = replace_block(text, f'<Keywords name="{name}">', "</Keywords>", crlf.join(words))
        return text
    rewrite(SYNTAX / "Notepad++" / "m4cm.xml", update)


def update_programmers_notepad(version: str, m4: list[str], pic: list[str], cm: list[str]) -> None:
    def update(text: str, eol: str) -> str:
        indent = eol + "\t\t\t"
        text = replace_block(text, r'<keyword-class name="m4">', r"\s*</keyword-class>", indent + " ".join(m4))
        text = replace_block(text, r'<keyword-class name="pic">', r"\s*</keyword-class>",
                             indent + " ".join(sorted(DOTWORDS) + ORDINALS + pic))
        text = replace_block(text, r'<keyword-class name="cm">\s*<!--[^>]*-->', r"\s*</keyword-class>",
                             indent + " ".join(cm))
        return re.sub(r"(by Dwight Aplevich, Version )[\d.]+", lambda m: m.group(1) + version, text)
    rewrite(SYNTAX / "Programmer's Notepad 2" / "m4cm.scheme", update)


def words_regex(words) -> str:
    return r"\b(?:" + "|".join(sorted(words, key=lambda w: (-len(w), w))) + r")\b"


def vscode_grammar(version: str, m4: list[str], pic: list[str], cm: list[str]) -> dict:
    functions = set(FUNC1) | set(FUNC2) | {"sprintf", "rand"}
    variables = set(SCALED_ENV) | set(UNSCALED_ENV) | set(OPTION_VARS) | {"Here"}
    other = [w for w in pic if w not in PIC_CONTROL | PIC_PRIMITIVES | functions | variables]
    dots = sorted((w[1:] for w in DOTWORDS), key=lambda w: (-len(w), w))
    return {
        "$schema": "https://raw.githubusercontent.com/martinring/tmlanguage/master/tmlanguage.json",
        "name": "M4 Circuit Macros",
        "comment": f"Generated by m4cm_defines.py from Circuit Macros {version}; do not edit by hand.",
        "scopeName": "source.m4cm",
        "patterns": [{"include": "#statement"}],
        "repository": {
            "statement": {"patterns": [{"include": f"#{name}"} for name in (
                "comment", "dnl", "picture", "string", "m4-quote", "label", "m4-builtin", "circuit-macro",
                "pic-control", "pic-primitive", "pic-function", "pic-variable", "pic-keyword", "corner",
                "argument", "tex", "ordinal", "number")]},
            "comment": {"name": "comment.line.number-sign.m4cm", "match": "#.*$"},
            "dnl": {"name": "comment.line.dnl.m4", "match": r"\bdnl\b.*$"},
            "picture": {"name": "keyword.control.directive.pic", "match": r"^\.P[SEF]\b"},
            "string": {"name": "string.quoted.double.pic", "begin": '"', "end": '"',
                       "patterns": [{"match": r'\\"', "name": "constant.character.escape.pic"},
                                    {"include": "#argument"}, {"include": "#tex"}]},
            "m4-quote": {"name": "string.quoted.other.m4", "begin": "`", "end": "'",
                         "patterns": [{"include": "#statement"}]},
            "label": {"match": r"\b([A-Z][A-Za-z0-9_]*)\s*(:)(?!=)",
                      "captures": {"1": {"name": "entity.name.label.pic"},
                                   "2": {"name": "punctuation.separator.label.pic"}}},
            "m4-builtin": {"name": "support.function.builtin.m4", "match": words_regex(m4)},
            "circuit-macro": {"name": "support.function.circuit-macros", "match": words_regex(cm)},
            "pic-control": {"name": "keyword.control.pic", "match": words_regex(PIC_CONTROL)},
            "pic-primitive": {"name": "storage.type.primitive.pic", "match": words_regex(PIC_PRIMITIVES)},
            "pic-function": {"name": "support.function.math.pic", "match": words_regex(functions)},
            "pic-variable": {"name": "variable.language.pic", "match": words_regex(variables)},
            "pic-keyword": {"name": "keyword.other.pic", "match": words_regex(other)},
            "corner": {"name": "variable.other.property.pic", "match": r"\.(?:" + "|".join(dots) + r")\b"},
            "argument": {"name": "variable.parameter.m4cm", "match": r"\$(?:\d+|[#*@+])"},
            "tex": {"name": "support.function.tex", "match": r"\\[A-Za-z]+"},
            "ordinal": {"name": "constant.numeric.ordinal.pic", "match": r"\b\d+(?:st|nd|rd|th)\b"},
            "number": {"name": "constant.numeric.pic",
                       "match": r"(?<![\w.])(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"},
        },
    }


def build_vscode(version: str, m4: list[str], pic: list[str], cm: list[str]) -> None:
    grammar = VSCODE / "syntaxes" / "m4cm.tmLanguage.json"
    grammar.parent.mkdir(parents=True, exist_ok=True)
    grammar.write_text(json.dumps(vscode_grammar(version, m4, pic, cm), indent=2) + "\n", encoding="utf-8")
    print(f"updated {grammar.relative_to(HERE.parent)}")
    manifest = json.loads((VSCODE / "package.json").read_text(encoding="utf-8"))
    vsix = VSCODE / f"{manifest['name']}-{manifest['version']}.vsix"
    files = ["package.json", "language-configuration.json", "syntaxes/m4cm.tmLanguage.json"]
    with zipfile.ZipFile(vsix, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="utf-8"?>\n'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension=".json" ContentType="application/json"/>'
                   '<Default Extension=".vsixmanifest" ContentType="text/xml"/></Types>\n')
        z.writestr("extension.vsixmanifest", f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="{manifest['name']}" Version="{manifest['version']}" Publisher="{manifest['publisher']}"/>
    <DisplayName>{escape(manifest['displayName'])}</DisplayName>
    <Description xml:space="preserve">{escape(manifest['description'])}</Description>
    <Categories>Programming Languages</Categories>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{manifest['engines']['vscode']}"/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="ui,workspace"/>
    </Properties>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>
  </Assets>
</PackageManifest>
""")
        for name in files:
            z.write(VSCODE / name, f"extension/{name}")
    print(f"updated {vsix.relative_to(HERE.parent)}")


def write_word_lists(cm: list[str]) -> None:
    out = HERE / "defines"
    out.mkdir(exist_ok=True)
    (out / "m4cm_defines_katepart.txt").write_text("".join(f"<item> {w} </item>\n" for w in cm), encoding="utf-8")
    (out / "m4cm_defines_notepad++.txt").write_text("".join(f"{w}\n" for w in cm), encoding="utf-8")
    (out / "m4cm_defines_pnotepad2.txt").write_text(" ".join(cm), encoding="utf-8")


def main(argv: list[str]) -> int:
    defines = find_defines(argv[0] if argv else None)
    if not defines.is_file():
        print(f"{defines} not found; run 'm4cm --get-cm' or pass the Circuit Macros folder", file=sys.stderr)
        return 1
    version = cm_version(defines)
    cm, m4, pic = circuit_macros(defines), M4_BUILTINS, pic_keywords()
    print(f"Circuit Macros {version}: {len(cm)} macros from {defines}")
    write_word_lists(cm)
    update_kate(version, m4, pic, cm)
    update_notepad_plus_plus(m4, pic, cm)
    update_programmers_notepad(version, m4, pic, cm)
    build_vscode(version, m4, pic, cm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
