
from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd().resolve()

if not (ROOT / "solve.py").exists():
    raise SystemExit("ERROR: Run this script from the RS42 repository root.")

CHANGED_ENVS = [
    ("e1_fast_slow", "E1 - Fast vs Slow"),
    ("e2_transfer_network", "E2 - Transfer Network"),
    ("e3_waiting_network", "E3 - Waiting Network"),
    ("e5_mixed_preferences", "E5 - Mixed Preferences"),
]

FROZEN_ENVS = {
    "e4_simple_complex",
    "e6_shared_conflict",
}

PROFILES = [
    ("fastest", "Fastest", "profile_fastest.lp"),
    ("least_waiting", "Less Waiting", "profile_least_waiting.lp"),
    ("fewest_transfers", "Fewer Transfers", "profile_fewest_transfers.lp"),
    ("simple", "Simple Journey", "profile_comfort.lp"),
    ("balanced", "Balanced", "profile_balanced.lp"),
]

ENCODINGS = [
    ROOT / "asp" / "custom" / "connection.lp",
    ROOT / "asp" / "custom" / "encoding.lp",
    ROOT / "asp" / "custom" / "waypoint.lp",
    ROOT / "asp" / "custom" / "passenger_transfer.lp",
    ROOT / "asp" / "custom" / "visual.lp",
    ROOT / "asp" / "custom" / "objectives.lp",
]

RESULT_DIR = (
    ROOT
    / "experiments"
    / "final_evaluation"
    / "results"
)

RUN_DIR = RESULT_DIR / "runs"
SUMMARY_DIR = RESULT_DIR / "summaries"

FINAL_CSV = RUN_DIR / "all_runs.csv"
REFRESH_CSV = RUN_DIR / "fresh_e1_e2_e3_e5_runs.csv"
SUMMARY_JSON = SUMMARY_DIR / "refresh_20_summary.json"

TIMEOUT = 300

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

def pair_atoms(atoms, predicate):
    pattern = re.compile(
        rf"^{re.escape(predicate)}\(([^,()]+),(-?\d+)\)$"
    )
    values = {}
    for atom in atoms:
        m = pattern.match(atom)
        if m:
            values[m.group(1)] = int(m.group(2))
    return values

def first_metric(atoms, predicate):
    values = pair_atoms(atoms, predicate)
    if not values:
        return None
    return next(iter(values.values()))

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

def selected_train_ids(atoms, legs):
    if legs:
        return sorted({row["train"] for row in legs})

    ids = []
    patterns = [
        re.compile(r"^passenger_uses_train\([^,]+,(\d+)\)$"),
        re.compile(r"^uses_train\([^,]+,(\d+),\d+\)$"),
    ]

    for atom in atoms:
        for pattern in patterns:
            m = pattern.match(atom)
            if m:
                ids.append(int(m.group(1)))
                break

    return sorted(set(ids))

def aggregate(mapping, train_ids):
    values = [
        mapping[str(train)]
        for train in train_ids
        if str(train) in mapping
    ]
    return sum(values) if values else None

def run_case(stem, env_label, profile_key, profile_label, profile_filename, show_file):
    env_lp = ROOT / "envs" / "lp" / f"{stem}.lp"
    scenario = ROOT / "asp" / "scenarios" / f"{stem}.lp"
    profile = ROOT / "asp" / "profiles" / profile_filename

    for path in [env_lp, scenario, profile] + ENCODINGS:
        if not path.exists():
            raise RuntimeError(f"Missing required file: {path}")

    cmd = [
        sys.executable,
        "-m",
        "clingo",
        str(env_lp),
        *[str(path) for path in ENCODINGS],
        str(profile),
        str(scenario),
        str(show_file),
        "--outf=2",
        "--opt-mode=opt",
    ]

    started = time.perf_counter()

    try:
        process = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        elapsed = time.perf_counter() - started
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - started
        return {
            "environment": stem,
            "environment_label": env_label,
            "profile": profile_key,
            "profile_label": profile_label,
            "status": "TIMEOUT",
            "journey_time": "",
            "transfer_wait": "",
            "transfers": "",
            "turns": "",
            "runtime_seconds": round(elapsed, 3),
            "selected_trains": "",
            "chosen_legs": "",
        }

    try:
        payload = json.loads(process.stdout)
    except Exception:
        return {
            "environment": stem,
            "environment_label": env_label,
            "profile": profile_key,
            "profile_label": profile_label,
            "status": "ERROR",
            "journey_time": "",
            "transfer_wait": "",
            "transfers": "",
            "turns": "",
            "runtime_seconds": round(elapsed, 3),
            "selected_trains": "",
            "chosen_legs": "",
        }

    status = str(payload.get("Result", "UNKNOWN")).upper()

    calls = payload.get("Call", [])
    witnesses = calls[-1].get("Witnesses", []) if calls else []

    atoms = witnesses[-1].get("Value", []) if witnesses else []

    legs = chosen_legs(atoms)
    train_ids = selected_train_ids(atoms, legs)

    journey = first_metric(atoms, "passenger_journey_time")
    waiting = first_metric(atoms, "passenger_transfer_wait")
    transfers = first_metric(atoms, "transfer_count")

    travel = pair_atoms(atoms, "travel_time")
    turns_map = pair_atoms(atoms, "turns")

    if journey is None:
        journey = aggregate(travel, train_ids)

    turns = aggregate(turns_map, train_ids)

    return {
        "environment": stem,
        "environment_label": env_label,
        "profile": profile_key,
        "profile_label": profile_label,
        "status": status,
        "journey_time": "" if journey is None else journey,
        "transfer_wait": "" if waiting is None else waiting,
        "transfers": "" if transfers is None else transfers,
        "turns": "" if turns is None else turns,
        "runtime_seconds": round(elapsed, 3),
        "selected_trains": json.dumps(train_ids),
        "chosen_legs": json.dumps(legs),
    }

def merge_with_frozen(fresh_rows):
    frozen_rows = []

    if FINAL_CSV.exists():
        with FINAL_CSV.open(
            "r",
            newline="",
            encoding="utf-8",
        ) as handle:
            previous = list(csv.DictReader(handle))

        frozen_rows = [
            row
            for row in previous
            if row.get("environment") in FROZEN_ENVS
        ]

    expected_frozen = 10

    if len(frozen_rows) != expected_frozen:
        print()
        print(
            "WARNING: expected 10 frozen E4/E6 rows, found {}."
            .format(len(frozen_rows))
        )
        print(
            "The fresh 20 runs will still be saved, but all_runs.csv "
            "will not be replaced automatically."
        )
        return None

    all_rows = fresh_rows + frozen_rows

    # Normalize a common field set while preserving extra old columns.
    fieldnames = []

    preferred = [
        "environment",
        "environment_label",
        "profile",
        "profile_label",
        "status",
        "journey_time",
        "transfer_wait",
        "transfers",
        "turns",
        "runtime_seconds",
        "selected_trains",
        "chosen_legs",
    ]

    for field in preferred:
        if any(field in row for row in all_rows):
            fieldnames.append(field)

    for row in all_rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)

    backup_dir = (
        ROOT
        / "experiments"
        / "final_evaluation"
        / "_archive"
    )
    backup_dir.mkdir(parents=True, exist_ok=True)

    if FINAL_CSV.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = backup_dir / f"all_runs_before_refresh_{stamp}.csv"
        shutil.copy2(FINAL_CSV, backup)
        print("Previous all_runs.csv archived to:")
        print(" ", backup.relative_to(ROOT))

    with FINAL_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(all_rows)

    return all_rows

def main():
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 76)
    print("RS42 FRESH E1/E2/E3/E5 EVALUATION")
    print("4 environments x 5 profiles = 20 runs")
    print("=" * 76)
    print("Timeout per run:", TIMEOUT, "seconds")
    print()

    fresh_rows = []

    with tempfile.TemporaryDirectory() as tmp:
        show_file = Path(tmp) / "show.lp"
        show_file.write_text(SHOW, encoding="utf-8")

        total = len(CHANGED_ENVS) * len(PROFILES)
        number = 0

        for stem, env_label in CHANGED_ENVS:
            print()
            print("===", env_label, "===")

            for profile_key, profile_label, profile_filename in PROFILES:
                number += 1

                print(
                    "[{:02d}/{:02d}] {:<18} ... ".format(
                        number,
                        total,
                        profile_label,
                    ),
                    end="",
                    flush=True,
                )

                row = run_case(
                    stem,
                    env_label,
                    profile_key,
                    profile_label,
                    profile_filename,
                    show_file,
                )

                fresh_rows.append(row)

                print(
                    "{} | journey={} wait={} transfers={} turns={} | {}s".format(
                        row["status"],
                        row["journey_time"],
                        row["transfer_wait"],
                        row["transfers"],
                        row["turns"],
                        row["runtime_seconds"],
                    )
                )

    fieldnames = [
        "environment",
        "environment_label",
        "profile",
        "profile_label",
        "status",
        "journey_time",
        "transfer_wait",
        "transfers",
        "turns",
        "runtime_seconds",
        "selected_trains",
        "chosen_legs",
    ]

    with REFRESH_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(fresh_rows)

    optimum = sum(
        1
        for row in fresh_rows
        if row["status"] == "OPTIMUM FOUND"
    )

    timeouts = [
        "{} / {}".format(
            row["environment"],
            row["profile_label"],
        )
        for row in fresh_rows
        if row["status"] == "TIMEOUT"
    ]

    merged = merge_with_frozen(fresh_rows)

    summary = {
        "fresh_runs": len(fresh_rows),
        "fresh_optimum_found": optimum,
        "fresh_non_optimum": len(fresh_rows) - optimum,
        "timeouts": timeouts,
        "merged_total_rows": (
            len(merged)
            if merged is not None
            else None
        ),
        "frozen_environments": sorted(FROZEN_ENVS),
        "refreshed_environments": [
            stem for stem, _ in CHANGED_ENVS
        ],
    }

    SUMMARY_JSON.write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 76)
    print("REFRESH SUMMARY")
    print("=" * 76)
    print(
        "Fresh optimization runs: {}/20 OPTIMUM FOUND"
        .format(optimum)
    )

    if timeouts:
        print("Timeouts:")
        for item in timeouts:
            print("  ", item)
    else:
        print("Timeouts: none")

    print()
    print(
        "Fresh CSV:",
        REFRESH_CSV.relative_to(ROOT),
    )

    if merged is not None:
        print(
            "Merged final CSV:",
            FINAL_CSV.relative_to(ROOT),
        )
        print(
            "Merged rows:",
            len(merged),
        )

    print(
        "Summary:",
        SUMMARY_JSON.relative_to(ROOT),
    )

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
