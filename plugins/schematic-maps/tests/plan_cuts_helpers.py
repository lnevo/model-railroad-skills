"""Small plan-XML builders shared by the plan reader tests."""


def seg(ident, a, ta, b, tb):
    return (f'<tracksegment ident="{ident}" connect1name="{a}" type1="{ta}" connect2name="{b}" type2="{tb}" '
            'blockname="B_1_Mainline" dashed="no" mainline="yes" hidden="no"/>')


def bumper(ident, x, y):
    return f'<positionablepoint ident="{ident}" type="END_BUMPER" x="{x}" y="{y}" connect1name="s"/>'


def panel(*parts):
    return '<layout-config><LayoutEditor name="t">' + "".join(parts) + "</LayoutEditor></layout-config>"
