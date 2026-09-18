from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path.cwd().resolve()

RUNS_CSV = (
    ROOT
    / "experiments"
    / "final_evaluation"
    / "results"
    / "runs"
    / "all_runs.csv"
)

OUTPUT_JSON = (
    ROOT
    / "experiments"
    / "final_evaluation"
    / "results"
    / "summaries"
    / "primary_checks.json"
)

PROFILES = [
    "fastest",
    "least_waiting",
    "fewest_transfers",
    "simple",
    "balanced",
]

IDEAL_TRANSFER = 6


def number(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "null"}:
        return None
    try:
        return float(text) if "." in text else int(text)
    except ValueError:
        return None


def load_rows():
    if not RUNS_CSV.exists():
        raise SystemExit(f"Missing results file: {RUNS_CSV}")

    with RUNS_CSV.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        for field in [
            "journey_time",
            "transfer_wait",
            "transfers",
            "turns",
            "runtime_seconds",
        ]:
            row[field] = number(row.get(field))

    return rows


def get(rows, env, profile):
    for row in rows:
        if row.get("environment") == env and row.get("profile") == profile:
            return row
    raise KeyError(f"Missing run: {env} / {profile}")


def is_optimum(row):
    return row.get("status") == "OPTIMUM FOUND"


def make_check(name, environment, description, passed, observed):
    return {
        "name": name,
        "environment": environment,
        "description": description,
        "observed": observed,
        "pass": bool(passed),
    }


def main():
    rows = load_rows()
    checks = []

    # E1: control environment — all profiles should agree.
    e1 = [get(rows, "e1_fast_slow", p) for p in PROFILES]
    e1_journeys = [r["journey_time"] for r in e1]

    checks.append(
        make_check(
            "E1 all canonical profiles reach a proven optimum",
            "e1_fast_slow",
            "The E1 control environment should remain solvable under every profile.",
            all(is_optimum(r) for r in e1),
            {r["profile"]: r["status"] for r in e1},
        )
    )

    checks.append(
        make_check(
            "E1 profiles agree when no meaningful preference trade-off exists",
            "e1_fast_slow",
            "All five profiles should select the same passenger journey time in E1.",
            all(v is not None for v in e1_journeys)
            and len(set(e1_journeys)) == 1,
            {r["profile"]: r["journey_time"] for r in e1},
        )
    )

    # E2: journey time versus transfer count.
    e2_fast = get(rows, "e2_transfer_network", "fastest")
    e2_few = get(rows, "e2_transfer_network", "fewest_transfers")

    checks.append(
        make_check(
            "E2 Fastest accepts a transfer for a shorter journey",
            "e2_transfer_network",
            "Fastest should have a shorter journey time than Fewer Transfers.",
            is_optimum(e2_fast)
            and is_optimum(e2_few)
            and e2_fast["journey_time"] is not None
            and e2_few["journey_time"] is not None
            and e2_fast["journey_time"] < e2_few["journey_time"],
            {
                "fastest_journey": e2_fast["journey_time"],
                "fewest_transfers_journey": e2_few["journey_time"],
            },
        )
    )

    checks.append(
        make_check(
            "E2 Fewer Transfers uses fewer train changes than Fastest",
            "e2_transfer_network",
            "The transfer-focused profile should reduce transfer count relative to Fastest.",
            e2_fast["transfers"] is not None
            and e2_few["transfers"] is not None
            and e2_few["transfers"] < e2_fast["transfers"],
            {
                "fastest_transfers": e2_fast["transfers"],
                "fewest_transfers_transfers": e2_few["transfers"],
            },
        )
    )

    # E3: quicker trip versus transfer timing closest to the 6-step ideal.
    e3_fast = get(rows, "e3_waiting_network", "fastest")
    e3_wait = get(rows, "e3_waiting_network", "least_waiting")

    checks.append(
        make_check(
            "E3 Fastest chooses the quicker itinerary",
            "e3_waiting_network",
            "Fastest should arrive sooner than the transfer-timing profile.",
            is_optimum(e3_fast)
            and is_optimum(e3_wait)
            and e3_fast["journey_time"] is not None
            and e3_wait["journey_time"] is not None
            and e3_fast["journey_time"] < e3_wait["journey_time"],
            {
                "fastest_journey": e3_fast["journey_time"],
                "less_waiting_journey": e3_wait["journey_time"],
            },
        )
    )

    fast_dev = (
        abs(e3_fast["transfer_wait"] - IDEAL_TRANSFER)
        if e3_fast["transfer_wait"] is not None
        else None
    )
    wait_dev = (
        abs(e3_wait["transfer_wait"] - IDEAL_TRANSFER)
        if e3_wait["transfer_wait"] is not None
        else None
    )

    checks.append(
        make_check(
            "E3 Less Waiting chooses transfer timing closer to the six-step ideal",
            "e3_waiting_network",
            "The transfer-timing profile should reduce absolute deviation from the preferred six-step connection.",
            fast_dev is not None
            and wait_dev is not None
            and wait_dev < fast_dev,
            {
                "ideal_transfer": IDEAL_TRANSFER,
                "fastest_wait": e3_fast["transfer_wait"],
                "fastest_deviation": fast_dev,
                "less_waiting_wait": e3_wait["transfer_wait"],
                "less_waiting_deviation": wait_dev,
            },
        )
    )

    # E4: journey time versus route simplicity.
    e4_fast = get(rows, "e4_simple_complex", "fastest")
    e4_simple = get(rows, "e4_simple_complex", "simple")

    checks.append(
        make_check(
            "E4 Fastest is quicker than Simple Journey",
            "e4_simple_complex",
            "Fastest should trade greater route complexity for a shorter journey.",
            is_optimum(e4_fast)
            and is_optimum(e4_simple)
            and e4_fast["journey_time"] is not None
            and e4_simple["journey_time"] is not None
            and e4_fast["journey_time"] < e4_simple["journey_time"],
            {
                "fastest_journey": e4_fast["journey_time"],
                "simple_journey": e4_simple["journey_time"],
            },
        )
    )

    checks.append(
        make_check(
            "E4 Simple Journey uses fewer turns than Fastest",
            "e4_simple_complex",
            "Simple Journey should reduce route turns relative to Fastest.",
            e4_fast["turns"] is not None
            and e4_simple["turns"] is not None
            and e4_simple["turns"] < e4_fast["turns"],
            {
                "fastest_turns": e4_fast["turns"],
                "simple_turns": e4_simple["turns"],
            },
        )
    )

    # E5: integrated mixed-preference trade-off.
    e5_fast = get(rows, "e5_mixed_preferences", "fastest")
    e5_few = get(rows, "e5_mixed_preferences", "fewest_transfers")

    checks.append(
        make_check(
            "E5 Fastest chooses a shorter journey than Fewer Transfers",
            "e5_mixed_preferences",
            "The integrated environment should preserve the journey-time versus transfer-count trade-off.",
            is_optimum(e5_fast)
            and is_optimum(e5_few)
            and e5_fast["journey_time"] is not None
            and e5_few["journey_time"] is not None
            and e5_fast["journey_time"] < e5_few["journey_time"],
            {
                "fastest_journey": e5_fast["journey_time"],
                "fewest_transfers_journey": e5_few["journey_time"],
            },
        )
    )

    checks.append(
        make_check(
            "E5 Fewer Transfers reduces train changes relative to Fastest",
            "e5_mixed_preferences",
            "The integrated transfer-focused profile should use fewer transfers than Fastest.",
            e5_fast["transfers"] is not None
            and e5_few["transfers"] is not None
            and e5_few["transfers"] < e5_fast["transfers"],
            {
                "fastest_transfers": e5_fast["transfers"],
                "fewest_transfers_transfers": e5_few["transfers"],
            },
        )
    )

    passed = sum(1 for check in checks if check["pass"])

    payload = {
        "scope": "controlled relational preference checks for E1-E5",
        "method": (
            "Checks are recomputed from all_runs.csv and compare profile behaviour "
            "relationally rather than against hardcoded timetable values."
        ),
        "ideal_transfer_time": IDEAL_TRANSFER,
        "checks": checks,
        "passed": passed,
        "total": len(checks),
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=" * 72)
    print("RS42 RELATIONAL SEMANTIC RECHECK")
    print("=" * 72)

    for index, check in enumerate(checks, start=1):
        marker = "PASS" if check["pass"] else "FAIL"
        print(f"[{index:02d}/10] {marker} - {check['name']}")

    print()
    print(f"RESULT: {passed}/{len(checks)} PASS")
    print(f"Saved: {OUTPUT_JSON.relative_to(ROOT)}")

    if passed != len(checks):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
