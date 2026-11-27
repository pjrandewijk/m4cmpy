import tempfile
import unittest
from pathlib import Path

import m4cmpy.cm as cm
from m4cmpy import Converter, build_parser
from m4cmpy.cm import Drawing, Expr, Pos


def body(drawing: Drawing) -> list[str]:
    """The statements of a drawing, without the .PS header and .PE."""
    lines = drawing.to_m4().splitlines()
    return lines[lines.index("cct_init") + 2:-1]


def ex0() -> Drawing:
    """Examples/ex0.m4cm, written with the facade."""
    d = Drawing()
    O = d.point("O", (0, 0))
    d.source("sinusoid", up=12.5, start=O, label=r"\mathbf{V}_s")
    d.inductor(None, 3, None, "dimen_/5", right=25, label="jX_s")
    d.ebox(down_to=O, label=r"\mathbf{Z}_l")
    d.line(end=O)
    d.dot()
    d.ground()
    return d


class SourceTextTests(unittest.TestCase):
    def test_ex0_is_reproduced(self):
        self.assertEqual(body(ex0()), [
            "O: (0,0)",
            r"source(up_ 12.5 from O,S); llabel(,\mathbf{V}_s)",
            "inductor(right_ 25,,3,,dimen_/5); llabel(,jX_s)",
            r"ebox(down_ to (Here.x,O.y)); llabel(,\mathbf{Z}_l)",
            "line to O",
            "dot",
            "ground",
        ])

    def test_header_follows_the_unit_and_libraries(self):
        self.assertIn("scale=25.4", Drawing().to_m4())
        self.assertIn("scale=2.54", Drawing(unit="cm").to_m4())
        self.assertNotIn("scale", Drawing(unit="in").to_m4())
        self.assertIn("include(libSLD.m4)", Drawing(libraries=["libSLD.m4"]).to_m4())
        with self.assertRaises(ValueError):
            Drawing(unit="furlong")


class PlacementTests(unittest.TestCase):
    def spec(self, **place) -> str:
        d = Drawing()
        d.resistor(**place)
        return body(d)[0]

    def test_relative_directions(self):
        self.assertEqual(self.spec(), "resistor")
        self.assertEqual(self.spec(up=True), "resistor(up_)")
        self.assertEqual(self.spec(left=7.5), "resistor(left_ 7.5)")
        self.assertEqual(self.spec(dir="down", length=10), "resistor(down_ 10)")
        self.assertEqual(self.spec(dir="R"), "resistor(right_)")
        self.assertEqual(self.spec(length=10), "resistor(to Here+vec_(10,0))")

    def test_angles(self):
        self.assertEqual(self.spec(dir=30, length=10), "resistor(to Here+(Rect_(10,30)))")
        self.assertEqual(self.spec(dir=-45, start=(1, 2)), "resistor(to (1,2)+(Rect_(elen_,-45)) from (1,2))")

    def test_coordinates_and_terminals(self):
        self.assertEqual(self.spec(start=(0, 0), end=(0, 12.5)), "resistor(from (0,0) to (0,12.5))")
        self.assertEqual(self.spec(up=10, start="P"), "resistor(up_ 10 from P)")

    def test_direction_until_a_level(self):
        self.assertEqual(self.spec(down_to=Pos("O")), "resistor(down_ to (Here.x,O.y))")
        self.assertEqual(self.spec(right_to=25), "resistor(right_ to (25,Here.y))")
        self.assertEqual(self.spec(up_to=(3, 4), start=(1, 0)), "resistor(up_ to (1,4) from (1,0))")

    def test_conflicting_placement_is_refused(self):
        for place in ({"up": 1, "dir": "down"}, {"down_to": 1, "end": (0, 0)}, {"dir": "sideways"},
                      {"dir": 30, "end": (1, 1)}, {"up_to": 1, "left_to": 2}):
            with self.subTest(place=place), self.assertRaises(ValueError):
                self.spec(**place)

    def test_unknown_keyword_is_refused(self):
        with self.assertRaisesRegex(TypeError, "colour"):
            Drawing().resistor(colour="red")


class ElementTests(unittest.TestCase):
    def test_aliases_and_codes(self):
        d = Drawing()
        d.source("current", reversed=True)
        d.source("AC")
        d.consource("voltage")
        d.ground(kind="european", dir="up")
        self.assertEqual(body(d), ["source(,I,,R)", "source(,AC)", "consource(,V)", "ground(,,E,U)"])

    def test_names_are_given_only_when_a_terminal_is_used(self):
        d = Drawing()
        r = d.resistor(right=10)
        c = d.capacitor(down=5)
        d.line(end=r.start)
        self.assertEqual(body(d), ["R1: resistor(right_ 10)", "capacitor(down_ 5)", "line to R1.start"])
        self.assertEqual((str(c.center), c.name), ("C1.c", "C1"))

    def test_user_names_are_checked_and_skipped_by_automatic_names(self):
        d = Drawing()
        d.resistor(name="R1")
        self.assertEqual(d.resistor().name, "R2")
        for bad in ("R1", "r3", "3R"):
            with self.subTest(name=bad), self.assertRaises(ValueError):
                d.resistor(name=bad)

    def test_block_points_and_typos(self):
        d = Drawing()
        a = d.opamp(at=(5, 5), anchor="In1", name="A", lead=0)
        self.assertEqual((str(a.Out), str(a.ne)), ("A.Out", "A.ne"))
        self.assertEqual(body(d), ["A: opamp with .In1 at (5,5)"])
        with self.assertRaises(AttributeError):
            a.lable("x")

    def test_opamp_pins_are_lead_ends(self):
        d = Drawing()
        a = d.opamp(dir="up", lead=3, at=(5, 5), anchor="In1")
        self.assertEqual([str(p) for p in (a.inv, a.noninv, a.out, a.N)], ["A1.In1", "A1.In2", "A1.Out", "A1.N"])
        text = "\n".join(body(d))
        self.assertTrue(text.startswith("A1: [ Body: opamp(up_)\n  pinlen = 3\n"), text)
        self.assertIn("In1: Body.In1+(-pinlen*(Body.E.x-Body.W.x)/axlen,", text)
        self.assertIn("Out: Body.Out+(pinlen*(Body.E.x-Body.W.x)/axlen,", text)
        self.assertIn("line from Body.Out to Out", text)
        self.assertTrue(text.endswith("E2: Body.E2 ] with .In1 at (5,5)"), text)
        self.assertNotIn("V1", text)
        self.assertIn("V1: Body.V1", Drawing().opamp(chars="P")._body)

    def test_labels(self):
        d = Drawing()
        d.resistor(rlabel=("+", "v", "-")).label("R", side="c")
        self.assertEqual(body(d), ["resistor; rlabel(+,v,-); clabel(,R)"])

    def test_m4_quoting(self):
        d = Drawing()
        d.resistor(label="i_{a,b}")
        d.resistor(label="f(x")
        self.assertEqual(body(d), ["resistor; llabel(,`i_{a,b}')", "resistor; llabel(,`f(x')"])
        with self.assertRaises(ValueError):
            d.resistor(label="v', w")

    def test_key_value_arguments(self):
        d = Drawing()
        d.ebox({"lgth": 8, "text": '"Z"'})
        self.assertEqual(body(d), ['ebox(,lgth=8; text="Z")'])


class WireTests(unittest.TestCase):
    def test_orthogonal_routes(self):
        d = Drawing()
        a, b = Pos("A"), Pos("B")
        d.wire(a, b)
        d.wire(a, b, route="|-", dot=True)
        d.wire(a, b, route="-")
        d.wire(a, b, via=[(1, 2)])
        self.assertEqual(body(d), [
            "line from A to (B.x,A.y) then to B",
            "line from A to (A.x,B.y) then to B",
            "dot(at A)",
            "dot(at B)",
            "line from A to (B.x,A.y)",
            "line from A to (1,2) then to B",
        ])

    def test_lines_and_moves(self):
        d = Drawing()
        d.line((0, 0), (1, 0), (1, 1))
        d.line(up=5, arrow=True)
        d.move(right=2)
        self.assertEqual(body(d), ["line from (0,0) to (1,0) then to (1,1)", "arrow up_ 5", "move right_ 2"])


class ExpressionTests(unittest.TestCase):
    def test_positions(self):
        self.assertEqual(str(Pos("V1.end").x), "V1.end.x")
        self.assertEqual(str(Pos.of((1, 2)).y), "2")
        self.assertEqual(str((Pos("A") + (1, 0)).x), "(A+(1,0)).x")
        self.assertEqual(str(Pos("A").between("B", 0.25)), "0.25 between A and B")
        with self.assertRaises(TypeError):
            Pos.of(Drawing().resistor())

    def test_variables_and_arithmetic(self):
        d = Drawing()
        dx = d.var("dx", 12.5)
        d.resistor(right=2 * dx + 1)
        self.assertEqual(body(d), ["dx = 12.5", "resistor(right_ ((2*dx)+1))"])
        self.assertEqual(str(-Expr("a") / 2), "((-a)/2)")


class PyplotStyleTests(unittest.TestCase):
    def test_module_functions_use_the_current_drawing(self):
        d = cm.new()
        cm.resistor(right=5)
        with Drawing() as inner:
            cm.capacitor()
        self.assertIs(cm.gcd(), d)
        self.assertEqual((body(d), body(inner)), (["resistor(right_ 5)"], ["capacitor"]))

    def test_sld_methods_include_libsld(self):
        d = Drawing()
        bus = d.busbar(3, right=40)
        d.sl_generator(up=10, start=bus.P1)
        self.assertIn("include(libSLD.m4)", d.to_m4())
        self.assertEqual(body(d), ["Bus1: sl_busbar(right_ 40,3)", "sl_generator(up_ 10 from Bus1.P1)"])

    def test_transformer_labels_go_around_its_body(self):
        d = Drawing()
        d.sl_transformer(down=20, llabel="T_1")
        d.sl_transformer({"name": "Tx"}, label="T_2")
        d.resistor(label="R").label("x", side="r", block="Blk")
        self.assertEqual(body(d), ["sl_transformer(down_ 20); llabel(,T_1,,,Body)",
                                   "sl_transformer(,name=Tx); llabel(,T_2,,,Tx)",
                                   "resistor; llabel(,R); rlabel(,x,,,Blk)"])


def _circuit_macros_found() -> bool:
    return Converter(build_parser().parse_args(["x"])).circuit_macros() is not None


@unittest.skipUnless(_circuit_macros_found(), "Circuit Macros not found (run m4cm --get-cm)")
class FacadeToolchainTests(unittest.TestCase):
    def test_generated_source_compiles_to_pstricks(self):
        d = ex0()
        bus = d.busbar(2, right=30, start=(40, 20))
        d.sl_transformer(None, "C", down=15, start=bus.P1)
        a = d.opamp(at=(60, 0), anchor="In1")
        d.wire(bus.P2, a.In2, route="|-")
        with tempfile.TemporaryDirectory() as directory:
            src = d.save(Path(directory) / "facade.m4cm")
            tex = Converter(build_parser().parse_args(["-Q", str(src)])).pstricks(src)
        self.assertIsNotNone(tex)
        self.assertIn(r"\begin{pspicture}", tex)


_tools_missing = Converter(build_parser().parse_args(["-p", "x"])).missing_tools()


@unittest.skipIf(_tools_missing or not _circuit_macros_found(), "LaTeX, Ghostscript or Circuit Macros not found")
class FacadeRenderTests(unittest.TestCase):
    def test_render_writes_the_requested_files(self):
        with tempfile.TemporaryDirectory() as directory:
            files = ex0().render(Path(directory) / "ex0.m4cm", pdf=True)
            self.assertEqual([f.suffix for f in files], [".eps", ".pdf"])
            for f in files:
                self.assertGreater(f.stat().st_size, 0, f)


if __name__ == "__main__":
    unittest.main()
