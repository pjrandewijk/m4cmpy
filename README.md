# m4cmpy

[![CI](https://github.com/pjrandewijk/m4cmpy/actions/workflows/ci.yml/badge.svg)](https://github.com/pjrandewijk/m4cmpy/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/m4cmpy?label=PyPI)](https://pypi.org/project/m4cmpy/)

M4 Circuit Macros Python automation script to create standalone PDF, PNG, JPG,
SVG and EPS pictures with ease (see [m4cmpy.wordpress.com](https://m4cmpy.wordpress.com)).

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
`%dpic_pstricks_output_here%`; see [My Examples/default.ltx](My%20Examples/default.ltx).

## Repository

| Folder | Contents |
|---|---|
| [src/m4cmpy](src/m4cmpy) | the `m4cm` command |
| [tests](tests) | unit, toolchain and end-to-end tests: `python -m unittest discover -s tests -v` |
| [My Examples](My%20Examples) | example `.m4cm` files and template |
| [My LaTeX Style Files](My%20LaTeX%20Style%20Files) | `sansserifmath.sty`, used by the example template |
| [Syntax Highlighting](Syntax%20Highlighting) | VS Code (`.vsix`), Notepad++, Kate and Programmer's Notepad definitions |
| [Additional Scripts](Additional%20Scripts) | animation helper, and `m4cm_defines.py`, which regenerates the syntax highlighting from a Circuit Macros release |
| [legacy/m4cm.py](legacy/m4cm.py) | the classic script (version 3.3), which still uses m4, dpic and ImageMagick |

CI runs the tests on Windows, macOS and Linux against the latest pym4 and
pppic, and builds the example with TeX Live (the figures are kept as a build artifact).

## Licence

GPL-3.0-or-later; see [LICENSE](LICENSE). Circuit Macros and dpic are by
J. D. Aplevich.
