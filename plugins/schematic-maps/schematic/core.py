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
    base = f"OS {d.get('label') or n}"      # unlabelled: its node id, as the Layout Editor's OS blocks
    return {**{p: base + p.lower() for p in "ABCD"}, "X": base + " X"}


def switch_ref(d, n):
    """How a message names a switch: number/alias when it has an alias, else its number, else its node id."""
    label = d.get("label") or n
    return f"{label}/{d['alias']}" if d.get("alias") else str(label)


def other_names(bands, given):
    """{block name: what has it} for the names a panel's blocks other than double crossover corners take: `given`
    ({name: what}, the names the caller's names or bindings give), every switch's default OS block "OS <number>"
    and every track's name, so a default corner name can be checked against them (check_default_xovers)."""
    out = dict(given)
    for title, band, _ in bands:
        for n, d in sorted(band["nodes"].items()):
            if d["kind"] in JUNCTION:
                out.setdefault(f"OS {d.get('label') or n}", f"switch {switch_ref(d, n)}'s OS block on {title}")
        for s in band["strands"].values():
            if s.get("name"):
                out.setdefault(s["name"], f"track {s['name']} on {title}")
    return out


def check_default_xovers(bands, entries, taken, how):
    """Stop when a double crossover's default block (xover_names) is another block's name (`taken`, other_names) or
    another double crossover's default block. `entries`: [(band index, node, legs)] drawn with default names for
    those legs ("ABCD" and "X" keys); `how`: what names them instead (the error says to use it). Both panels check
    alike, so a Layout Editor and a CATS panel of one railroad give a crossover the same blocks or both stop."""
    owner = {}
    for bi, n, keys in sorted(entries):
        title, band, _ = bands[bi]
        d = band["nodes"][n]
        ref = f"double crossover {switch_ref(d, n)} on {title}"
        names = xover_names(d, n)
        for k in keys:
            name = names[k]
            if name in owner:
                raise SchematicError(f"{owner[name]} and {ref} would take the same default block {name}; name one's "
                                     f"corners in {how}")
            if name in taken:
                raise SchematicError(f"{ref}: its default block {name} is also the name of {taken[name]}; name its "
                                     f"corners in {how}")
            owner[name] = ref



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
