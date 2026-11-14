"""Report: the checks that run every time on a drawn sheet (specification "Checks run every time").

  1. every switch, leg and run of the track graph appears once in the grid (`coverage`)
  2. no two drawn lines cross or lie on top of each other unless they cross on the layout (`faults`)
  3. R5: the main is level through every switch on it; R6: yard tracks are level in every ladder
  4. every switch the edits add or move has a source (`edits.apply_edits` refuses one without)
  5. no label overlaps a line, a symbol or another label (label_check, on the finished SVG)

The R5 and R6 checks read the drawn rows, not the rule that chose them, so they hold a hint-set or
preference-set drawing to the same standard.
"""
from . import layout, rules


def tag(nodes, n):
    d = nodes[n]
    lab = d.get("label") or ("end" if d["kind"] == "end" else d["kind"])
    return f"{lab} ({d['alias']})" if d.get("alias") and d["alias"] != lab else lab


def leg_rows(band):
    """For each switch: {port: (strand id, drawn sloped at this switch)}."""
    nodes, R = band["nodes"], band["R"]
    srow, nrow, diag = R["srow"], R["nrow"], R["diag"]
    out = {}
    for n, d in nodes.items():
        if d["kind"] != "switch":
            continue
        legs = {}
        for p in "ABC":
            sid = d["outs"].get(p) or d["ins"].get(p)
            if sid is not None:
                legs[p] = (sid, sid in diag or srow[sid] != nrow[n])
        out[n] = legs
    return out


def analyse(band, opts=None, strict=False):
    """{"faults": drawing faults, "main": R5 findings, "ladder": R6 findings, "coverage": check 1 findings}.

    `strict` also counts the loop cases the rule exempts (the return leg of a loop, a switch with main on
    both legs), which is how the stage 0 spike counted; it is for comparing old and new runs."""
    opts = opts or {}
    nodes, strands = band["nodes"], band["strands"]
    found = {"faults": layout.check(band), "main": [], "ladder": [], "coverage": coverage(band)}
    exempt = set() if strict else rules.loop_returns(band, opts)
    ladders = rules.ladder_switches(band, opts)
    for n, legs in leg_rows(band).items():
        s = {p: strands[sid] for p, (sid, _) in legs.items()}
        if "A" in s and s["A"]["main"]:
            via = [p for p in "BC" if p in s and s[p]["main"]]
            if len(via) == 1 and legs[via[0]][1] and (n, via[0]) not in exempt:
                other = "C" if via[0] == "B" else "B"
                found["main"].append((tag(nodes, n), f"main enters the common end and leaves by leg {via[0]}, which is drawn "
                                      f"sloped (the level leg is {other}, {s[other]['name'] or 'unnamed'})"))
            elif len(via) == 2 and (strict or all(legs[p][1] for p in via)):
                found["main"].append((tag(nodes, n), "main on all three legs (a loop)" if strict
                                      else "main on both legs and neither is level"))
        elif "A" in s and not s["A"]["main"]:
            via = [p for p in "BC" if p in s and s[p]["main"]]
            if via:
                found["main"].append((tag(nodes, n), f"main on leg {via[0]} but not on the common end"))
        if n in ladders:
            yard = ladders[n]
            if legs[yard][1]:
                found["ladder"].append((tag(nodes, n), f"yard track {s[yard]['name'] or 'leg ' + yard} "
                                        f"({s[yard]['cm']:.0f} cm) is drawn sloped; the link is level"))
    for sid in band["R"]["diag"]:
        if strands[sid]["main"]:
            u, v = strands[sid]["src"][0], strands[sid]["dst"][0]
            found["main"].append((f"{tag(nodes, u)} to {tag(nodes, v)}", "main strand drawn as a diagonal"))
    return found


def coverage(band):
    """Check 1: every switch and every strand of the graph is drawn exactly once (a position for each)."""
    nodes, strands, R = band["nodes"], band["strands"], band["R"]
    missing = []
    for sid in strands:
        if sid not in R["diag"] and sid not in R["srow"]:
            missing.append(f"run {sid} has no row")
    for n, d in nodes.items():
        if d["kind"] in ("switch", "end") and n not in R["nrow"]:
            missing.append(f"{d.get('label') or n} has no row")
        if n not in band["x"]:
            missing.append(f"{d.get('label') or n} has no column")
    return missing


def run(sheet, strict=False):
    """{band title: analysis} for a built sheet."""
    return {title: analyse(band, opts, strict) for title, band, opts in sheet.bands}


def counts(res):
    """Totals over every band: crossings, main not level, ladder not level, coverage."""
    return {k: sum(len(f[k]) for f in res.values()) for k in ("faults", "main", "ladder", "coverage")}


def text(res):
    lines = []
    for title, f in res.items():
        lines.append(f"== {title}")
        lines.append(f"  drawing faults (crossings, overlaps): {len(f['faults'])}")
        lines += [f"    {x}" for x in f["faults"]]
        lines.append(f"  R5 main not level: {len(f['main'])}")
        lines += [f"    {a}: {b}" for a, b in f["main"]]
        lines.append(f"  R6 ladder, yard track not level: {len(f['ladder'])}")
        lines += [f"    {a}: {b}" for a, b in f["ladder"]]
        if f["coverage"]:
            lines.append(f"  not drawn: {len(f['coverage'])}")
            lines += [f"    {x}" for x in f["coverage"]]
    t = counts(res)
    lines.append(f"total: crossings {t['faults']}, main not level {t['main']}, ladder not level {t['ladder']}")
    return "\n".join(lines)
