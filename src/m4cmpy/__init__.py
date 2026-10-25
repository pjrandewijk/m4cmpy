# m4cmpy - standalone figures from M4 Circuit Macros files
# Copyright (C) 2026 Peter Jan Randewijk
# SPDX-License-Identifier: GPL-3.0-or-later
"""m4cmpy: standalone EPS/PDF/PNG/JPG/SVG figures from M4 Circuit Macros files.

Works like the classic m4cm.py, but needs only Python and a TeX distribution such
as MiKTeX: m4 and dpic are replaced by pym4 and pppic, PNG/JPG come from
Ghostscript (MiKTeX's mgs.exe) instead of ImageMagick, and SVG comes from dvisvgm.
"""

from __future__ import annotations

import argparse
import glob
import http.client
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from pppic import PicCompiler, PicError
from pym4 import M4Error, M4Lite, read_source

__version__ = "4.0.0"
MARKER = "%pppic_output_here%"
LEGACY_MARKER = "%dpic_pstricks_output_here%"
MARKERS = (MARKER, LEGACY_MARKER)
DEFAULT_TEMPLATE = "default.ltx"
CTAN_URL = "https://mirrors.ctan.org/graphics/circuit_macros.zip"
# the redirector picks a mirror per request and some mirrors fail TLS checks: retry it, then use DANTE's ctan.net
CTAN_URLS = (CTAN_URL, CTAN_URL, "https://ctan.net/graphics/circuit_macros.zip")


# ------------------------------------------------------------------ helpers


def wrap_template(template: str, pstricks: str) -> str:
    """Replace a recognized marker line with the generated PSTricks picture."""
    lines = template.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if any(marker in line for marker in MARKERS):
            return "".join(lines[:i]) + pstricks.rstrip("\n") + "\n" + "".join(lines[i + 1:])
    raise ValueError("the template is missing a picture marker: " + " or ".join(MARKERS))


def ps_to_eps(ps: str, bbox: tuple[int, int, int, int], hires: tuple[float, float, float, float],
              offset: tuple[int, int, int, int]) -> str:
    """Turn dvips output into an EPS file with a tight, offset bounding box (m4cm.py method)."""
    left, bottom, right, top = offset
    lines = ps.splitlines(keepends=True)
    lines[0] = "%!PS-Adobe-3.0 EPSF-3.0\n"
    for i, line in enumerate(lines):
        if line.startswith("%%BoundingBox:"):
            lines[i] = (f"%%BoundingBox: {bbox[0] - left} {bbox[1] - bottom} {bbox[2] + right} {bbox[3] + top}\n"
                        f"%%HiResBoundingBox: {hires[0] - left:.6f} {hires[1] - bottom:.6f} "
                        f"{hires[2] + right:.6f} {hires[3] + top:.6f}\n")
        elif line.startswith("%%EndComments"):
            lines.insert(i, "%%BeginProlog\nsave\ncountdictstack\nmark\nnewpath\n/showpage {} def\n"
                            "/setpagedevice {pop} def\n%%EndProlog\n%%Page 1 1\n")
            break
    end = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].startswith("%%EOF")), len(lines))
    lines.insert(end, "cleartomark\ncountdictstack\nexch sub { end } repeat\nrestore\n")
    return "".join(lines)


def pad_svg(svg: str, offset: tuple[int, int, int, int]) -> str:
    """Grow the SVG canvas by the bounding-box offset (in bp) on each side."""
    left, bottom, right, top = offset
    tag = re.search(r"<svg\b[^>]*>", svg)
    if not tag:
        return svg
    root = tag.group(0)
    box = re.search(r"viewBox=(['\"])([^'\"]+)\1", root)
    if not box:
        return svg
    x, y, w, h = (float(v) for v in box.group(2).replace(",", " ").split())
    x, y, w, h = x - left, y - top, w + left + right, h + top + bottom
    fmt = lambda v: f"{v:.6f}".rstrip("0").rstrip(".")  # noqa: E731
    q = box.group(1)
    new = root.replace(box.group(0), f"viewBox={q}{fmt(x)} {fmt(y)} {fmt(w)} {fmt(h)}{q}")
    new = re.sub(r"\bwidth=(['\"])[^'\"]*\1", f"width={q}{fmt(w)}pt{q}", new, count=1)
    new = re.sub(r"\bheight=(['\"])[^'\"]*\1", f"height={q}{fmt(h)}pt{q}", new, count=1)
    return svg[:tag.start()] + new + svg[tag.end():]


def cache_dir() -> Path:
    """Per-user folder that holds the Circuit Macros downloaded by --get-cm."""
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        root = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(root) / "m4cmpy"


def cm_version(folder: Path) -> str:
    readme = folder / "README"
    match = re.search(r"Version\s+([\d.]+)", readme.read_text(errors="replace")) if readme.is_file() else None
    return match.group(1) if match else "?"


def get_circuit_macros(urls: tuple[str, ...] = CTAN_URLS) -> Path:
    """Download Circuit Macros from CTAN into cache_dir() and return its folder."""
    errors = []
    for url in urls:
        request = urllib.request.Request(url, headers={"User-Agent": f"m4cmpy/{__version__}"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                archive = zipfile.ZipFile(io.BytesIO(response.read()))
            break
        except (OSError, http.client.HTTPException, zipfile.BadZipFile) as error:
            errors.append(f"{url}: {error}")
    else:
        raise RuntimeError("; ".join(errors))
    cache = cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / "circuit_macros"
    with tempfile.TemporaryDirectory(dir=cache) as tmp:
        # zipfile drops absolute paths and ".." from member names
        with archive:
            archive.extractall(tmp)
        lib = next(Path(tmp).rglob("libcct.m4"), None)
        if lib is None:
            raise RuntimeError(f"{url} does not contain libcct.m4")
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(lib.parent), str(target))
    return target


def default_include_dirs(tools: Tools | None = None) -> list[Path]:
    """Circuit Macros when M4PATH is not set: the --get-cm download, else the TeX tree (kpsewhich)."""
    if os.environ.get("M4PATH"):
        return []
    cached = cache_dir() / "circuit_macros"
    if (cached / "libcct.m4").is_file():
        return [cached]
    kpsewhich = tools.find("kpsewhich") if tools else None
    if kpsewhich:
        r = subprocess.run([kpsewhich, "libcct.m4"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if r.returncode == 0 and r.stdout.strip():
            return [Path(r.stdout.strip()).parent]
    return []


class Tools:
    """Locate the TeX and Ghostscript programs (MiKTeX does not need to be on PATH)."""

    def __init__(self, tex_bin: str | None) -> None:
        self.dirs = [Path(tex_bin)] if tex_bin else []
        self.defaults = [Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "MiKTeX" / "miktex" / "bin" / "x64",
                         Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64"]
        self.latex = self.find("latex")
        self.dvips = self.find("dvips")
        self.epstopdf = self.find("epstopdf")
        self.dvisvgm = self.find("dvisvgm")
        self.gs = self.find("mgs", "gswin64c", "gswin32c", "gs")

    def find(self, *names: str) -> str | None:
        for name in names:
            for d in self.dirs:
                for candidate in (d / f"{name}.exe", d / name):
                    if candidate.is_file():
                        return str(candidate)
            hit = shutil.which(name)
            if hit:
                return hit
            for d in self.defaults:
                if (d / f"{name}.exe").is_file():
                    return str(d / f"{name}.exe")
        return None


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    # stdin must be closed: TeX tools otherwise wait for input on errors or bad options
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, errors="replace",
                          stdin=subprocess.DEVNULL)


def latex_errors(log: Path) -> list[str]:
    if not log.is_file():
        return []
    lines = log.read_text(errors="replace").splitlines()
    out = []
    for i, line in enumerate(lines):
        if line.startswith("!"):
            out.extend(lines[i:i + 3])
    return out[:12]


# ------------------------------------------------------------------ pipeline


class Converter:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.tools = Tools(args.tex_bin)
        self.dirs = [Path(d) for d in args.include] + default_include_dirs(self.tools)

    def circuit_macros(self) -> Path | None:
        m4path = [Path(p) for p in os.environ.get("M4PATH", "").split(os.pathsep) if p]
        return next((d for d in self.dirs + m4path if (d / "libcct.m4").is_file()), None)

    def say(self, text: str) -> None:
        if not self.args.SUPER_QUIET:
            print(text)

    def note(self, text: str) -> None:
        if not (self.args.QUIET or self.args.SUPER_QUIET):
            print(text)

    @staticmethod
    def fail(text: str) -> bool:
        print(text, file=sys.stderr)
        return False

    def pstricks(self, src: Path) -> str | None:
        self.say("m4cm -> pic")
        m4 = M4Lite(self.dirs)
        m4.base_dir = src.parent
        try:
            pic = m4.run([(read_source(src), str(src))])
        except M4Error as error:
            self.fail(f"m4: {error}")
            return None
        for warning in m4.warnings:
            self.note(warning)
        self.say("pic -> pstricks")
        compiler = PicCompiler(base_dir=src.parent, include_dirs=self.dirs)
        try:
            tex = compiler.compile(pic)
        except PicError as error:
            self.fail(f"pic: {error}")
            return None
        for message in compiler.messages + compiler.warnings:
            self.note(f"pic: {message}")
        if compiler.errors:
            for error in compiler.errors[:10]:
                self.fail(f"pic: {error}")
            return None
        return tex

    def template(self, src: Path) -> Path | None:
        name = Path(self.args.template)
        for candidate in (name, src.parent / name):
            if candidate.is_file():
                return candidate.resolve()
        if self.args.template == DEFAULT_TEMPLATE:
            return Path(__file__).resolve().parent / DEFAULT_TEMPLATE
        return None

    def convert(self, src: Path) -> bool:
        a = self.args
        started = time.monotonic()
        self.say(f"\nProcessing: {src}")
        template = self.template(src)
        if template is None:
            return self.fail(f"LATEX_TEMPLATE_FILE, {a.template}, could not be found...")
        tex = self.pstricks(src)
        if tex is None:
            return False
        out = Path(a.output_dir) if a.output_dir else src.parent
        out.mkdir(parents=True, exist_ok=True)
        stem = src.stem + a.append
        self.say(f"wrapping {stem}.tex with {template.name}")
        try:
            document = wrap_template(read_source(template).replace("\r\n", "\n"), tex)
        except ValueError as error:
            return self.fail(str(error))
        # TeX runs in a local temp folder: synced folders such as OneDrive slow every step down
        with tempfile.TemporaryDirectory(prefix="m4cm_") as tmp:
            work = Path(tmp)
            (work / f"{stem}.ltx").write_text(document, encoding="utf-8", newline="\n")
            searched = os.pathsep.join(str(d) for d in (template.parent, src.parent.resolve(), out.resolve()))
            env = dict(os.environ, TEXINPUTS=searched + os.pathsep + os.environ.get("TEXINPUTS", ""))
            products = self.build(work, stem, env)
            keep = products if products is not None else [work / f"{stem}{ext}" for ext in (".ltx", ".log")]
            for path in keep:
                if path.is_file():
                    shutil.copyfile(path, out / path.name)
        if products is None:
            return False
        self.say(f"Done! ({time.monotonic() - started:.1f} s)")
        return True

    def latex(self, work: Path, stem: str, env: dict) -> subprocess.CompletedProcess:
        cmd = [self.tools.latex, "-interaction=nonstopmode", "-halt-on-error", f"{stem}.ltx"]
        if "miktex" in self.tools.latex.lower():
            # MiKTeX's package-installer check costs seconds per run; retry with it only if a file is missing
            r = run([cmd[0], "--disable-installer", *cmd[1:]], work, env)
            log = work / f"{stem}.log"
            if r.returncode == 0 or not (log.is_file() and "not found" in log.read_text(errors="replace")):
                return r
        return run(cmd, work, env)

    def build(self, work: Path, stem: str, env: dict) -> list[Path] | None:
        a = self.args
        offset = tuple(a.BB_offset)
        self.say("pstricks -> dvi")
        r = self.latex(work, stem, env)
        if r.returncode or not (work / f"{stem}.dvi").is_file():
            for line in latex_errors(work / f"{stem}.log") or r.stdout.splitlines()[-12:]:
                print(line, file=sys.stderr)
            self.fail(f"LaTeX found errors in {stem}.ltx (the .ltx and .log are kept in the output folder)")
            return None
        products = []
        if a.SVG:
            self.say("dvi -> svg")
            fonts = ["--font-format=woff2"] if a.SVG_FONTS else ["--no-fonts"]
            r = run([self.tools.dvisvgm, "--exact-bbox", *fonts, "-o", f"{stem}.svg", f"{stem}.dvi"], work, env)
            svg = work / f"{stem}.svg"
            if r.returncode or not svg.is_file():
                self.fail(f"dvisvgm failed: {(r.stdout + r.stderr).strip()[-400:]}")
                return None
            svg.write_bytes(pad_svg(svg.read_bytes().decode("utf-8"), offset).encode("utf-8"))
            products.append(svg)

        self.say("dvi -> ps")
        r = run([self.tools.dvips, "-j0", "-G0", "-Ppdf", "-Pdownload35", "-q", f"{stem}.dvi", "-o", f"{stem}.ps"], work, env)
        if r.returncode or not (work / f"{stem}.ps").is_file():
            self.fail(f"dvips failed: {(r.stdout + r.stderr).strip()[-400:]}")
            return None
        self.say("ps -> eps")
        r = run([self.tools.gs, "-dBATCH", "-dNOPAUSE", "-dALLOWPSTRANSPARENCY", "-sDEVICE=bbox", f"{stem}.ps"], work)
        bb = re.search(r"%%BoundingBox:\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)", r.stderr)
        hr = re.search(r"%%HiResBoundingBox:\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", r.stderr)
        if not (bb and hr):
            self.fail(f"Ghostscript could not find the bounding box: {r.stderr.strip()[-400:]}")
            return None
        ps = (work / f"{stem}.ps").read_bytes().decode("latin-1")
        eps = work / f"{stem}.eps"
        eps.write_bytes(ps_to_eps(ps, tuple(int(v) for v in bb.groups()), tuple(float(v) for v in hr.groups()),
                                  offset).encode("latin-1"))

        raster = {"png": ("pngalpha", []), "jpg": ("jpeg", ["-dJPEGQ=75"])}
        for ext, wanted in (("png", a.PNG), ("jpg", a.JPG)):
            if wanted:
                self.say(f"eps -> {ext}")
                device, extra = raster[ext]
                r = run([self.tools.gs, "-dQUIET", "-dBATCH", "-dNOPAUSE", "-dSAFER", "-dEPSCrop", "-dALLOWPSTRANSPARENCY",
                         "-dGraphicsAlphaBits=4", "-dTextAlphaBits=4", f"-sDEVICE={device}", f"-r{a.resolution}", *extra,
                         f"-sOutputFile={stem}.{ext}", f"{stem}.eps"], work)
                if r.returncode:
                    self.fail(f"Ghostscript failed: {(r.stdout + r.stderr).strip()[-400:]}")
                    return None
                products.append(work / f"{stem}.{ext}")
        if a.PDF:
            self.say("eps -> pdf")
            r = run([self.tools.epstopdf, f"{stem}.eps"], work, env)
            if r.returncode or not (work / f"{stem}.pdf").is_file():
                self.fail(f"epstopdf failed: {(r.stdout + r.stderr).strip()[-400:]}")
                return None
            products.append(work / f"{stem}.pdf")
        if not (a.DELETE_EPS and (a.PNG or a.JPG or a.PDF or a.SVG)):
            products.append(eps)
        return products

    def missing_tools(self) -> list[str]:
        needed = {"latex": self.tools.latex, "dvips": self.tools.dvips, "Ghostscript (mgs/gswin64c)": self.tools.gs}
        if self.args.PDF:
            needed["epstopdf"] = self.tools.epstopdf
        if self.args.SVG:
            needed["dvisvgm"] = self.tools.dvisvgm
        return [name for name, path in needed.items() if not path]


# ------------------------------------------------------------------ command line


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="m4cm",
        description="Create standalone EPS/PDF/PNG/JPG/SVG figures from M4 Circuit Macros files, "
                    "using only Python and a TeX distribution (no m4, dpic or ImageMagick).",
        epilog='Instead of "M4CM_FILE", it is also possible to use "*.m4cm" to compile all the ".m4cm" files in the '
               'current folder. Circuit Macros is searched in the -I folders, M4PATH, the --get-cm download, '
               'and the TeX tree (kpsewhich).')
    p.add_argument("-a", "--append", dest="append", nargs="?", metavar="APPEND_CHARS", default="", const="",
                   help="Character/String to append to the end of the output file(s)")
    p.add_argument("-b", "--boundingbox_offset", dest="BB_offset", type=int, nargs=4, metavar=("L", "B", "R", "T"),
                   default=(1, 1, 1, 1), help="BoundingBox offset in points: left bottom right top (default: 1 1 1 1)")
    p.add_argument("-d", "--delete_eps", action="store_true", dest="DELETE_EPS",
                   help="delete EPS file after converting to PNG, JPG, PDF or SVG")
    p.add_argument("-e", "--eps", action="store_true", dest="EPS", default=True, help="convert to EPS format [default option]")
    p.add_argument("-g", "--ghostscript", action="store_true", dest="GS",
                   help="accepted for compatibility; PNG/JPG always use Ghostscript")
    p.add_argument("-j", "--jpg", action="store_true", dest="JPG", help="convert to JPG format")
    p.add_argument("-n", "--png", action="store_true", dest="PNG", help="convert to PNG format (transparent background)")
    p.add_argument("-o", "--output_dir", dest="output_dir", nargs="?", metavar="OUTPUT_DIR", default="", const="",
                   help="the Output Directory for the EPS/PDF/PNG/JPG/SVG output files")
    p.add_argument("-p", "--pdf", action="store_true", dest="PDF", help="convert to PDF format")
    p.add_argument("-q", "--quiet", action="store_true", dest="QUIET", help="run quietly, but print progress")
    p.add_argument("-Q", "--super_quiet", action="store_true", dest="SUPER_QUIET", help="run quietly with no output")
    p.add_argument("-r", "--resolution", dest="resolution", type=int, nargs="?", metavar="PNG_RESOLUTION",
                   default=600, const=600,
                   help="PNG or JPG resolution in dpi (default 600; 192 suits web pages)")
    p.add_argument("-s", "--svg", action="store_true", dest="SVG", help="convert to SVG format (text as outlines)")
    p.add_argument("--svg-fonts", action="store_true", dest="SVG_FONTS",
                   help="with --svg: embed WOFF2 fonts instead of outlines, so text stays selectable")
    p.add_argument("-t", "--template", dest="template", nargs="?", metavar="LATEX_TEMPLATE_FILE",
                   default=DEFAULT_TEMPLATE, const=DEFAULT_TEMPLATE,
                   help='LaTeX template file (default "default.ltx", looked up in the current folder, then next to '
                        'the input, else the built-in one)')
    p.add_argument("-I", "--include", action="append", default=[], metavar="DIR",
                   help="extra folder to search for m4 include files (may be repeated)")
    p.add_argument("--get-cm", action="store_true", dest="GET_CM",
                   help=f"download the latest Circuit Macros from CTAN into {cache_dir() / 'circuit_macros'}")
    p.add_argument("--tex-bin", metavar="DIR", help="folder with latex/dvips/dvisvgm/mgs (default: PATH, then MiKTeX)")
    p.add_argument("-v", "--version", action="version", version=f"Version: %(prog)s {__version__}")
    p.add_argument("m4cmFile", nargs="*", metavar="M4CM_FILE", help="M4CM file(s) to be compiled")
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.GET_CM:
        try:
            folder = get_circuit_macros()
        except (OSError, RuntimeError, zipfile.BadZipFile) as error:
            print(f"Could not download Circuit Macros: {error}", file=sys.stderr)
            return 2
        print(f"Circuit Macros {cm_version(folder)} installed in {folder}")
        if not args.m4cmFile:
            return 0
    if not args.m4cmFile:
        parser.print_help()
        return 0
    converter = Converter(args)
    missing = converter.missing_tools()
    if missing:
        print("Could not find: " + ", ".join(missing) + ". Install MiKTeX or use --tex-bin.", file=sys.stderr)
        return 2
    if converter.circuit_macros() is None:
        print("Could not find Circuit Macros (libcct.m4): run 'm4cm --get-cm', set M4PATH, or use -I.",
              file=sys.stderr)
        return 2
    files = []
    for pattern in args.m4cmFile:
        files += sorted(glob.glob(pattern)) if any(c in pattern for c in "*?") else [pattern]
    failures = 0
    for name in files:
        src = Path(name)
        if not src.is_file():
            print(f"{name} was not found...?", file=sys.stderr)
            failures += 1
        elif not converter.convert(src):
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
