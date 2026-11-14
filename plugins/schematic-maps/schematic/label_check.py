"""Label check: no label may overlap a drawn line, a symbol or another label.

Works on the finished SVG, so it judges what the reader sees, whatever placed the labels. It applies the
SVG transforms of every group (translate, scale, rotate with or without a centre, matrix), so lettering
inside a turned or scaled group is judged where it ends up.

Text boxes are measured with the bundled font metrics (metrics.py) and the text's letter-spacing; a box
runs from the cap height above the baseline to a small margin below it. Lines are the drawn path segments
widened by half their stroke. One fault per pair, naming both items.

    python3 -m schematic check drawing.svg [--list]
"""
import math
import re
import sys
import xml.etree.ElementTree as ET

from .metrics import text_width as _width

NS = "{http://www.w3.org/2000/svg}"
CAP, BELOW, PAD = 0.72, 0.06, 0.6                  # cap height and margin below the baseline (em); clearance (px)


def text_width(s, size, weight, spacing):
    return _width(s, size, weight, spacing)


def parse_transform(t):
    """An SVG transform list (translate, scale, rotate with or without a centre) as a matrix (a, b, c, d, e, f)."""
    m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for name, args in re.findall(r"(translate|scale|rotate|matrix)\(([^)]*)\)", t or ""):
        v = [float(x) for x in re.split(r"[ ,]+", args.strip()) if x]
        if name == "translate":
            step = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0.0)
        elif name == "matrix":
            step = tuple(v[:6])
        elif name == "scale":
            step = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        else:
            r = math.radians(v[0])
            c, s_ = math.cos(r), math.sin(r)
            cx, cy = (v[1], v[2]) if len(v) == 3 else (0.0, 0.0)
            step = (c, s_, -s_, c, cx - c * cx + s_ * cy, cy - s_ * cx - c * cy)
        m = compose(m, step)
    return m


def compose(outer, inner):
    a, b, c, d, e, f = outer
    A, B, C, D, E, F = inner
    return (a * A + c * B, b * A + d * B, a * C + c * D, b * C + d * D, a * E + c * F + e, b * E + d * F + f)


def _path_points(d):
    """The straight segments of a path made of M, L, m, l (and Z closing back) commands: [(start, end)]."""
    out, cur, first = [], None, None
    for cmd, args in re.findall(r"([MLmlZz])([^MLmlZz]*)", d):
        nums = [float(x) for x in re.findall(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?", args)]
        if cmd in "Zz":
            if cur is not None and first is not None and cur != first:
                out.append((cur, first))
                cur = first
            continue
        for i in range(0, len(nums) - 1, 2):
            p = (nums[i], nums[i + 1])
            if cmd in "ml" and cur is not None:
                p = (cur[0] + p[0], cur[1] + p[1])
            if cmd in "Ll" and cur is not None:
                out.append((cur, p))
            elif cmd in "Mm":
                first = p
                cmd = "L" if cmd == "M" else "l"
            cur = p
    return out


def walk(el, tf, out):
    tf = compose(tf, parse_transform(el.get("transform")))
    tag = el.tag.replace(NS, "")
    a_, b_, c_, d_, e_, f_ = tf
    s = math.sqrt(abs(a_ * d_ - b_ * c_))
    P = lambda x, y: (a_ * x + c_ * y + e_, b_ * x + d_ * y + f_)
    box = lambda x0, y0, x1, y1: (lambda q: (min(p[0] for p in q), min(p[1] for p in q),
                                              max(p[0] for p in q), max(p[1] for p in q)))(
        [P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)])
    if tag == "path":
        w = float(el.get("stroke-width", 1)) * s
        for p, q in _path_points(el.get("d", "")):
            out["lines"].append((P(*p), P(*q), w))
    elif tag in ("circle", "ellipse"):
        cx, cy = float(el.get("cx")), float(el.get("cy"))
        rx = float(el.get("r") or el.get("rx"))
        ry = float(el.get("r") or el.get("ry"))
        out["shapes"].append(("circle", box(cx - rx, cy - ry, cx + rx, cy + ry)))
    elif tag == "rect" and el.get("fill", "none") != "none":       # a filled box (helix box, title block) is a symbol
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        out["shapes"].append(("box", box(x, y, x + float(el.get("width")), y + float(el.get("height")))))
    elif tag == "text":
        size = float(el.get("font-size", 10))
        spacing = float(el.get("letter-spacing", 0))
        txt = "".join(el.itertext())
        w = text_width(txt, size, el.get("font-weight", "normal"), spacing)
        x, y = float(el.get("x")), float(el.get("y"))
        a = el.get("text-anchor", "start")
        x0 = x - (w / 2 if a == "middle" else w if a == "end" else 0)
        out["texts"].append((txt, box(x0, y - CAP * size, x0 + w, y + BELOW * size)))
    for c in el:
        walk(c, tf, out)


def seg_box_gap(a, b, box):
    """Distance from segment ab to an axis-aligned box (0 if they touch)."""
    x0, y0, x1, y1 = box
    if any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in (a, b)):
        return 0.0
    edges = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
    if any(_cross(a, b, c, d) for c, d in edges):
        return 0.0
    best = min(_pt_seg(p, a, b) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)))
    return min(best, *(_pt_seg(p, c, d) for p in (a, b) for c, d in edges))


def _pt_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _cross(a, b, c, d):
    o = lambda p, q, r: (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def boxes_overlap(p, q, pad=0.0):
    return p[0] < q[2] + pad and q[0] < p[2] + pad and p[1] < q[3] + pad and q[1] < p[3] + pad


def check(svg):
    """Label faults of a drawing, given as a file name or as the SVG text: ([(kind, text, other, box)], labels)."""
    out = {"lines": [], "shapes": [], "texts": []}
    root = ET.fromstring(svg) if str(svg).lstrip().startswith("<") else ET.parse(svg).getroot()
    walk(root, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0), out)
    lines = out["lines"]
    faults = []
    T = out["texts"]
    for i, (t, box) in enumerate(T):
        for a, b, w in lines:
            if seg_box_gap(a, b, box) < w / 2 + PAD:
                faults.append(("track", t, f"line {a[0]:.0f},{a[1]:.0f}-{b[0]:.0f},{b[1]:.0f}", box))
                break
        for kind, sb in out["shapes"]:
            inside = sb[0] <= box[0] and box[2] <= sb[2] and sb[1] <= box[1] and box[3] <= sb[3]
            if boxes_overlap(box, sb) and not inside:      # a letter inside its own circle is the symbol
                faults.append(("symbol", t, f"{kind} at {(sb[0] + sb[2]) / 2:.0f},{(sb[1] + sb[3]) / 2:.0f}", box))
        for u, ub in T[i + 1:]:
            if boxes_overlap(box, ub, PAD):
                faults.append(("label", t, u, box))
    return faults, len(T)


def report(svg, listing=False):
    faults, n = check(svg)
    kinds = {}
    for f in faults:
        kinds[f[0]] = kinds.get(f[0], 0) + 1
    lines = [f"{svg}: {n} labels, {len(faults)} label faults {kinds}"]
    if listing:
        for kind, t, other, box in faults:
            lines.append(f"  {kind:6} {t!r:28} vs {other}  at {box[0]:.0f},{box[1]:.0f}")
    return faults, "\n".join(lines)
