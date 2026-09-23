from __future__ import print_function

import argparse
import csv
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RUNNER_PATH = (
    ROOT / "tools" / "final_evaluation" / "run_final_evaluation_30.py"
)

ALL_RUNS_CSV = (
    ROOT / "experiments" / "final_evaluation" / "results" / "runs" / "all_runs.csv"
)

VALIDATION_CSV = (
    ROOT / "experiments" / "final_evaluation" / "results"
    / "validation" / "environment_validation.csv"
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--timeout",
        type=int,
        default=900,
        help="Retry timeout per E6 case. Default: 900 seconds.",
    )
    return parser.parse_args()


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "rs42_final_30run",
        str(RUNNER_PATH),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def coerce(value):
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text in {"None", "null"}:
        return None
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return value


def read_rows():
    with ALL_RUNS_CSV.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    numeric_fields = [
        "runtime_seconds",
        "journey_time",
        "transfer_wait",
        "transfers",
        "turns",
        "train_travel_time_sum",
        "train_wait_time_sum",
        "timeout_seconds",
    ]

    for row in rows:
        for field in numeric_fields:
            row[field] = coerce(row.get(field))

    return rows


def read_validation_rows():
    if not VALIDATION_CSV.exists():
        return []

    with VALIDATION_CSV.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        row["runtime_seconds"] = coerce(row.get("runtime_seconds"))
        row["returncode"] = coerce(row.get("returncode"))

    return rows


def replace_row(rows, new_row):
    key = (new_row["environment"], new_row["profile"])

    for index, row in enumerate(rows):
        if (row["environment"], row["profile"]) == key:
            rows[index] = new_row
            return

    raise RuntimeError("Existing row not found: {}".format(key))


def main():
    args = parse_args()

    if not RUNNER_PATH.exists():
        raise FileNotFoundError(str(RUNNER_PATH))

    if not ALL_RUNS_CSV.exists():
        raise FileNotFoundError(
            "Run the main 30-run evaluation first; all_runs.csv is missing."
        )

    runner = load_runner()
    runner.ensure_dirs()
    runner.require_files()

    rows = read_rows()
    validation_rows = read_validation_rows()

    e6 = next(
        item
        for item in runner.ENVIRONMENTS
        if item["stem"] == "e6_shared_conflict"
    )

    print("RS42 E6 TARGETED RETRY")
    print("Only the two timed-out E6 profiles will run.")
    print("Timeout per case: {} seconds".format(args.timeout))
    print()

    for profile in ["least_waiting", "simple"]:
        label = runner.PROFILE_LABELS[profile]

        print("Retrying E6 / {} ... ".format(label), end="", flush=True)

        new_row = runner.run_one(
            e6,
            profile,
            args.timeout,
        )

        replace_row(rows, new_row)

        print(
            "{} | turns={} | travel_sum={} | wait_sum={} | {:.3f}s".format(
                new_row["status"],
                new_row["turns"],
                new_row["train_travel_time_sum"],
                new_row["train_wait_time_sum"],
                new_row["runtime_seconds"],
            )
        )

    primary_checks = runner.build_primary_checks(rows)
    robustness_checks = runner.build_robustness_checks(rows)

    completion = runner.write_outputs(
        rows,
        primary_checks,
        robustness_checks,
        validation_rows,
        archived_results=None,
    )

    optimum_count = sum(
        1 for row in rows
        if row["status"] == "OPTIMUM FOUND"
    )

    print()
    print("UPDATED FINAL SUMMARY")
    print("  Optimization runs: {}/30 OPTIMUM FOUND".format(optimum_count))
    print(
        "  Controlled checks: {}/{}".format(
            completion["primary_checks_passed"],
            completion["primary_checks_total"],
        )
    )
    print(
        "  E6 robustness: {}/{}".format(
            completion["e6_robustness_passed"],
            completion["e6_robustness_total"],
        )
    )
    print(
        "  Flatland validation: {}/6 PASS".format(
            completion["flatland_validation_passed"]
        )
    )
    print("  FINAL STATUS: {}".format(completion["overall_status"]))

    if completion["overall_status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        raise SystemExit(1)
