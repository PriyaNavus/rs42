
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path.cwd().resolve()

if not (ROOT / "solve.py").exists():
    raise SystemExit("ERROR: Run this script from the RS42 repository root.")

STEM = "e5_mixed_preferences"

ENV_LP = ROOT / "envs" / "lp" / f"{STEM}.lp"
SCENARIO = ROOT / "asp" / "scenarios" / f"{STEM}.lp"
PROFILE = ROOT / "asp" / "profiles" / "profile_fastest.lp"

ENCODINGS = [
    ROOT / "asp" / "custom" / "connection.lp",
    ROOT / "asp" / "custom" / "encoding.lp",
    ROOT / "asp" / "custom" / "waypoint.lp",
    ROOT / "asp" / "custom" / "passenger_transfer.lp",
    ROOT / "asp" / "custom" / "visual.lp",
    ROOT / "asp" / "custom" / "objectives.lp",
]

for path in [ENV_LP, SCENARIO, PROFILE] + ENCODINGS:
    if not path.exists():
        raise SystemExit(f"ERROR: Missing required file: {path}")

SHOW = """
#show chosen_leg/7.
#show passenger_journey_time/2.
#show passenger_transfer_wait/2.
#show transfer_count/2.
#show passenger_uses_train/2.
#show uses_train/3.
#show travel_time/2.
#show turns/2.
"""

def metric(atoms, predicate):
    pattern = re.compile(
        rf"^{re.escape(predicate)}\(([^,()]+),(-?\d+)\)$"
    )
    for atom in atoms:
        match = pattern.match(atom)
        if match:
            return int(match.group(2))
    return None

def chosen_legs(atoms):
    pattern = re.compile(
        r"^chosen_leg\(([^,]+),(\d+),(\d+),([^,]+),([^,]+),(-?\d+),(-?\d+)\)$"
    )
    rows = []
    for atom in atoms:
        m = pattern.match(atom)
        if m:
            rows.append(
                {
                    "leg": int(m.group(2)),
                    "train": int(m.group(3)),
                    "from": m.group(4),
                    "to": m.group(5),
                    "board": int(m.group(6)),
                    "alight": int(m.group(7)),
                }
            )
    return sorted(rows, key=lambda row: row["leg"])

with tempfile.TemporaryDirectory() as tmp:
    show_file = Path(tmp) / "show.lp"
    show_file.write_text(SHOW, encoding="utf-8")

    cmd = [
        sys.executable,
        "-m",
        "clingo",
        str(ENV_LP),
        *[str(path) for path in ENCODINGS],
        str(PROFILE),
        str(SCENARIO),
        str(show_file),
        "--outf=2",
        "--opt-mode=opt",
    ]

    print("=" * 72)
    print("RS42 E5 FASTEST SMOKE TEST")
    print("=" * 72)
    print("Environment:", ENV_LP.relative_to(ROOT))
    print("Scenario:   ", SCENARIO.relative_to(ROOT))
    print("Profile:     Fastest")
    print("Timeout:     300 seconds")
    print()

    started = time.perf_counter()

    try:
        process = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise SystemExit(
            "E5 SMOKE TEST: TIMEOUT after 300 seconds.\n"
            "Do NOT start the 20-run evaluation."
        )

    elapsed = time.perf_counter() - started

    try:
        payload = json.loads(process.stdout)
    except Exception:
        print(process.stdout[-4000:])
        print(process.stderr[-4000:])
        raise SystemExit("E5 SMOKE TEST: could not parse Clingo JSON output.")

    status = str(payload.get("Result", "UNKNOWN")).upper()
    calls = payload.get("Call", [])
    witnesses = calls[-1].get("Witnesses", []) if calls else []

    print("Result:", status)
    print("Runtime: {:.2f}s".format(elapsed))

    if status != "OPTIMUM FOUND" or not witnesses:
        print()
        print(process.stderr[-3000:])
        raise SystemExit(
            "E5 SMOKE TEST: FAIL. Expected OPTIMUM FOUND."
        )

    atoms = witnesses[-1].get("Value", [])

    journey = metric(atoms, "passenger_journey_time")
    waiting = metric(atoms, "passenger_transfer_wait")
    transfers = metric(atoms, "transfer_count")
    legs = chosen_legs(atoms)

    print()
    print("Passenger result")
    print("  journey:   ", journey)
    print("  waiting:   ", waiting)
    print("  transfers: ", transfers)

    if legs:
        print()
        print("Chosen legs")
        for row in legs:
            print(
                "  leg {leg}: train {train} | {from_} -> {to} | {board} -> {alight}".format(
                    leg=row["leg"],
                    train=row["train"],
                    from_=row["from"],
                    to=row["to"],
                    board=row["board"],
                    alight=row["alight"],
                )
            )

    print()
    print("E5 SMOKE TEST: PASS")
    print("You can now run the 20-case refresh script.")
