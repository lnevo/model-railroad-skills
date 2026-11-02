"""Settle the gates only a build can decide, by reading a real JMRI build of the same files.

The gate port reports not_checked for four things the builder decides as it goes: quick service
and aggressive pulls that free room (E9), how many other cars take a stop's moves (D3), how much
of the train other cars fill (D9, G10), and an AUTO locomotive count in a departure staging track
(A8). When JMRI is installed, one dry run builds every enabled train on a copy of the files; the
answer for each car is what that build did. The run is cached by the content of the files, so a
second question about the same plan costs nothing. Without JMRI the gates stay not_checked.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


SOURCE = "real JMRI build"
ALONE = "real JMRI build of this train alone"
# ops_jmri and ops_store import the gates, so they load on first use.
_cache: dict[str, list[dict]] = {}


def available() -> bool:
    import ops_jmri
    return ops_jmri.jmri_home() is not None


def _digest(directory: Path) -> str:
    from ops_store import FILES
    h = hashlib.sha1()
    for name in FILES:
        path = Path(directory) / name
        if path.is_file():
            h.update(name.encode() + b"\0" + path.read_bytes())
    return h.hexdigest()


RUNS = 4  # The builder draws at random, so one build proves little. Same default as ops_build_check.


def real_build(directory: Path, only: str | None = None, runs: int = RUNS) -> list[dict]:
    """Build every enabled train, RUNS times on copies, nothing terminated. Cached per file content.

    only: build just that train, with no other train built first (the answer when another train takes a
    car in the full session)."""
    import ops_jmri
    from concurrent.futures import ThreadPoolExecutor
    key = _digest(directory) + (f"|{only}" if only else "") + f"|{runs}"
    if key not in _cache:
        if len(_cache) > 24:
            _cache.clear()
        job = {"build": True, **({"only": [only]} if only else {})}
        with ThreadPoolExecutor(max_workers=min(runs, 4)) as pool:
            _cache[key] = list(pool.map(lambda _: ops_jmri.run_worker(Path(directory), job), range(runs)))
    return _cache[key]


def forget() -> None:
    _cache.clear()


def _note(gate: dict, status: str, reason: str, source: str = SOURCE) -> dict:
    out = {k: v for k, v in gate.items() if k not in ("settle", "fix")}
    out.update(status=status, reason=f"{gate['reason']} -- {reason}", source=source)
    if status != "pass" and "fix" in gate:
        out["fix"] = gate["fix"]
    return out


def _refusals(row: dict, car) -> list[tuple[str, str]]:
    """The gate and line the build report gives for each refusal of this car, read by ops_report."""
    import ops_report
    text = row.get("report_text", "")
    if not text:
        return []
    try:
        story = ops_report.explain(text, car=f"{car.road} {car.number}", detail="normal").get("story")
    except Exception:
        return []
    found = []
    for attempt in (story or {}).get("attempts", []):
        for line in attempt.get("refused", []):
            code = line.rsplit("(", 1)[-1].rstrip(")")
            found.append((code, line))
    return found


def settle_gates(rr, gates_obj, car, train, target, gates: list[dict], result: dict,
                 source: str = SOURCE) -> list[dict]:
    """Replace each open gate with the answer the real build gives, saying which source answered.

    Pass: the build set the car out at this track with this train. Fail: the build report names this gate
    as a refusal at this location. Anything else stays not_checked with what the build did instead."""
    row = result.get("builds", {}).get(train.name)
    if row is None:
        why = f"{train.name} was not built (Build is off), so there is no real build to read"
        return [{**g, "source": "port", "build_note": why} if g.get("settle") else g for g in gates]
    placed = {p["car"]: p for p in row.get("placed", [])}
    mine = placed.get(car.id)
    elsewhere = next((n for n, r in result["builds"].items()
                      if n != train.name and any(p["car"] == car.id for p in r.get("placed", []))), None)
    place = rr.locations[target.location_id].name
    refused = _refusals(row, car)
    out = []
    for g in gates:
        code = g["gate"]
        if not g.get("settle"):
            out.append(g)
        elif code in ("A8", "A9"):
            out.append(_a8(g, row, source, code))
        elif mine is not None and mine["track_id"] == target.id:
            out.append(_note(g, "pass", source=source, reason=f"the build set {car} out at {target.name} with {train.name}"))
        elif mine is not None:
            out.append({**g, "source": source, "build_note":
                        f"the build set the car out at {mine['location']}, {mine['track']} instead, "
                        "so it did not decide this track"})
        elif elsewhere:
            out.append({**g, "source": source, "build_note": f"the build put the car on {elsewhere}"})
        else:
            hit = next((line for c, line in refused if c == code and place in line), None)
            if hit:
                out.append(_note(g, "fail", source=source, reason=f"the build report refused the car: {hit}"))
            else:
                other = sorted({c for c, _ in refused})
                out.append({**g, "source": source, "build_note":
                            f"the build left the car off {train.name} and its report does not name {code} at {place}"
                            + (f" (it names {', '.join(other)})" if other else "")})
    return out


def _a8(g: dict, row: dict, source: str, code: str = "A8") -> dict:
    """A8 (departure staging with an AUTO count) and A9 (locomotives): the train builds or it does not."""
    if code == "A9" and row.get("built") and not row.get("engines"):
        return {**g, "source": source, "build_note": "the train built with no locomotive; check the engine list"}
    if row.get("built"):
        track = row.get("departure_track") or "a staging track"
        engines = len(row.get("engines", []))
        return _note(g, "pass", source=source, reason=f"the build departed from {track} with {engines} locomotive"
                                f"{'' if engines == 1 else 's'}")
    if row.get("failed"):
        return {**g, "source": source, "build_note":
                f"the build failed: {row.get('message', '')}; read the build report for the gate"}
    return {**g, "source": source, "build_note": "the build did not run for this train"}


def port_gate(g: dict) -> dict:
    """The port's own answer, left open, with the marker removed."""
    out = {k: v for k, v in g.items() if k != "settle"}
    return {**out, "source": "port"} if g.get("settle") and g["status"] == "not_checked" else out


def in_sync(rr) -> bool:
    """True when the railroad in memory is what the files hold, so a build of the files answers for it."""
    from ops_data import load
    try:
        fresh = load(rr.directory)
    except Exception:
        return False
    return all(getattr(rr, name) == getattr(fresh, name)
               for name in ("setup", "locations", "tracks", "schedules", "routes", "trains", "cars", "engines"))


def settle_runs(rr, gates_obj, car, train, target, gates: list[dict], results: list[dict], source: str) -> list[dict]:
    """settle_gates over several builds. Pass if any build passes the gate (the build can do it). Fail only
    if every build refuses it. Anything mixed stays not_checked and says how the builds split."""
    per = [settle_gates(rr, gates_obj, car, train, target, gates, r, source) for r in results]
    n = len(per)
    out = []
    for i, g in enumerate(gates):
        if not g.get("settle"):
            out.append(g)
            continue
        votes = [p[i] for p in per]
        passed = [v for v in votes if v["status"] == "pass"]
        failed = [v for v in votes if v["status"] == "fail"]
        if passed:
            note = "in all %d builds" % n if len(passed) == n else (
                f"in {len(passed)} of {n} builds; the builder draws at random, so another build may differ")
            out.append({**passed[0], "reason": f"{passed[0]['reason']} ({note})"})
        elif len(failed) == n:
            out.append({**failed[0], "reason": f"{failed[0]['reason']} (in all {n} builds)"})
        else:
            first = next((v for v in votes if v["status"] == "not_checked"), votes[0])
            extra = f"; {len(failed)} of {n} builds refused it" if failed else ""
            out.append({**first, "build_note": f"{first.get('build_note', '')}{extra}".strip("; ")})
    return out


def settle_table(rr, gates_obj, car, table: list) -> tuple[list, str | None]:
    """table rows are (train, track, gates). Returns the rows settled, and a note if JMRI could not run."""
    if not any(g.get("settle") for _, _, gates in table for g in gates):
        return table, None
    from ops_store import Refused
    if not in_sync(rr):
        return ([(t, k, [port_gate(g) for g in gates]) for t, k, gates in table],
                "The railroad in memory differs from the files, so a real build of the files cannot answer for it; "
                "those gates stay not_checked.")
    if not available():
        note = ("Some gates depend on the build and JMRI was not found (set JMRI_HOME), so they stay "
                "not_checked; they come from the port only.")
        return [(t, k, [port_gate(g) for g in gates])
                for t, k, gates in table], note
    try:
        result = real_build(rr.directory)
    except Refused as exc:
        return [(t, k, [port_gate(g) for g in gates])
                for t, k, gates in table], f"The real build could not run ({exc}); those gates stay not_checked."
    rows = []
    for t, k, gates in table:
        settled = settle_runs(rr, gates_obj, car, t, k, gates, result, SOURCE)
        if any(g.get("settle") and "put the car on" in g.get("build_note", "") for g in settled):
            try:  # Another train took the car in the full session; ask what this train does alone.
                alone = real_build(rr.directory, only=t.name)
                settled = settle_runs(rr, gates_obj, car, t, k, gates, alone, ALONE)
            except Refused:
                pass
        rows.append((t, k, [{x: v for x, v in g.items() if x != "settle"} for g in settled]))
    return rows, None
