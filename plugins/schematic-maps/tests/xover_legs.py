"""A made-up railroad for single crossovers whose halves join by leg B or C (tests/test_xover_legs.py).

Two parallel tracks, North and South, each from a west end to an east end, and two single crossovers between them:

  - 3 (halves 3A on North and 3B on South), the usual build: joined leg C to leg C, each half's straight leg B on
    its through track;
  - 5 (halves 5A on North and 5B on South), joined 5A's leg C to 5B's leg B: 5B is laid with its straight route on
    the crossover's diagonal, so its leg A starts along the diagonal and its through track runs on from its leg C.

The graph is in the plan reader's form (plan_reader.read), coordinates in plan units, y down. `graph(labels)`
relabels the halves.
"""
import math

ANGLE = math.radians(14.0)          # the diagonal's angle to the through tracks
COS, SIN = math.cos(ANGLE), math.sin(ANGLE)
GAP = 60.0                          # North to South


def graph(labels=None):
    """The plan graph: {"nodes", "edges"}. `labels` relabels nodes ({node: label})."""
    labels = labels or {}
    nodes, edges = {}, []

    def switch(n, label, xy, dirs, hand):
        nodes[n] = dict(kind="switch", label=labels.get(n, label), alias=n, xy=list(xy), district="Test", hand=hand,
                        dirs={k: list(v) for k, v in dirs.items()}, z=0.0)

    def end(n, xy):
        nodes[n] = dict(kind="end", label="", xy=list(xy), district="Test", z=0.0)

    def track(u, up, v, vp, cm, name, main):
        edges.append(dict(id=f"e{len(edges)}", u=u, up=up, v=v, vp=vp, names=[name] if name else [], cm=cm,
                          link=False, main=main, district="Test", hidden=False))

    east, west = (1.0, 0.0), (-1.0, 0.0)
    down, up = (COS, SIN), (-COS, -SIN)             # along the diagonal, down to the east and back up
    run = GAP / SIN * COS
    end("END:WN", (0, 0))
    end("END:WS", (0, GAP))
    end("END:EN", (1600, 0))
    end("END:ES", (1600, GAP))
    switch("X3A", "3A", (300, 0), {"A": west, "B": east, "C": down}, 1)
    switch("X3B", "3B", (300 + run, GAP), {"A": east, "B": west, "C": up}, 1)
    switch("X5A", "5A", (900, 0), {"A": west, "B": east, "C": down}, 1)
    switch("X5B", "5B", (900 + run, GAP), {"A": down, "B": up, "C": west}, -1)
    track("END:WN", "E", "X3A", "A", 300.0, "North", True)
    track("X3A", "B", "X5A", "A", 600.0, "North", True)
    track("X5A", "B", "END:EN", "E", 700.0, "North", True)
    track("END:WS", "E", "X3B", "B", 540.0, "South", False)
    track("X3A", "C", "X3B", "C", 62.0, "", False)
    track("X3B", "A", "X5B", "C", 500.0, "South", False)
    track("X5A", "C", "X5B", "B", 62.0, "", False)
    track("X5B", "A", "END:ES", "E", 400.0, "South", False)
    return dict(nodes=nodes, edges=edges)


_built = {}


def bands(labels=None):
    """The solved bands of graph(labels) (sheet.build, no layer files), built once per labels; a copy each call."""
    import copy
    import tempfile

    from schematic import sheet
    key = repr(sorted((labels or {}).items()))
    if key not in _built:
        with tempfile.TemporaryDirectory() as data:
            _built[key] = sheet.build([(graph(labels), "xo")], data).bands
    return copy.deepcopy(_built[key])
