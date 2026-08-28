"""
RS42 Experiment 1
Controlled preference trade-off: Fastest vs Fewer Transfers

This experiment deliberately separates two claims:

A) Preference behavior (controlled ASP case)
   - Direct itinerary: 0 transfers, journey time 9
   - Transfer itinerary: 1 transfer, journey time 6
   Expected:
       Fastest          -> transfer itinerary
       Fewer Transfers  -> direct itinerary

B) Execution validity (real Flatland regressions)
   Re-run the two already validated environments and record whether
   ASP plans still execute correctly in Flatland.

This script does NOT modify backend files.

Run from rs42 root:
    conda activate flatlandrs42
    python tools/run_exp1_transfer_preference.py
"""

from __future__ import print_function

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PASSENGER = ROOT / "asp" / "custom" / "passenger_transfer.lp"
VISUAL = ROOT / "asp" / "custom" / "visual.lp"
OBJECTIVES = ROOT / "asp" / "custom" / "objectives.lp"

RESULTS_DIR = ROOT / "experiments" / "controlled" / "results"
RAW_DIR = RESULTS_DIR / "raw"

EXP_CSV = RESULTS_DIR / "exp1_transfer_preference.csv"
EXP_JSON = RESULTS_DIR / "exp1_transfer_preference.json"
VAL_CSV = RESULTS_DIR / "flatland_execution_validation.csv"

FLATLAND_CASES = [
    ROOT / "envs" / "pkl" / "env_001--2_4.pkl",
    ROOT / "envs" / "pkl" / "test.pkl",
]


def require_files():
    required = [PASSENGER, VISUAL, OBJECTIVES] + FLATLAND_CASES
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing required RS42 files:\n" + "\n".join(missing)
        )


def unit_case_text(mode):
    return """% RS42 Experiment 1: controlled OD preference trade-off
objective_mode({mode}).

#const w_arrival = 8.
#const w_wait = 8.
#const w_transfer = 8.
#const w_turn = 4.
#const w_waypoint = 6.

passenger(p).
passenger_origin(p,a).
passenger_destination(p,d).

% Direct service: a -> d, duration 9, zero transfers.
first_station_visit(0,a,1).
first_station_visit(0,d,10).

% Faster transfer service:
% train 1 a -> b, then train 2 b -> d.
first_station_visit(1,a,1).
first_station_visit(1,b,4).

first_station_visit(2,b,5).
first_station_visit(2,d,7).

turns(0,1).
turns(1,1).
turns(2,1).

waypoint_time(0,0).
waypoint_time(1,0).
waypoint_time(2,0).

#show chosen_leg/7.
#show passenger_journey_time/2.
#show passenger_transfer_wait/2.
#show transfer_count/2.
""".format(mode=mode)


def run_clingo_case(mode):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    case_file = RAW_DIR / ("exp1_{0}.lp".format(mode))
    case_file.write_text(unit_case_text(mode), encoding="utf-8")

    cmd = [
        sys.executable,
        "-m",
        "clingo",
        str(case_file),
        str(PASSENGER),
        str(VISUAL),
        str(OBJECTIVES),
        "--outf=2",
        "--opt-mode=opt",
    ]

    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )

    raw_output = RAW_DIR / ("exp1_{0}_clingo.json".format(mode))
    raw_output.write_text(result.stdout, encoding="utf-8")

    stderr_output = RAW_DIR / ("exp1_{0}_stderr.txt".format(mode))
    stderr_output.write_text(result.stderr, encoding="utf-8")

    if result.returncode != 0 and not result.stdout.strip():
        raise RuntimeError(
            "{0}: clingo failed:\n{1}".format(mode, result.stderr[-4000:])
        )

    try:
        data = json.loads(result.stdout)
    except Exception:
        raise RuntimeError(
            "{0}: clingo did not return valid JSON.\nSTDOUT:\n{1}\nSTDERR:\n{2}".format(
                mode,
                result.stdout[-4000:],
                result.stderr[-4000:],
            )
        )

    status = str(data.get("Result", "UNKNOWN")).upper()
    if status != "OPTIMUM FOUND":
        raise RuntimeError(
            "{0}: expected OPTIMUM FOUND, got {1}".format(mode, status)
        )

    calls = data.get("Call", [])
    witnesses = calls[-1].get("Witnesses", []) if calls else []
    if not witnesses:
        raise RuntimeError("{0}: no optimum witness returned".format(mode))

    atoms = witnesses[-1].get("Value", [])

    def integer_atom(predicate):
        pattern = re.compile(
            r"^{0}\(p,(-?\d+)\)$".format(re.escape(predicate))
        )
        for atom in atoms:
            match = pattern.match(atom)
            if match:
                return int(match.group(1))
        return None

    journey_time = integer_atom("passenger_journey_time")
    transfer_wait = integer_atom("passenger_transfer_wait")
    transfers = integer_atom("transfer_count")

    legs = sorted(
        [atom for atom in atoms if atom.startswith("chosen_leg(")]
    )

    if journey_time is None or transfers is None:
        raise RuntimeError(
            "{0}: expected passenger metrics were not produced.\nAtoms:\n{1}".format(
                mode,
                "\n".join(atoms),
            )
        )

    return {
        "profile": mode,
        "journey_time": journey_time,
        "transfer_wait": transfer_wait,
        "transfers": transfers,
        "chosen_legs": legs,
        "clingo_status": status,
    }


def expected_assertions(rows):
    by_profile = {row["profile"]: row for row in rows}

    fastest = by_profile["fastest"]
    fewest = by_profile["fewest_transfers"]

    if fastest["journey_time"] != 6 or fastest["transfers"] != 1:
        raise RuntimeError(
            "Fastest did not produce expected controlled result: {0}".format(
                fastest
            )
        )

    if fewest["journey_time"] != 9 or fewest["transfers"] != 0:
        raise RuntimeError(
            "Fewer Transfers did not produce expected controlled result: {0}".format(
                fewest
            )
        )

    if fastest["journey_time"] >= fewest["journey_time"]:
        raise RuntimeError(
            "Controlled time trade-off is missing."
        )


def run_flatland_validation(env_path):
    cmd = [
        sys.executable,
        "solve.py",
        str(env_path),
        "--no-render",
    ]

    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )

    output = result.stdout + result.stderr

    raw_path = RAW_DIR / (
        "validation_{0}.txt".format(env_path.stem)
    )
    raw_path.write_text(output, encoding="utf-8")

    passed = (
        result.returncode == 0
        and "RS42_VALIDATION: PASS" in output
    )

    return {
        "environment": env_path.name,
        "validation": "PASS" if passed else "FAIL",
        "returncode": result.returncode,
    }


def write_results(exp_rows, validation_rows):
    with EXP_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "profile",
                "journey_time",
                "transfer_wait",
                "transfers",
                "chosen_legs",
                "clingo_status",
            ],
        )
        writer.writeheader()
        for row in exp_rows:
            out = dict(row)
            out["chosen_legs"] = " | ".join(row["chosen_legs"])
            writer.writerow(out)

    payload = {
        "experiment": "Experiment 1 - Fastest vs Fewer Transfers",
        "type": "controlled ASP preference experiment",
        "controlled_case": {
            "direct_itinerary": {
                "journey_time": 9,
                "transfers": 0,
            },
            "transfer_itinerary": {
                "journey_time": 6,
                "transfers": 1,
            },
        },
        "results": exp_rows,
        "interpretation_boundary": (
            "This controlled case tests preference-selection behavior. "
            "Flatland execution validity is reported separately using "
            "real RS42 environments."
        ),
        "flatland_execution_validation": validation_rows,
    }

    EXP_JSON.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    with VAL_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "environment",
                "validation",
                "returncode",
            ],
        )
        writer.writeheader()
        writer.writerows(validation_rows)


def main():
    require_files()

    print("Experiment 1: controlled preference trade-off")
    print()

    rows = []

    print("Running Fastest...")
    fastest = run_clingo_case("fastest")
    rows.append(fastest)
    print(
        "  journey_time={0}, transfers={1}".format(
            fastest["journey_time"],
            fastest["transfers"],
        )
    )

    print("Running Fewer Transfers...")
    fewest = run_clingo_case("fewest_transfers")
    rows.append(fewest)
    print(
        "  journey_time={0}, transfers={1}".format(
            fewest["journey_time"],
            fewest["transfers"],
        )
    )

    expected_assertions(rows)

    print()
    print("Controlled preference result: PASS")
    print("  Fastest          -> 6 journey time, 1 transfer")
    print("  Fewer Transfers  -> 9 journey time, 0 transfers")

    print()
    print("Re-running real Flatland execution regressions...")
    validation_rows = []
    for env_path in FLATLAND_CASES:
        result = run_flatland_validation(env_path)
        validation_rows.append(result)
        print(
            "  {0}: {1}".format(
                result["environment"],
                result["validation"],
            )
        )

    if not all(row["validation"] == "PASS" for row in validation_rows):
        raise RuntimeError(
            "At least one Flatland execution regression failed."
        )

    write_results(rows, validation_rows)

    print()
    print("SUCCESS")
    print("Saved:")
    print("  {0}".format(EXP_CSV.relative_to(ROOT)))
    print("  {0}".format(EXP_JSON.relative_to(ROOT)))
    print("  {0}".format(VAL_CSV.relative_to(ROOT)))
    print("  {0}".format(RAW_DIR.relative_to(ROOT)))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR: {0}".format(exc), file=sys.stderr)
        raise SystemExit(1)
