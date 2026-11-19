"""Small shared pieces of the layout engine: constants, track-name tidying, a switch's legs, local search."""


class SchematicError(ValueError):
    """The input cannot be drawn: the message names the switch, run or rule at fault."""


TAU = {"A": -1, "B": 1, "C": 1, "D": -1}
JUNCTION = ("switch", "dx")
TURN_SIGN = 1


def tidy(names):
    """Block names to track names: drop "Track ", and "S-4 East" when "S-4" is there too."""
    short = [n[6:] if n.startswith("Track ") else n for n in names]
    out = []
    for n in short:
        base = n.rsplit(" ", 1)[0] if n.endswith((" East", " West")) else n
        n = base if base in short else n
        if n not in out:
            out.append(n)
    return out



def node_ref(d):
    """How a track's end reads in a made-up block name: the switch number, "link X", "helix" or "end"."""
    if d["kind"] in ("switch", "dx") and d.get("label"):
        return d["label"]
    if d.get("sub") == "link" and d.get("label"):
        return "link " + d["label"]
    if d.get("sub") == "helix":
        return "helix"
    return "end"


def legs(nodes, n):
    """(upper strand, lower strand) of the frog side of switch n, in screen terms."""
    d = nodes[n]
    side = d["outs"] if d["sig"] == 1 else d["ins"]
    b, c = side["B"], side["C"]
    c_low = (d["hand"] == 1) == (d["sig"] == 1)
    return (b, c) if c_low else (c, b)


def dx_tracks(nodes, n):
    """Double crossover: ((upper in, upper out), (lower in, lower out))."""
    d = nodes[n]
    if d["sig"] == 1:
        ab, dc = (d["ins"]["A"], d["outs"]["B"]), (d["ins"]["D"], d["outs"]["C"])
    else:
        ab, dc = (d["ins"]["B"], d["outs"]["A"]), (d["ins"]["C"], d["outs"]["D"])
    return (ab, dc) if (d["hand"] == 1) == (d["sig"] == 1) else (dc, ab)


XOVER_ONE = "one"       # a double crossover's `corners` binding (CATS) or `xover_blocks` entry (Layout Editor): one block


def xover_names(d, n):
    """The default blocks of double crossover `n` (data `d`): a block per band leg, "OS <number>a" to "OS <number>d"
    (its OS block's name and the leg's letter), and "OS <number> X" for the middle of its X (CATS only; a Layout
    Editor double crossover has none). The Layout Editor and CATS panels name a double crossover's corners alike."""
    if d.get("kind") != "dx":
        raise SchematicError(f"switch {d.get('label') or n} is not a double crossover; only those have corners")
    base = f"OS {d.get('label') or n}"
    return {**{p: base + p.lower() for p in "ABCD"}, "X": base + " X"}



def descend(start, items, push, cost):
    """Local search: move one item a step, pushing whatever it would collide with; keep it if cheaper."""
    cur, best = start, cost(start)
    improved = True
    while improved:
        improved = False
        for it in items:
            for step in (1, -1):
                new = push(cur, it, step)
                c = cost(new)
                if c < best - 1e-9:
                    cur, best, improved = new, c, True
    return cur, best



def other_end(strands, sid, n):
    s = strands[sid]
    return s["src"][0] if s["dst"][0] == n else s["dst"][0]


def dedupe(pts):
    out = []
    for p in pts:
        if not out or abs(out[-1][0] - p[0]) > 0.01 or abs(out[-1][1] - p[1]) > 0.01:
            out.append(p)
    return out
