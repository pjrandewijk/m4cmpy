"""Circuits written with the m4cmpy.cm scripting facade.

Run from this folder:  python facade_example.py
Each drawing is saved as .m4cm source and rendered to PDF and PNG with m4cm.
"""

import m4cmpy.cm as cm

# --- 1. ex0.m4cm in Python: a source, a line reactance and a load
with cm.Drawing() as d:
    O = d.point("O", (0, 0))
    d.source("sinusoid", up=12.5, start=O, label=r"\mathbf{V}_s")
    d.inductor(None, 3, None, "dimen_/5", right=25, label="jX_s")
    d.ebox(down_to=O, label=r"\mathbf{Z}_l")  # down to the level of O
    d.line(end=O)
    d.dot()
    d.ground()
d.render("ex0_facade.m4cm", pdf=True, png=True, resolution=192)

# --- 2. Inverting amplifier, pyplot style; wires start from terminals and stay orthogonal
cm.new()
vin = cm.source("voltage", up=15, start=(0, 0), label="v_{in}")
r1 = cm.resistor(right=15, label="R_1")
amp = cm.opamp(at=r1.end, anchor="In1")
cm.line(up=12, start=r1.end)                   # feedback path above the forward path
cm.resistor(right_to=amp.Out, label="R_f")
cm.line(down_to=amp.Out)
cm.dot(r1.end)
cm.wire(amp.In2, vin.start, route="|-")        # non-inverting input to the reference
cm.ground(at=vin.start)
cm.line(right=8, start=amp.Out)
cm.dot()
cm.render("amplifier_facade.m4cm", pdf=True, png=True, resolution=192)

# --- 3. Single-line diagram elements (libSLD.m4 is included automatically)
with cm.Drawing() as d:
    bus = d.busbar(3, right=40, start=(0, 0), label=("B_1", None, None))  # label at the bus start
    d.sl_generator(None, "C", up=12, start=bus.P1, rlabel="G_1")
    d.sl_transformer({"type": "S"}, "C", None, "Y", "Delta", down=30, start=bus.P2, llabel="T_1")
    d.sl_load(None, "C", down=12, start=bus.P3, llabel="L_1")
d.render("sld_facade.m4cm", pdf=True, png=True, resolution=192)
