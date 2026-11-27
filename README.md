# m4cmpy

[![CI](https://github.com/pjrandewijk/m4cmpy/actions/workflows/ci.yml/badge.svg)](https://github.com/pjrandewijk/m4cmpy/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/m4cmpy?label=PyPI)](https://pypi.org/project/m4cmpy/)

The M4 Circuit Macros (M4CM) Python automation package simplifies to process to create standalone EPS, PDF, PNG, JPG and
SVG pictures from [Circuit Macros](https://ctan.org/pkg/circuit-macros) source, see also [peter.randewijk.dk/m4cmpy](https://peter.randewijk.dk/m4cmpy/) for examples.

Version 4 needs **only Python and a TeX distribution** (MiKTeX or TeX Live):
GNU m4, dpic and ImageMagick are no longer required.

| Package | Replaces | Role |
|---|---|---|
| [pym4](https://github.com/pjrandewijk/pym4) | GNU m4 | m4 → pic |
| [pppic](https://github.com/pjrandewijk/pppic) | dpic -p | pic → PSTricks |
| **m4cmpy** | m4cm.py 3.3 | m4 → PDF / PNG / JPG / SVG / EPS |

## Install

```
pip install m4cmpy
m4cm --get-cm
```

`m4cm --get-cm` downloads the latest [Circuit Macros](https://ctan.org/pkg/circuit-macros)
from CTAN into your user cache folder. Alternatively set `M4PATH`, pass `-I DIR`,
or rely on the copy in your TeX tree (found with `kpsewhich libcct.m4`).

The TeX tools come from MiKTeX or TeX Live: `latex`, `dvips`, Ghostscript
(`mgs` in MiKTeX, `gs` elsewhere), `epstopdf` for PDF and `dvisvgm` for SVG.
MiKTeX does not have to be on `PATH`; use `--tex-bin DIR` for other locations.

## Use

```
m4cm -p -n -s ex0.m4cm         # PDF, PNG and SVG (plus EPS)
m4cm -p -d *.m4cm              # PDF only, for every .m4cm file in the folder
m4cm -n -r 192 -o web ex0.m4cm # 192 dpi PNG in the folder "web"
```

| Option | Meaning |
|---|---|
| `-e` | EPS (always made, default) |
| `-p` / `-n` / `-j` / `-s` | PDF / PNG (transparent) / JPG / SVG |
| `--svg-fonts` | SVG with embedded WOFF2 fonts instead of outlines |
| `-d` | delete the EPS afterwards |
| `-r DPI` | PNG/JPG resolution (default 600) |
| `-b L B R T` | bounding-box offset in points (default 1 1 1 1) |
| `-a TEXT` | append TEXT to the output file names |
| `-o DIR` | output folder |
| `-t FILE` | LaTeX template (default `default.ltx`) |
| `-I DIR` | extra m4 include folder, e.g. for your own macro libraries |
| `-q` / `-Q` | quiet / silent |

The LaTeX template is looked up in the current folder, then next to the input;
without one, a built-in template is used. Templates must contain a line with
`%dpic_pstricks_output_here%`; see [Examples/default.ltx](Examples/default.ltx).

## Scripting in Python

`m4cmpy.cm` writes Circuit Macros source from Python and renders it with `m4cm`:

```python
import m4cmpy.cm as cm

with cm.Drawing() as d:                         # lengths in mm
    O = d.point("O", (0, 0))
    d.source("sinusoid", up=12.5, start=O, label=r"\mathbf{V}_s")
    d.inductor(right=25, label="jX_s")
    d.ebox(down_to=O, label=r"\mathbf{Z}_l")    # down to the level of O
    d.line(end=O)
    d.ground()
d.render("ex0.m4cm", pdf=True, png=True)        # also writes ex0.m4cm
```

* Methods are named after the Circuit Macros macros (`source`, `resistor`, `opamp`,
  `busbar`, `sl_transformer`, ...) and take their arguments; readable aliases such as
  `"voltage"` stand for the macro codes (`V`). `d.element("anymacro", ...)` reaches the rest.
* Place an element by direction (`up=12.5`, `right=True`, `dir=30`), by coordinates or
  terminals (`start=(0, 0)`, `end=r1.end`), or by direction to a level (`down_to=O`).
  Without placement it continues from the previous element, as in Circuit Macros.
* Terminals are positions: `r1.start`, `r1.end`, `r1.center`, `amp.Out`, `bus.P2`.
  `d.wire(a, b, route="-|")` joins two terminals with orthogonal segments.
* The module-level functions (`cm.source(...)`, `cm.render(...)`) work on a current
  drawing, as in matplotlib's pyplot.

See [Examples/facade_example.py](Examples/facade_example.py).

## Repository

| Folder | Contents |
|---|---|
| [src/m4cmpy](src/m4cmpy) | the `m4cm` command |
| [tests](tests) | unit, toolchain and end-to-end tests: `python -m unittest discover -s tests -v` |
| [Examples](Examples) | example `.m4cm` files and template |
| [Sansserif Math LaTeX Style Files](Sansserif%20Math%20LaTeX%20Style%20Files) | `sansserifmath.sty`, used by the example template |
| [Syntax Highlighting](Syntax%20Highlighting) | VS Code (`.vsix`), Notepad++, Kate and Programmer's Notepad definitions |
| [Additional Scripts](Additional%20Scripts) | animation helper, and `m4cm_defines.py`, which regenerates the syntax highlighting from a Circuit Macros release |
| [legacy/m4cm.py](legacy/m4cm.py) | the classic script (version 3.3), which still uses m4, dpic and ImageMagick |

CI runs the tests on Windows, macOS and Linux against the latest pym4 and
pppic, and builds the example with TeX Live (the figures are kept as a build artifact).

## Licence

GPL-3.0-or-later; see [LICENSE](LICENSE). Circuit Macros and dpic are by
J. D. Aplevich.
