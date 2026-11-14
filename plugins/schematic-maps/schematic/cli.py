"""The `schematic` command: read a plan, a panel and the layer files; draw, check and fingerprint a sheet.

    python3 -m schematic plan EXPORT.xml OUT.json [--section +Name] [--parts parts.json] [--z-range LO HI]
    python3 -m schematic panel TABLES.xml OUT.json [--numbers numbers.csv] [--lengths lengths.csv]
    python3 -m schematic signals TABLES.xml GRAPH.json NAME OUT.json --data DIR [--numbers ..] [--lengths ..]
    python3 -m schematic draw OUT.svg --data DIR GRAPH.json:NAME [GRAPH.json:NAME ...] [--no-preferences]
    python3 -m schematic report --data DIR GRAPH.json:NAME ...          rule checks and drawing faults
    python3 -m schematic fingerprint OUT.json --data DIR GRAPH.json:NAME ...
    python3 -m schematic check DRAWING.svg [--list]                     label faults in a finished SVG
"""
import argparse
import json
import sys

from . import fingerprint, label_check, layers, panel_reader, plan_reader, report, sheet, signal_reader
from .core import SchematicError
from .plan_reader import PlanError


def inputs(items):
    out = []
    for item in items:
        graph, _, name = item.rpartition(":")
        if not graph:
            raise SchematicError(f"{item}: write each input as GRAPH.json:NAME, NAME being the stem of its layer files")
        out.append((graph, name))
    return out


def csv_args(a):
    numbers = panel_reader.load_numbers(a.numbers) if a.numbers else None
    lengths = panel_reader.load_lengths(a.lengths) if a.lengths else None
    return numbers, lengths


def build(a):
    return sheet.build(inputs(a.inputs), a.data, preferences=not a.no_preferences, hints=a.with_hints)


def run(argv=None):
    ap = argparse.ArgumentParser(prog="schematic", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="AnyRail's JMRI export to a track graph")
    p.add_argument("export")
    p.add_argument("out")
    p.add_argument("--section", help='"+Name" keeps only sections named Name; "Name" leaves them out')
    p.add_argument("--parts", help="plan parts JSON, for switch numbers T<n> and heights")
    p.add_argument("--z-range", nargs=2, type=float, metavar=("LO", "HI"), help="use only parts in this height range")
    p.add_argument("--main-section", default="Mainline", help="section name that marks main track")

    p = sub.add_parser("panel", help="a Layout Editor panel to a track graph")
    p.add_argument("tables")
    p.add_argument("out")
    p.add_argument("--numbers")
    p.add_argument("--lengths")
    p.add_argument("--panel")

    p = sub.add_parser("signals", help="masts on the panel, as layer 1 signals")
    p.add_argument("tables")
    p.add_argument("graph")
    p.add_argument("name", help="stem of the plan overrides file in --data")
    p.add_argument("out")
    p.add_argument("--data", required=True)
    p.add_argument("--numbers")
    p.add_argument("--lengths")
    p.add_argument("--panel")

    for name, helptext in (("draw", "draw the sheet"), ("report", "rule checks and drawing faults"),
                           ("fingerprint", "the grid as JSON, for golden tests")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("out" if name != "report" else "--out", nargs=None if name != "report" else "?")
        p.add_argument("--data", required=True)
        p.add_argument("inputs", nargs="+", metavar="GRAPH.json:NAME")
        p.add_argument("--no-preferences", action="store_true", help="draw from layers 1 and 2 only")
        p.add_argument("--with-hints", action="store_true", help="comparison runs only: also read NAME.hints.json")

    p = sub.add_parser("check", help="label faults in a finished SVG")
    p.add_argument("svg")
    p.add_argument("--list", action="store_true")

    a = ap.parse_args(argv)
    try:
        if a.cmd == "plan":
            parts = json.load(open(a.parts)) if a.parts else None
            g = plan_reader.read(a.export, a.section, parts, tuple(a.z_range) if a.z_range else None, a.main_section)
            json.dump(g, open(a.out, "w"), indent=1)
            print("\n".join(g["notes"]))
        elif a.cmd == "panel":
            numbers, lengths = csv_args(a)
            g = panel_reader.read(a.tables, numbers, lengths, a.panel)
            json.dump(g, open(a.out, "w"), indent=1)
            print(len(g["nodes"]), "nodes", len(g["edges"]), "edges")
        elif a.cmd == "signals":
            numbers, lengths = csv_args(a)
            ov = layers.load(a.name, a.data, preferences=False)
            res = signal_reader.read(a.tables, json.load(open(a.graph)), ov, numbers, lengths, a.panel)
            signal_reader.write(a.out, res)
            kinds = {}
            for r in res["signals"]:
                kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
            print(len(res["signals"]), "masts placed", kinds, "|", len(res["unplaced"]), "problems")
            for x in res["unplaced"]:
                print("  ", x)
        elif a.cmd == "draw":
            s = build(a)
            s.write(a.out)
            print("\n".join(s.log))
            faults, text = label_check.report(a.out)
            print(text)
        elif a.cmd == "report":
            print(report.text(report.run(build(a))))
        elif a.cmd == "fingerprint":
            json.dump(fingerprint.of(build(a)), open(a.out, "w"), indent=1, sort_keys=True)
        elif a.cmd == "check":
            faults, text = label_check.report(a.svg, a.list)
            print(text)
            return 1 if faults else 0
    except (SchematicError, PlanError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0
