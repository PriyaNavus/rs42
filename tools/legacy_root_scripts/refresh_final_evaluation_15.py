
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
    raise SystemExit(
        "ERROR: Run this script from the RS42 repository root."
    )

CHANGED_ENVS = [
    (
        "e1_fast_slow",
        "E1 - Fast vs Slow",
    ),
    (
        "e2_transfer_network",
        "E2 - Transfer Network",
    ),
    (
        "e3_waiting_network",
        "E3 - Waiting Network",
    ),
]

FROZEN_ENVS = {
    "e4_simple_complex",
    "e5_mixed_preferences",
    "e6_shared_conflict",
}

PROFILES = [
    (
        "fastest",
        "Fastest",
        "profile_fastest.lp",
    ),
    (
        "least_waiting",
        "Less Waiting",
        "profile_least_waiting.lp",
    ),
    (
        "fewest_transfers",
        "Fewer Transfers",
        "profile_fewest_transfers.lp",
    ),
    (
        "simple",
        "Simple Journey",
        "profile_comfort.lp",
    ),
    (
        "balanced",
        "Balanced",
        "profile_balanced.lp",
    ),
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

REFRESH_CSV = (
    RUN_DIR
    / "fresh_e1_e2_e3_runs.csv"
)

SUMMARY_JSON = (
    SUMMARY_DIR
    / "refresh_15_summary.json"
)

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


def pair_atoms(
    atoms,
    predicate,
):
    pattern = re.compile(
        rf"^{re.escape(predicate)}\(([^,()]+),(-?\d+)\)$"
    )

    values = {}

    for atom in atoms:
        match = pattern.match(
            atom
        )

        if match:
            values[
                match.group(1)
            ] = int(
                match.group(2)
            )

    return values


def first_metric(
    atoms,
    predicate,
):
    values = pair_atoms(
        atoms,
        predicate,
    )

    if not values:
        return None

    return next(
        iter(
            values.values()
        )
    )


def chosen_legs(atoms):
    pattern = re.compile(
        r"^chosen_leg\("
        r"([^,]+),"
        r"(\d+),"
        r"(\d+),"
        r"([^,]+),"
        r"([^,]+),"
        r"(-?\d+),"
        r"(-?\d+)"
        r"\)$"
    )

    rows = []

    for atom in atoms:
        match = pattern.match(
            atom
        )

        if not match:
            continue

        rows.append(
            {
                "leg": int(
                    match.group(2)
                ),
                "train": int(
                    match.group(3)
                ),
                "from": match.group(4),
                "to": match.group(5),
                "board": int(
                    match.group(6)
                ),
                "alight": int(
                    match.group(7)
                ),
            }
        )

    return sorted(
        rows,
        key=lambda row: row["leg"],
    )


def selected_train_ids(
    atoms,
    legs,
):
    if legs:
        return sorted(
            {
                row["train"]
                for row in legs
            }
        )

    ids = []

    patterns = [
        re.compile(
            r"^passenger_uses_train\([^,]+,(\d+)\)$"
        ),
        re.compile(
            r"^uses_train\([^,]+,(\d+),\d+\)$"
        ),
    ]

    for atom in atoms:
        for pattern in patterns:
            match = pattern.match(
                atom
            )

            if match:
                ids.append(
                    int(
                        match.group(1)
                    )
                )
                break

    return sorted(
        set(ids)
    )


def aggregate(
    mapping,
    train_ids,
):
    values = [
        mapping[str(train)]
        for train in train_ids
        if str(train) in mapping
    ]

    if not values:
        return None

    return sum(values)


def blank_row(
    stem,
    env_label,
    profile_key,
    profile_label,
    status,
    elapsed,
):
    return {
        "environment": stem,
        "environment_label": env_label,
        "profile": profile_key,
        "profile_label": profile_label,
        "status": status,
        "journey_time": "",
        "transfer_wait": "",
        "transfers": "",
        "turns": "",
        "runtime_seconds": round(
            elapsed,
            3,
        ),
        "selected_trains": "",
        "chosen_legs": "",
    }


def run_case(
    stem,
    env_label,
    profile_key,
    profile_label,
    profile_filename,
    show_file,
):
    env_lp = (
        ROOT
        / "envs"
        / "lp"
        / f"{stem}.lp"
    )

    scenario = (
        ROOT
        / "asp"
        / "scenarios"
        / f"{stem}.lp"
    )

    profile = (
        ROOT
        / "asp"
        / "profiles"
        / profile_filename
    )

    required = (
        [env_lp, scenario, profile]
        + ENCODINGS
    )

    for path in required:
        if not path.exists():
            raise RuntimeError(
                "Missing required file: {}"
                .format(path)
            )

    cmd = [
        sys.executable,
        "-m",
        "clingo",
        str(env_lp),
        *[
            str(path)
            for path in ENCODINGS
        ],
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

    except subprocess.TimeoutExpired:
        elapsed = (
            time.perf_counter()
            - started
        )

        return blank_row(
            stem,
            env_label,
            profile_key,
            profile_label,
            "TIMEOUT",
            elapsed,
        )

    elapsed = (
        time.perf_counter()
        - started
    )

    try:
        payload = json.loads(
            process.stdout
        )

    except Exception:
        return blank_row(
            stem,
            env_label,
            profile_key,
            profile_label,
            "ERROR",
            elapsed,
        )

    status = str(
        payload.get(
            "Result",
            "UNKNOWN",
        )
    ).upper()

    calls = payload.get(
        "Call",
        [],
    )

    witnesses = (
        calls[-1].get(
            "Witnesses",
            [],
        )
        if calls
        else []
    )

    atoms = (
        witnesses[-1].get(
            "Value",
            [],
        )
        if witnesses
        else []
    )

    legs = chosen_legs(
        atoms
    )

    train_ids = selected_train_ids(
        atoms,
        legs,
    )

    journey = first_metric(
        atoms,
        "passenger_journey_time",
    )

    waiting = first_metric(
        atoms,
        "passenger_transfer_wait",
    )

    transfers = first_metric(
        atoms,
        "transfer_count",
    )

    travel = pair_atoms(
        atoms,
        "travel_time",
    )

    turns_map = pair_atoms(
        atoms,
        "turns",
    )

    if journey is None:
        journey = aggregate(
            travel,
            train_ids,
        )

    turns = aggregate(
        turns_map,
        train_ids,
    )

    return {
        "environment": stem,
        "environment_label": env_label,
        "profile": profile_key,
        "profile_label": profile_label,
        "status": status,
        "journey_time": (
            ""
            if journey is None
            else journey
        ),
        "transfer_wait": (
            ""
            if waiting is None
            else waiting
        ),
        "transfers": (
            ""
            if transfers is None
            else transfers
        ),
        "turns": (
            ""
            if turns is None
            else turns
        ),
        "runtime_seconds": round(
            elapsed,
            3,
        ),
        "selected_trains": json.dumps(
            train_ids
        ),
        "chosen_legs": json.dumps(
            legs
        ),
    }


def read_previous_rows():
    if not FINAL_CSV.exists():
        raise RuntimeError(
            "Existing all_runs.csv was not found. "
            "It is needed to retain frozen E4/E5/E6 results."
        )

    with FINAL_CSV.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:
        return list(
            csv.DictReader(
                handle
            )
        )


def merge_final(
    fresh_rows,
):
    previous = read_previous_rows()

    frozen_rows = [
        row
        for row in previous
        if row.get(
            "environment"
        ) in FROZEN_ENVS
    ]

    if len(frozen_rows) != 15:
        raise RuntimeError(
            "Expected 15 frozen E4/E5/E6 rows in all_runs.csv, "
            "but found {}. The fresh CSV is safe; final merge was not done."
            .format(
                len(frozen_rows)
            )
        )

    final_rows = (
        fresh_rows
        + frozen_rows
    )

    fields = [
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

    for row in final_rows:
        for key in row:
            if key not in fields:
                fields.append(
                    key
                )

    archive = (
        ROOT
        / "experiments"
        / "final_evaluation"
        / "_archive"
    )

    archive.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup = (
        archive
        / "all_runs_before_refresh_{}.csv"
        .format(stamp)
    )

    shutil.copy2(
        FINAL_CSV,
        backup,
    )

    with FINAL_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(
            final_rows
        )

    return (
        final_rows,
        backup,
    )


def main():
    RUN_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SUMMARY_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 76)
    print("RS42 FINAL REFRESH")
    print("E1 + E2 + E3 only")
    print("3 environments x 5 profiles = 15 fresh runs")
    print("=" * 76)
    print()

    fresh_rows = []

    with tempfile.TemporaryDirectory() as tmp:
        show_file = (
            Path(tmp)
            / "show.lp"
        )

        show_file.write_text(
            SHOW,
            encoding="utf-8",
        )

        total = (
            len(CHANGED_ENVS)
            * len(PROFILES)
        )

        number = 0

        for (
            stem,
            env_label,
        ) in CHANGED_ENVS:

            print()
            print(
                "=== {} ==="
                .format(
                    env_label
                )
            )

            for (
                profile_key,
                profile_label,
                profile_filename,
            ) in PROFILES:

                number += 1

                print(
                    "[{:02d}/{:02d}] {:<18} ... "
                    .format(
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

                fresh_rows.append(
                    row
                )

                print(
                    "{} | journey={} wait={} transfers={} turns={} | {}s"
                    .format(
                        row["status"],
                        row["journey_time"],
                        row["transfer_wait"],
                        row["transfers"],
                        row["turns"],
                        row["runtime_seconds"],
                    )
                )

    fields = [
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
            fieldnames=fields,
        )

        writer.writeheader()

        writer.writerows(
            fresh_rows
        )

    optimum = sum(
        row["status"]
        == "OPTIMUM FOUND"
        for row in fresh_rows
    )

    failures = [
        {
            "environment": row["environment"],
            "profile": row["profile_label"],
            "status": row["status"],
        }
        for row in fresh_rows
        if row["status"]
        != "OPTIMUM FOUND"
    ]

    merged = None
    backup = None

    if optimum == 15:
        try:
            merged, backup = merge_final(
                fresh_rows
            )

        except Exception as exc:
            print()
            print(
                "FINAL MERGE NOT PERFORMED:"
            )
            print(
                " ",
                exc,
            )

    else:
        print()
        print(
            "Final all_runs.csv was NOT replaced because "
            "not all 15 fresh runs reached OPTIMUM FOUND."
        )

    summary = {
        "fresh_runs": 15,
        "optimum_found": optimum,
        "failures": failures,
        "final_merge_performed": (
            merged is not None
        ),
        "final_rows": (
            len(merged)
            if merged is not None
            else None
        ),
        "refreshed_environments": [
            stem
            for stem, _ in CHANGED_ENVS
        ],
        "frozen_environments": sorted(
            FROZEN_ENVS
        ),
        "test02_level8_note": (
            "Supplementary Test_02 Level_8 E5 attempt timed out "
            "after 300 seconds under the current ASP formulation."
        ),
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
    print("FINAL REFRESH SUMMARY")
    print("=" * 76)

    print(
        "Fresh runs with OPTIMUM FOUND: {}/15"
        .format(
            optimum
        )
    )

    if failures:
        print(
            "Non-optimum cases:"
        )

        for item in failures:
            print(
                "  {} / {} -> {}"
                .format(
                    item["environment"],
                    item["profile"],
                    item["status"],
                )
            )

    else:
        print(
            "Fresh timeouts/errors: none"
        )

    print()
    print(
        "Fresh results:",
        REFRESH_CSV.relative_to(
            ROOT
        ),
    )

    if merged is not None:
        print(
            "Final merged results:",
            FINAL_CSV.relative_to(
                ROOT
            ),
        )

        print(
            "Final rows:",
            len(merged),
        )

        print(
            "Previous results archived:",
            backup.relative_to(
                ROOT
            ),
        )

    print(
        "Summary:",
        SUMMARY_JSON.relative_to(
            ROOT
        ),
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        print(
            "ERROR:",
            exc,
            file=sys.stderr,
        )

        raise SystemExit(1)
