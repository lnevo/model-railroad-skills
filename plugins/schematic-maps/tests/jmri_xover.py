"""How JMRI 5.16 loads a Layout Editor crossover from the panel XML, for the tests: a port of the coordinate setters
and getters of jmri.jmrit.display.layoutEditor.LayoutTurnoutView and the load order of
configurexml.LayoutTurnoutViewXml.

The view's own `version` field is never set from the XML (LayoutTurnoutView keeps 1 whatever `ver` says), so every
crossover is held as a centre and two displacements (dispA, dispB), and each setter reshapes the parallelogram:
A = c - dispA, B = c + dispB, C = c + dispA, D = c - dispB. The loader calls setCoordsA only when ver is 2, then
setCoordsB and setCoordsC, then setCoordsD when ver is 2.

`diagonals` ports what draw1 draws for the crossed-over route: a single crossover's diagonal from the middle of
A-B through the centre to the middle of C-D; a double crossover's four from 5/8 of the way from each end to the
middle of its side (pAM, pBM, pCM, pDM: MathUtil.lerp(pA, pABM, 5.0 / 8.0)) to the centre, not from its corners."""
import math

L_DEFAULT, S_DEFAULT, W_DEFAULT = 30.0, 10.0, 10.0      # LayoutEditor's xOverLong, xOverShort, xOverHWid defaults


def jdiv(n, d):
    """Java double division (infinity or NaN on a zero divisor)."""
    if d == 0:
        if n == 0 or math.isnan(n):
            return math.nan
        return math.copysign(math.inf, n) * math.copysign(1.0, d)
    return n / d


def _foot(a_num, a_den, x, y, sign):
    """(xi, yi): JMRI's foot point for the parallelogram adjustment."""
    b = sign * y
    xi, yi = 0.0, b
    if a_den != 0.0:
        a = jdiv(a_num, a_den)
        b = sign * y + a * x if sign < 0 else y - a * x
        xi = jdiv(-b, a + jdiv(1.0, a))
        yi = a * xi + b
    return xi, yi


class View:
    def __init__(self, ttype, centre):
        self.t, self.c = ttype, centre
        if ttype == "RH_XOVER":
            self.dispB, self.dispA = (S_DEFAULT, -W_DEFAULT), (L_DEFAULT, W_DEFAULT)
        elif ttype == "LH_XOVER":
            self.dispB, self.dispA = (L_DEFAULT, -W_DEFAULT), (S_DEFAULT, W_DEFAULT)
        else:                                   # DOUBLE_XOVER
            self.dispB, self.dispA = (L_DEFAULT, -W_DEFAULT), (L_DEFAULT, W_DEFAULT)

    def _scale(self, d, length):
        old = math.hypot(*d)
        return (d[0] * length / old, d[1] * length / old)

    def set_a(self, p):
        x, y = self.c[0] - p[0], self.c[1] - p[1]
        if self.t == "DOUBLE_XOVER":
            self.dispA = (x, y)
            self.dispB = self._scale(self.dispB, math.hypot(x, y))
            return
        self.dispA = (x, y)
        b = -y
        xi, yi = 0.0, b
        if self.dispB[0] + x != 0.0:
            a = jdiv(self.dispB[1] + y, self.dispB[0] + x)
            b = -y + a * x
            xi = jdiv(-b, a + jdiv(1.0, a))
            yi = a * xi + b
        k = 0.333333 if self.t == "RH_XOVER" else 3.0
        self.dispB = (xi - k * (-x - xi), yi - k * (-y - yi))

    def set_b(self, p):
        x, y = self.c[0] - p[0], self.c[1] - p[1]
        self.dispB = (-x, -y)
        if self.t == "DOUBLE_XOVER":
            self.dispA = self._scale(self.dispA, math.hypot(x, y))
            return
        b = y
        xi, yi = 0.0, b
        if self.dispA[0] - x != 0.0:
            if -self.dispA[0] + x == 0:
                x = x - 0.0000000001
            a = jdiv(self.dispA[1] - y, self.dispA[0] - x)
            b = y - a * x
            xi = jdiv(-b, a + jdiv(1.0, a))
            yi = a * xi + b
        k = 0.333333 if self.t == "LH_XOVER" else 3.0
        self.dispA = (xi - k * (x - xi), yi - k * (y - yi))

    def set_c(self, p):
        x, y = self.c[0] - p[0], self.c[1] - p[1]
        self.dispA = (-x, -y)
        if self.t == "DOUBLE_XOVER":
            self.dispB = self._scale(self.dispB, math.hypot(x, y))
            return
        b = -y
        xi, yi = 0.0, b
        if self.dispB[0] + x != 0.0:
            if -self.dispB[0] + x == 0:
                x = x - 0.0000000001
            a = jdiv(-self.dispB[1] + y, -self.dispB[0] + x)
            b = -y + a * x
            xi = jdiv(-b, a + jdiv(1.0, a))
            yi = a * xi + b
        k = 0.333333 if self.t == "RH_XOVER" else 3.0
        self.dispB = (-(xi - k * (-x - xi)), -(yi - k * (-y - yi)))

    def set_d(self, p):
        x, y = self.c[0] - p[0], self.c[1] - p[1]
        self.dispB = (x, y)
        if self.t == "DOUBLE_XOVER":
            self.dispA = self._scale(self.dispA, math.hypot(x, y))
            return
        b = y
        xi, yi = 0.0, b
        if self.dispA[0] + x != 0.0:
            a = jdiv(self.dispA[1] + y, self.dispA[0] + x)
            b = -y + a * x
            xi = jdiv(-b, a + jdiv(1.0, a))
            yi = a * xi + b
        k = 0.333333 if self.t == "LH_XOVER" else 3.0
        self.dispA = (xi - k * (-x - xi), yi - k * (-y - yi))

    def points(self):
        c, a, b = self.c, self.dispA, self.dispB
        return {"A": (c[0] - a[0], c[1] - a[1]), "B": (c[0] + b[0], c[1] + b[1]),
                "C": (c[0] + a[0], c[1] + a[1]), "D": (c[0] - b[0], c[1] - b[1])}


def load(el):
    """{leg: (x, y)} of a <layoutturnout> crossover element as JMRI 5.16 holds it once loaded."""
    v = View(el.get("type"), (float(el.get("xcen")), float(el.get("ycen"))))
    pt = lambda k: (float(el.get("x" + k)), float(el.get("y" + k)))      # noqa: E731
    ver = int(el.get("ver") or 1)
    if ver == 2:
        v.set_a(pt("a"))
    v.set_b(pt("b"))
    v.set_c(pt("c"))
    if ver == 2:
        v.set_d(pt("d"))
    return v.points()


def slant(points):
    """"\\" when JMRI's diagonal (the middle of A-B to the middle of D-C) drops to the right on screen, else "/"."""
    top = ((points["A"][0] + points["B"][0]) / 2, (points["A"][1] + points["B"][1]) / 2)
    bot = ((points["C"][0] + points["D"][0]) / 2, (points["C"][1] + points["D"][1]) / 2)
    return "\\" if (bot[0] - top[0]) * (bot[1] - top[1]) > 0 else "/"


def diagonals(ttype, points, centre):
    """[(from, to)] of the diagonal lines JMRI 5.16 draws (LayoutTurnoutView.draw1) for a loaded crossover."""
    lerp = lambda p, q, t: (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)     # noqa: E731
    ab = lerp(points["A"], points["B"], 0.5)
    cd = lerp(points["C"], points["D"], 0.5)
    if ttype == "DOUBLE_XOVER":
        return [(lerp(points[k], ab if k in "AB" else cd, 5.0 / 8.0), centre) for k in "ABCD"]
    return [(ab, centre), (centre, cd)]


def angle(segment):
    """Degrees from the horizontal of a drawn line."""
    (x0, y0), (x1, y1) = segment
    return math.degrees(math.atan2(abs(y1 - y0), abs(x1 - x0)))
