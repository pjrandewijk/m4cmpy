import io
import os
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest import mock

import m4cmpy
from m4cmpy import Converter, build_parser, default_include_dirs, main, pad_svg, ps_to_eps, wrap_template

CIRCUIT = """.PS
include(pstricks.m4)
scale=25.4
cct_init
O: (0,0)
Vs: source(up_ 12.5 from O,S); llabel(,\\mathbf{V}_s,)
L:  inductor(right_ 25,,3,,dimen_/5); llabel(,jX_s,)
Zl: ebox(down_ to (Here.x,O.y)); llabel(,\\mathbf{Z}_l,)
    line to O
    dot
    ground
.PE
"""


class WrapTemplateTests(unittest.TestCase):
    def test_current_and_legacy_marker_lines_are_replaced_by_the_picture(self):
        for marker in m4cmpy.MARKERS:
            with self.subTest(marker=marker):
                template = f"\\begin{{document}}\n  {marker} comment\n\\end{{document}}\n"
                result = wrap_template(template, "\\psline(0,0)(1,0)\n")
                self.assertEqual(result, "\\begin{document}\n\\psline(0,0)(1,0)\n\\end{document}\n")

    def test_missing_marker_is_reported(self):
        with self.assertRaisesRegex(ValueError, "pppic_output_here.*dpic_pstricks_output_here"):
            wrap_template("\\begin{document}\\end{document}\n", "x")


class EpsTests(unittest.TestCase):
    def test_bounding_box_offset_prolog_and_epilog(self):
        ps = "%!PS-Adobe-2.0\n%%BoundingBox: 0 0 596 842\n%%EndComments\nbody\n%%EOF\n"
        eps = ps_to_eps(ps, (10, 20, 30, 40), (10.5, 20.5, 30.5, 40.5), (1, 2, 3, 4)).splitlines()
        self.assertEqual(eps[0], "%!PS-Adobe-3.0 EPSF-3.0")
        self.assertEqual(eps[1], "%%BoundingBox: 9 18 33 44")
        self.assertEqual(eps[2], "%%HiResBoundingBox: 9.500000 18.500000 33.500000 44.500000")
        self.assertLess(eps.index("%%BeginProlog"), eps.index("%%EndComments"))
        self.assertEqual(eps[-5:], ["cleartomark", "countdictstack", "exch sub { end } repeat", "restore", "%%EOF"])


class SvgTests(unittest.TestCase):
    def test_canvas_grows_by_the_offset(self):
        svg = "<?xml version='1.0'?>\n<svg version='1.1' width='100pt' height='50pt' viewBox='10 -20 100 50'>\n</svg>"
        result = pad_svg(svg, (1, 2, 3, 4))
        self.assertIn("viewBox='9 -24 104 56'", result)
        self.assertIn("width='104pt'", result)
        self.assertIn("height='56pt'", result)


class OptionTests(unittest.TestCase):
    def test_m4cm_options_are_accepted(self):
        args = build_parser().parse_args(["-p", "-n", "-s", "-r", "192", "-b", "2", "2", "2", "2", "-a", "_x", "fig.m4cm"])
        self.assertTrue(args.PDF and args.PNG and args.SVG)
        self.assertEqual((args.resolution, tuple(args.BB_offset), args.append), (192, (2, 2, 2, 2), "_x"))
        self.assertEqual(build_parser().parse_args(["fig.m4cm", "-a"]).append, "")


class TemplateTests(unittest.TestCase):
    def test_built_in_template_is_used_when_no_default_ltx_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            cwd = os.getcwd()
            os.chdir(directory)
            try:
                src = Path(directory) / "fig.m4cm"
                template = Converter(build_parser().parse_args([str(src)])).template(src)
            finally:
                os.chdir(cwd)
        self.assertEqual(template.parent, Path(m4cmpy.__file__).resolve().parent)
        self.assertIn(m4cmpy.MARKER, template.read_text(encoding="utf-8"))

    def test_a_named_template_must_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "fig.m4cm"
            converter = Converter(build_parser().parse_args(["-t", "missing.ltx", str(src)]))
            self.assertIsNone(converter.template(src))


class CircuitMacrosSearchTests(unittest.TestCase):
    def test_get_cm_download_is_found_before_the_tex_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {"LOCALAPPDATA": directory, "XDG_CACHE_HOME": directory, "M4PATH": ""}
            with mock.patch.dict(os.environ, env):
                cached = m4cmpy.cache_dir() / "circuit_macros"
                cached.mkdir(parents=True)
                (cached / "libcct.m4").write_text("", encoding="utf-8")
                self.assertEqual(default_include_dirs(), [cached])

    def test_m4path_takes_over(self):
        with mock.patch.dict(os.environ, {"M4PATH": "somewhere"}):
            self.assertEqual(default_include_dirs(), [])

    def test_get_cm_tries_the_next_mirror_after_a_failure(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("circuit_macros/libcct.m4", "")
            z.writestr("circuit_macros/README", "Circuit_macros Version 11.1.3")
        responses = [urllib.error.URLError("certificate verify failed"), io.BytesIO(archive.getvalue())]
        with tempfile.TemporaryDirectory() as directory:
            env = {"LOCALAPPDATA": directory, "XDG_CACHE_HOME": directory}
            with mock.patch.dict(os.environ, env), mock.patch("urllib.request.urlopen", side_effect=responses):
                folder = m4cmpy.get_circuit_macros(("https://bad.example/cm.zip", "https://good.example/cm.zip"))
                self.assertTrue((folder / "libcct.m4").is_file())
                self.assertEqual(m4cmpy.cm_version(folder), "11.1.3")


def _converter(*options):
    return Converter(build_parser().parse_args([*options, "fig.m4cm"]))


@unittest.skipIf(_converter().circuit_macros() is None, "Circuit Macros not found (run m4cm --get-cm)")
class ToolchainTests(unittest.TestCase):
    def test_pym4_and_pppic_turn_a_circuit_into_pstricks(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "circuit.m4cm"
            src.write_text(CIRCUIT, encoding="utf-8")
            tex = _converter("-Q").pstricks(src)
        self.assertIsNotNone(tex)
        self.assertIn(r"\begin{pspicture}", tex)
        self.assertIn("pppic", tex)


@unittest.skipIf(_converter("-p", "-s").missing_tools() or _converter().circuit_macros() is None,
                 "LaTeX, dvips, Ghostscript, epstopdf, dvisvgm or Circuit Macros not found")
class EndToEndTests(unittest.TestCase):
    def test_pdf_png_svg_and_eps_are_written(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "circuit.m4cm").write_text(CIRCUIT, encoding="utf-8")
            code = main(["-Q", "-p", "-n", "-s", "-r", "96", "-o", str(root / "out"), str(root / "circuit.m4cm")])
            self.assertEqual(code, 0)
            for ext in ("pdf", "png", "svg", "eps"):
                self.assertGreater((root / "out" / f"circuit.{ext}").stat().st_size, 0, ext)


if __name__ == "__main__":
    unittest.main()
