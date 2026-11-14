"""Fingerprints: a drawing's grid as plain JSON, to keep as a golden and compare switch by switch.

For every band: each switch's column, row, facing (which way its points face) and level leg; each track's row
and column span (or "slope" for a link drawn on a diagonal); each connector's letter and the track it ends.
Columns count from the band's leftmost junction, rows from its top row. Nothing in it depends on the style
(fonts, colours, widths), so a change of look leaves a golden alone.

    fp = fingerprint.of(sheet)
    fingerprint.diff(golden, fp)        # [] when equal, else one line per difference
"""
from . import report


def _name(nodes, n):
    d = nodes[n]
    if d["kind"] == "end":
        return "end" + (":" + d["label"] if d.get("label") else "")
    return d.get("label") or n


def _switch_keys(nodes):
    """A label per switch; a label shared by the two halves of a crossover takes the plan part as a suffix."""
    labels = [d["label"] for d in nodes.values() if d["kind"] in ("switch", "dx")]
    keys = {}
    for n, d in nodes.items():
        if d["kind"] in ("switch", "dx"):
            dup = labels.count(d["label"]) > 1
            keys[n] = f"{d['label']}({d.get('alias') or n})" if dup else d["label"]
    return keys


def band(title, b):
    nodes, strands, R, x = b["nodes"], b["strands"], b["R"], b["x"]
    srow, nrow, diag = R["srow"], R["nrow"], R["diag"]
    x0 = min(x.values())
    r0 = min(srow.values())
    keys = _switch_keys(nodes)
    legs = report.leg_rows(b)
    switches = {}
    for n, k in keys.items():
        d = nodes[n]
        entry = dict(col=x[n] - x0, row=nrow[n] - r0 if n in nrow else None, facing="right" if d["sig"] == 1 else "left")
        if d["kind"] == "switch":
            level = [p for p in "BC" if p in legs[n] and not legs[n][p][1]]
            entry["level_leg"] = level[0] if len(level) == 1 else ("".join(level) or "none")
        switches[k] = entry
    tracks, connectors = {}, {}
    for sid, s in strands.items():
        (u, up), (v, vp) = s["src"], s["dst"]
        key = f"{keys.get(u) or _name(nodes, u)}.{up}-{keys.get(v) or _name(nodes, v)}.{vp}"
        if sid in diag:
            tracks[key] = dict(row="slope", cols=[x[u] - x0, x[v] - x0], name=s["name"])
        else:
            su, sv, _ = b["need"][sid]
            tracks[key] = dict(row=srow[sid] - r0, cols=[x[u] + su - x0, x[v] - sv - x0], name=s["name"])
        for n, p in ((u, up), (v, vp)):
            if nodes[n].get("sub") == "link":
                other = v if n == u else u
                connectors[nodes[n]["label"]] = dict(to=nodes[n].get("to", ""), track=key, at=keys.get(other) or _name(nodes, other))
    return dict(title=title, switches=switches, tracks=tracks, connectors=connectors,
                size=[max(x.values()) - x0, max(srow.values()) - r0 + 1])


def of(sheet):
    """{band title: band fingerprint} for a built sheet."""
    return {title: band(title, b) for title, b, _ in sheet.bands}


def diff(golden, actual, limit=60):
    """Differences between two fingerprints, one line each, switch by switch; [] when they agree."""
    out = []
    for title in sorted(set(golden) | set(actual)):
        if title not in actual:
            out.append(f"{title}: band missing")
            continue
        if title not in golden:
            out.append(f"{title}: band not in the golden")
            continue
        g, a = golden[title], actual[title]
        for section, noun in (("switches", "switch"), ("tracks", "track"), ("connectors", "connector")):
            for key in sorted(set(g[section]) | set(a[section])):
                if key not in a[section]:
                    out.append(f"{title}: {noun} {key} is gone")
                elif key not in g[section]:
                    out.append(f"{title}: {noun} {key} is new")
                else:
                    changes = [f"{f} {g[section][key].get(f)} -> {a[section][key].get(f)}"
                               for f in sorted(set(g[section][key]) | set(a[section][key]))
                               if g[section][key].get(f) != a[section][key].get(f)]
                    if changes:
                        out.append(f"{title}: {noun} {key}: " + ", ".join(changes))
        if g["size"] != a["size"]:
            out.append(f"{title}: size {g['size']} -> {a['size']}")
    if len(out) > limit:
        out = out[:limit] + [f"... and {len(out) - limit} more"]
    return out
