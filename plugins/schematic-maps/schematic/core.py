"""Small shared pieces of the layout engine: constants, track-name tidying, a switch's legs, local search."""
import re
from collections import defaultdict


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


HALF_LETTER = re.compile(r"(.*\d)([AB])")    # a crossover half's label: its number and one letter, A or B


def switch_number(label):
    """A switch label's number: the label less a trailing * (a switch with an added branch) and, after a digit, one
    trailing A or B, the letter the prototype gives each half of a crossover ("23A" and "23B" are switch 23)."""
    bare = (label or "").rstrip("*")
    m = HALF_LETTER.fullmatch(bare)
    return m.group(1) if m else bare


def crossover_name(label):
    """How a single crossover is named (shown on a panel, listed in preferences) from either half's label: the
    number of halves lettered A and B, else the label the two halves share."""
    return switch_number(label) if HALF_LETTER.fullmatch((label or "").rstrip("*")) else label


def through_leg(link):
    """A single crossover half's normal (closed) leg: its leg B or C that is not its link to the other half."""
    return {"B": "C", "C": "B"}[link]


def crossover_halves(nodes, strands, log=None):
    """{switch node: (link leg, other half, strand id)} of every single crossover: two switches of one number joined
    directly by one track, which is the crossover's diagonal and each half's link (thrown) leg; the half's other leg B
    or C is its normal (closed) route, on its through track (through_leg). Two pairings:

      - leg C to leg C, as before 0.1.42: two switches labelled alike, or lettered one A and one B (switch_number);
      - leg B to leg C: only halves lettered one A and one B (a half laid with its straight route on the diagonal).

    Leg B to leg B is two switches back to back on one through track, and a points (leg A) joins no crossover: those
    stay two switches, as before. Lettered halves are not paired, and `log` (a list, when given) says why, when they
    are joined by more than one track (a run-around: two switches), when their labels are ambiguous (two A's, or a
    lettered half and an unlettered switch of its number), when more than two lettered switches carry their number,
    or when a half would pair with two switches. Nothing here stops a run: a plan that drew before still draws."""
    say = log.append if log is not None else (lambda _m: None)
    label = {n: (d.get("label") or "").rstrip("*") for n, d in nodes.items() if d["kind"] == "switch"}
    lettered = defaultdict(set)         # number -> its lettered switches
    for n, lab in label.items():
        if HALF_LETTER.fullmatch(lab):
            lettered[switch_number(lab)].add(n)
    joins = defaultdict(list)           # (u, v) in track order of the first -> [(strand id, u's leg, v's leg)]
    for sid, s in sorted(strands.items()):
        (u, pu), (v, pv) = s["src"], s["dst"]
        if u != v and u in label and v in label:
            key = (u, v) if (v, u) not in joins else (v, u)
            joins[key].append((sid, pu, pv) if key == (u, v) else (sid, pv, pu))
    found = defaultdict(list)           # node -> [(link leg, other node, strand id)]
    for (u, v), tracks in joins.items():
        lu, lv = label[u], label[v]
        num = switch_number(lu)
        if not lu or not lv or num != switch_number(lv):
            continue
        what = f"switches {nodes[u].get('label')} and {nodes[v].get('label')}"
        lettered_pair = {lu, lv} == {num + "A", num + "B"}
        if lu == lv:            # labelled alike: leg C to leg C, as before
            got = [t for t in tracks if t[1:] == ("C", "C")]
            if lu != num and not got and any(set(t[1:]) == {"B", "C"} for t in tracks):
                say(f"{what} are both lettered {lu[-1]}, so they are not paired as a single crossover")
        elif not lettered_pair:
            if any(set(t[1:]) <= {"B", "C"} for t in tracks):
                say(f"{what} share number {num} but are not lettered one A and one B, so they are not paired as a "
                    "single crossover")
            continue
        elif len(tracks) > 1:
            say(f"{what} are joined by {len(tracks)} tracks (a run-around or passing track), so they are two "
                "switches, not a single crossover")
            continue
        else:
            got = [t for t in tracks if t[1:] in (("C", "C"), ("B", "C"), ("C", "B"))]
            if got and len(lettered[num]) > 2:
                say(f"{what}: {len(lettered[num])} switches carry letters of number {num}, so none is paired as a "
                    "single crossover")
                continue
        for sid, pu, pv in got:
            found[u].append((pu, v, sid))
            found[v].append((pv, u, sid))
    out = {}
    for n, links in sorted(found.items()):
        if len(links) > 1:
            say(f"switch {nodes[n].get('label')} would pair with "
                f"{' and '.join(nodes[o].get('label') for _p, o, _s in links)}, so it is no single crossover's half")
            continue
        out[n] = links[0]
    return {n: got for n, got in out.items() if out.get(got[1], (None, None))[1] == n}


def crossover_notes(nodes, halves):
    """Log lines for the field, one per single crossover half (`halves`, crossover_halves) joined by its leg B: the
    half is laid with its own straight route on the diagonal, so with Closed lining both through tracks its machine
    must be wired reversed."""
    return [f"switch {nodes[n].get('label')} is laid straight on the crossover's diagonal: wire its machine reversed "
            "so Closed lines the through route" for n, (link, _o, _s) in sorted(halves.items()) if link == "B"]


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
