"""Generation rules that choose which leg of a switch runs level (R5 and R6) and the settings they use.

A switch has a common end (A, the points) and two legs, B (straight) and C (diverging). A drawn switch keeps
one leg level, on the row of its common end, and the other slopes to its own row. These rules say which leg
that is, from the track alone: no per-switch hint.

R5 Main level. Where the main route enters a switch by the common end and leaves by exactly one leg, that leg
   is level. Where the main uses both legs, the track is a loop: the leg the main enters the loop by is level
   and the return is drawn as a fold, so a loop's return (a fold half of a run longer than `long_track_cm`) is not pinned and the check does not count
   the return.
R6 Ladder. A ladder is a chain of two or more switches, each joined to the next by a short link (shorter
   than `ladder_link_max_cm`, default 40) from the same leg of each (all straight or all diverging) to the next
   switch's common end, whose other leg is a yard track: it runs to a track end or is longer than `long_track_cm` (default 100). The yard track leg of each ladder switch is level and the link slopes.
   The lead into the first switch runs straight into its common end, so the lead-side leg is level by
   construction. R5 wins where the two meet (a main link stays level).

R8 Straight level. Every other switch keeps its straight leg (B, the normal route) level and its diverging leg
   (C) sloped, so a switch off the main and outside a ladder is drawn as the part is built, not as the row search
   happens to pack it. R5 and R6 win where they apply. A switch with no leg B (a wye), a loop's entry (the main on
   both legs), a switch whose leg B is a loop's return or a crossover's diagonal (a short track to another switch's
   leg B or C), or one that a ladder switch's link leads to (it carries the ladder on) is left to the search.

All three are strong preferences, not pins. The row search keeps them unless breaking one makes the drawing tighter by
more than `rule_weight` (default 2.0, the price of two rows of slope): a short loop entered with the main sloped,
or a ladder whose link runs level, can draw in fewer rows than the rule allows. The report lists every switch where a
rule gave way. A `level_leg` preference (layer 3) is a hard pin and overrides both.
"""

DEFAULT_SETTINGS = dict(ladder_link_max_cm=40.0, long_track_cm=100.0, rule_weight=2.0)


def setting(opts, key):
    return (opts or {}).get(key, DEFAULT_SETTINGS[key])


def is_fold(sid):
    """A run that doubles back is cut in two at a turnback; each half has an id ending in .0 or .1."""
    return sid.endswith((".0", ".1"))


def is_loop_return(strands, sid, opts=None):
    """A fold half of a long run: the track of a loop, which the main goes round and comes back from."""
    return is_fold(sid) and strands[sid]["cm"] >= setting(opts, "long_track_cm")


def leg_strands(nodes, n):
    """{port: strand id} of a switch's legs."""
    d = nodes[n]
    return {p: (d["outs"].get(p) or d["ins"].get(p)) for p in "ABC" if d["outs"].get(p) or d["ins"].get(p)}


def main_pins(nodes, strands, opts=None):
    """R5: {switch node: level leg} for every switch where the main enters by A and leaves by one leg."""
    pins = {}
    for n, d in nodes.items():
        if d["kind"] != "switch":
            continue
        legs = leg_strands(nodes, n)
        if "A" not in legs or not strands[legs["A"]]["main"]:
            continue
        via = [p for p in "BC" if p in legs and strands[legs[p]]["main"]]
        if len(via) == 1 and not is_loop_return(strands, legs[via[0]], opts):
            pins[n] = via[0]
    return pins


def links(nodes, strands, opts):
    """Short strands from a leg (B or C) of one switch to the common end of another: {(switch, leg): next switch}."""
    top = setting(opts, "ladder_link_max_cm")
    out = {}
    for s in strands.values():
        (u, up), (v, vp) = s["src"], s["dst"]
        if nodes[u]["kind"] != "switch" or nodes[v]["kind"] != "switch" or s["cm"] >= top:
            continue
        if up in "BC" and vp == "A":
            out[(u, up)] = v
        elif vp in "BC" and up == "A":
            out[(v, vp)] = u
    return out


def is_yard_track(nodes, strands, n, sid, opts):
    """A yard track starts off the ladder: it runs to a track end, or is a long track."""
    s = strands[sid]
    far = s["dst"][0] if s["src"][0] == n else s["src"][0]
    return nodes[far]["kind"] == "end" or s["cm"] >= setting(opts, "long_track_cm")


def ladder_switches(band_or_nodes, opts=None, strands=None):
    """R6: {switch node: yard track leg} for every switch of a ladder: joined to a next switch by a short link on one
    leg while its other leg is a yard track, in a chain of two or more such switches that all link on the same leg (it
    links to one, or one links to it). A switch that stands alone, or whose neighbour links on the other leg, is no
    ladder."""
    if strands is None:
        nodes, strands = band_or_nodes["nodes"], band_or_nodes["strands"]
    else:
        nodes = band_or_nodes
    rungs = {}
    for (n, leg), nxt in links(nodes, strands, opts).items():
        legs = leg_strands(nodes, n)
        yard = "C" if leg == "B" else "B"
        if yard not in legs or strands[legs[leg]]["main"] or strands[legs[yard]]["main"]:
            continue                        # a main link or main yard track is R5's business
        if is_yard_track(nodes, strands, n, legs[yard], opts):
            rungs[n] = (leg, nxt)
    chained = {(leg, nxt) for leg, nxt in rungs.values()}
    return {n: "C" if leg == "B" else "B" for n, (leg, nxt) in rungs.items()
            if rungs.get(nxt, (None,))[0] == leg or (leg, n) in chained}


def crossover_leg(nodes, strands, n, sid, opts=None):
    """True when strand `sid` from switch `n` is a crossover's diagonal: a short track to a leg (B or C) of another
    switch, so it climbs from one parallel track to the other and cannot be level."""
    s = strands[sid]
    (u, up), (v, vp) = s["src"], s["dst"]
    other, port = (v, vp) if u == n else (u, up)
    return other != n and nodes[other]["kind"] == "switch" and port in "BC" \
        and s["cm"] < setting(opts, "ladder_link_max_cm")


def straight_pins(nodes, strands, opts=None):
    """R8: {switch node: "B"} for every switch with a straight leg B that is not a loop's return or a crossover's
    diagonal, and that is not the next switch of a ladder (reached by a ladder switch's link: it carries the ladder on,
    so the row search places its legs)."""
    ladder = ladder_switches(nodes, opts, strands)
    in_ladder = {nxt for (n, _leg), nxt in links(nodes, strands, opts).items() if n in ladder}
    pins = {}
    for n, d in nodes.items():
        if d["kind"] != "switch" or n in in_ladder:
            continue
        legs = leg_strands(nodes, n)
        if "A" not in legs or "B" not in legs or "C" not in legs or is_loop_return(strands, legs["B"], opts):
            continue
        if strands[legs["B"]]["main"] and strands[legs["C"]]["main"]:
            continue                        # a loop's entry: the main uses both legs, and R5 leaves it to the search
        if crossover_leg(nodes, strands, n, legs["B"], opts):
            continue                        # the straight leg is a crossover's diagonal
        pins[n] = "B"
    return pins


def level_legs(nodes, strands, opts):
    """The legs rules R5, R6 and R8 fix level, as {switch node: leg}. R8 is the default, R6 overrides it and R5 is
    applied last so it wins."""
    pins = straight_pins(nodes, strands, opts)
    pins.update(ladder_switches(nodes, opts, strands))
    pins.update(main_pins(nodes, strands, opts))
    return pins


def loop_returns(band, opts=None):
    """The fold halves that are a loop's return: (switch, leg) pairs the main check does not count."""
    nodes, strands = band["nodes"], band["strands"]
    out = set()
    for n in nodes:
        if nodes[n]["kind"] != "switch":
            continue
        for p, sid in leg_strands(nodes, n).items():
            if p in "BC" and is_loop_return(strands, sid, opts) and strands[sid]["main"]:
                out.add((n, p))
    return out
