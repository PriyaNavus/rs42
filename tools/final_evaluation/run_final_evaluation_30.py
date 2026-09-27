"""
RS42 FINAL SIX-ENVIRONMENT EVALUATION

Runs:
    6 canonical environments x 5 canonical profiles = 30 Clingo runs

Environments:
    E1 e1_fast_slow
    E2 e2_transfer_network
    E3 e3_waiting_network
    E4 e4_simple_complex
    E5 e5_mixed_preferences
    E6 e6_shared_conflict

Profiles are read DIRECTLY from asp/profiles/*.lp:
    fastest
    least_waiting
    fewest_transfers
    simple
    balanced

E1-E5:
    controlled passenger/preference experiments

E6:
    multi-train infrastructure robustness experiment.
    It is intentionally NOT used for passenger-transfer interpretation.

The runner also performs ASP -> Flatland validation for all six canonical
environment pickles and writes a consolidated completion_status.json.

Run from the repository root:

    conda activate flatlandrs42
    python tools/final_evaluation/run_final_evaluation_30.py

Optional:
    --skip-flatland-validation
    --timeout 180

The E4 Less Waiting case automatically receives at least 360 seconds.
E6 cases automatically receive at least 300 seconds.
"""

from __future__ import print_function

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

EVAL_ROOT = ROOT / "experiments" / "final_evaluation"
RESULTS_DIR = EVAL_ROOT / "results"
RUNS_DIR = RESULTS_DIR / "runs"
SUMMARY_DIR = RESULTS_DIR / "summaries"
VALIDATION_DIR = RESULTS_DIR / "validation"
RAW_DIR = EVAL_ROOT / "raw"
LOG_DIR = EVAL_ROOT / "logs"
RUNTIME_CONFIG_DIR = EVAL_ROOT / "configs" / "runtime"

ALL_RUNS_CSV = RUNS_DIR / "all_runs.csv"
ALL_RUNS_JSON = SUMMARY_DIR / "all_runs.json"
PRIMARY_CHECKS_JSON = SUMMARY_DIR / "primary_checks.json"
ROBUSTNESS_CHECKS_JSON = SUMMARY_DIR / "robustness_checks.json"
COMPLETION_JSON = SUMMARY_DIR / "completion_status.json"
MANIFEST_JSON = SUMMARY_DIR / "evaluation_manifest.json"
VALIDATION_CSV = VALIDATION_DIR / "environment_validation.csv"

ENVIRONMENTS = [
    {
        "stem": "e1_fast_slow",
        "label": "E1 - Fast vs Slow",
        "role": "controlled_preference",
    },
    {
        "stem": "e2_transfer_network",
        "label": "E2 - Transfer Network",
        "role": "controlled_preference",
    },
    {
        "stem": "e3_waiting_network",
        "label": "E3 - Waiting Network",
        "role": "controlled_preference",
    },
    {
        "stem": "e4_simple_complex",
        "label": "E4 - Simple vs Complex",
        "role": "controlled_preference",
    },
    {
        "stem": "e5_mixed_preferences",
        "label": "E5 - Mixed Preferences",
        "role": "integrated_preference",
    },
    {
        "stem": "e6_shared_conflict",
        "label": "E6 - Infrastructure Robustness",
        "role": "infrastructure_robustness",
    },
]

PROFILES = [
    "fastest",
    "least_waiting",
    "fewest_transfers",
    "simple",
    "balanced",
]

PROFILE_LABELS = {
    "fastest": "Fastest",
    "least_waiting": "Less Waiting",
    "fewest_transfers": "Fewer Transfers",
    "simple": "Simple Journey",
    "balanced": "Balanced",
}

PROFILE_FILES = {
    "fastest": ROOT / "asp" / "profiles" / "profile_fastest.lp",
    "least_waiting": ROOT / "asp" / "profiles" / "profile_least_waiting.lp",
    "fewest_transfers": ROOT / "asp" / "profiles" / "profile_fewest_transfers.lp",
    "simple": ROOT / "asp" / "profiles" / "profile_simple_journey.lp",
    "balanced": ROOT / "asp" / "profiles" / "profile_balanced.lp",
}

CONNECTION = ROOT / "asp" / "custom" / "connection.lp"
ENCODING = ROOT / "asp" / "custom" / "encoding.lp"
WAYPOINT = ROOT / "asp" / "custom" / "waypoint.lp"
PASSENGER = ROOT / "asp" / "custom" / "passenger_transfer.lp"
VISUAL = ROOT / "asp" / "custom" / "visual.lp"
OBJECTIVES = ROOT / "asp" / "custom" / "objectives.lp"

COLLECTOR = RUNTIME_CONFIG_DIR / "metric_collector_30run.lp"

COLLECTOR_TEXT = r"""% RS42 six-environment final metric collector

#show chosen_leg/7.
#show passenger_journey_time/2.
#show passenger_transfer_wait/2.
#show transfer_count/2.
#show passenger_uses_train/2.
#show uses_train/3.

#show travel_time/2.
#show waiting_time/2.
#show wait_time/2.
#show turns/2.
#show waypoint_time/2.
"""


CSV_FIELDS = [
    "environment",
    "environment_label",
    "evaluation_role",
    "metric_scope",
    "profile",
    "profile_label",
    "status",
    "runtime_seconds",
    "journey_time",
    "transfer_wait",
    "transfers",
    "turns",
    "train_travel_time_sum",
    "train_wait_time_sum",
    "selected_trains",
    "chosen_legs",
    "optimization_cost",
    "timeout_seconds",
]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Base Clingo timeout in seconds. Default: 180.",
    )
    parser.add_argument(
        "--skip-flatland-validation",
        action="store_true",
        help="Skip the final six-environment solve.py validation.",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Do not archive the previous results directory before this run.",
    )
    return parser.parse_args()


def ensure_dirs():
    for folder in [
        RUNS_DIR,
        SUMMARY_DIR,
        VALIDATION_DIR,
        RAW_DIR,
        LOG_DIR,
        RUNTIME_CONFIG_DIR,
    ]:
        folder.mkdir(parents=True, exist_ok=True)

    COLLECTOR.write_text(
        COLLECTOR_TEXT,
        encoding="utf-8",
    )


def require_files():
    required = [
        CONNECTION,
        ENCODING,
        WAYPOINT,
        PASSENGER,
        VISUAL,
        OBJECTIVES,
    ]

    required.extend(PROFILE_FILES.values())

    for env_info in ENVIRONMENTS:
        stem = env_info["stem"]
        required.extend(
            [
                ROOT / "envs" / "lp" / (stem + ".lp"),
                ROOT / "envs" / "pkl" / (stem + ".pkl"),
                ROOT / "asp" / "scenarios" / (stem + ".lp"),
            ]
        )

    missing = [
        str(path)
        for path in required
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Missing final-evaluation files:\n"
            + "\n".join(missing)
        )


def archive_previous_results():
    if not RESULTS_DIR.exists():
        return None

    existing_files = [
        path
        for path in RESULTS_DIR.rglob("*")
        if path.is_file()
    ]

    if not existing_files:
        return None

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    archive = (
        EVAL_ROOT
        / "_archive"
        / ("results_before_30run_" + timestamp)
    )

    archive.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copytree(
        str(RESULTS_DIR),
        str(archive),
    )

    return archive


def timeout_for(env, profile, base):
    value = max(int(base), 90)

    if env == "e4_simple_complex" and profile == "least_waiting":
        value = max(value, 360)

    if env == "e5_mixed_preferences":
        value = max(value, 180)

    if env == "e6_shared_conflict":
        value = max(value, 300)

    return value


def parse_passenger_metric(atoms, predicate):
    pattern = re.compile(
        r"^{}\(([^,]+),(-?\d+)\)$".format(
            re.escape(predicate)
        )
    )

    for atom in atoms:
        match = pattern.match(atom)
        if match:
            return int(match.group(2))

    return None


def parse_train_map(atoms, predicate):
    pattern = re.compile(
        r"^{}\((\d+),(-?\d+)\)$".format(
            re.escape(predicate)
        )
    )

    result = {}

    for atom in atoms:
        match = pattern.match(atom)
        if match:
            result[int(match.group(1))] = int(match.group(2))

    return result


def parse_wait_map(atoms):
    # Current backend uses waiting_time/2.
    # wait_time/2 is retained for compatibility with older outputs.
    current = parse_train_map(
        atoms,
        "waiting_time",
    )
    legacy = parse_train_map(
        atoms,
        "wait_time",
    )

    merged = dict(legacy)
    merged.update(current)
    return merged


def parse_chosen_legs(atoms):
    return sorted(
        atom
        for atom in atoms
        if atom.startswith("chosen_leg(")
    )


def selected_train_ids(atoms, chosen):
    ids = []

    chosen_pattern = re.compile(
        r"^chosen_leg\([^,]+,\d+,(\d+),"
    )

    for atom in chosen:
        match = chosen_pattern.match(atom)
        if match:
            ids.append(int(match.group(1)))

    if ids:
        return sorted(set(ids))

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
            match = pattern.match(atom)
            if match:
                ids.append(int(match.group(1)))
                break

    return sorted(set(ids))


def metric_sum(metric_map, train_ids):
    values = [
        metric_map[train_id]
        for train_id in train_ids
        if train_id in metric_map
    ]

    if not values:
        return None

    return sum(values)


def empty_row(
    env_info,
    profile,
    status,
    runtime,
    timeout_seconds,
):
    return {
        "environment": env_info["stem"],
        "environment_label": env_info["label"],
        "evaluation_role": env_info["role"],
        "metric_scope": (
            "system_all_trains"
            if env_info["role"] == "infrastructure_robustness"
            else "passenger_or_selected_service"
        ),
        "profile": profile,
        "profile_label": PROFILE_LABELS[profile],
        "status": status,
        "runtime_seconds": round(runtime, 3),
        "journey_time": None,
        "transfer_wait": None,
        "transfers": None,
        "turns": None,
        "train_travel_time_sum": None,
        "train_wait_time_sum": None,
        "selected_trains": "",
        "chosen_legs": "",
        "optimization_cost": "",
        "timeout_seconds": timeout_seconds,
    }


def run_one(env_info, profile, base_timeout):
    env = env_info["stem"]
    timeout_seconds = timeout_for(
        env,
        profile,
        base_timeout,
    )

    env_lp = ROOT / "envs" / "lp" / (env + ".lp")
    scenario = ROOT / "asp" / "scenarios" / (env + ".lp")
    profile_file = PROFILE_FILES[profile]

    cmd = [
        sys.executable,
        "-m",
        "clingo",
        str(env_lp),
        str(CONNECTION),
        str(ENCODING),
        str(WAYPOINT),
        str(PASSENGER),
        str(VISUAL),
        str(OBJECTIVES),
        str(profile_file),
        str(scenario),
        str(COLLECTOR),
        "--outf=2",
        "--opt-mode=opt",
    ]

    start = time.perf_counter()

    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        runtime = time.perf_counter() - start

        stdout = exc.stdout or ""
        stderr = exc.stderr or ""

        if isinstance(stdout, bytes):
            stdout = stdout.decode(
                "utf-8",
                errors="replace",
            )

        if isinstance(stderr, bytes):
            stderr = stderr.decode(
                "utf-8",
                errors="replace",
            )

        RAW_DIR.joinpath(
            "{}__{}__30run.json".format(
                env,
                profile,
            )
        ).write_text(
            stdout,
            encoding="utf-8",
        )

        LOG_DIR.joinpath(
            "{}__{}__30run.stderr.txt".format(
                env,
                profile,
            )
        ).write_text(
            stderr,
            encoding="utf-8",
        )

        return empty_row(
            env_info,
            profile,
            "TIMEOUT",
            runtime,
            timeout_seconds,
        )

    runtime = time.perf_counter() - start

    raw_path = RAW_DIR / (
        "{}__{}__30run.json".format(
            env,
            profile,
        )
    )
    stderr_path = LOG_DIR / (
        "{}__{}__30run.stderr.txt".format(
            env,
            profile,
        )
    )

    raw_path.write_text(
        result.stdout,
        encoding="utf-8",
    )
    stderr_path.write_text(
        result.stderr,
        encoding="utf-8",
    )

    try:
        data = json.loads(result.stdout)
    except Exception:
        return empty_row(
            env_info,
            profile,
            "BAD_JSON",
            runtime,
            timeout_seconds,
        )

    status = str(
        data.get("Result", "UNKNOWN")
    ).upper()

    calls = data.get("Call", [])
    witnesses = (
        calls[-1].get("Witnesses", [])
        if calls
        else []
    )

    if not witnesses:
        return empty_row(
            env_info,
            profile,
            status,
            runtime,
            timeout_seconds,
        )

    witness = witnesses[-1]
    atoms = witness.get("Value", [])
    costs = witness.get("Costs", [])

    chosen = parse_chosen_legs(atoms)
    selected = selected_train_ids(
        atoms,
        chosen,
    )

    turns_map = parse_train_map(
        atoms,
        "turns",
    )
    travel_map = parse_train_map(
        atoms,
        "travel_time",
    )
    wait_map = parse_wait_map(atoms)

    # Legacy E4 has historically required the all-train fallback.
    if env == "e4_simple_complex" and not selected:
        selected = sorted(
            set(turns_map)
            | set(travel_map)
            | set(wait_map)
        )

    # E6 is explicitly a system-level robustness environment.
    # It has no passenger OD scenario, so report aggregate train metrics.
    if env == "e6_shared_conflict":
        selected = sorted(
            set(turns_map)
            | set(travel_map)
            | set(wait_map)
        )

    journey = parse_passenger_metric(
        atoms,
        "passenger_journey_time",
    )
    transfer_wait = parse_passenger_metric(
        atoms,
        "passenger_transfer_wait",
    )
    transfers = parse_passenger_metric(
        atoms,
        "transfer_count",
    )

    selected_turns = metric_sum(
        turns_map,
        selected,
    )
    selected_travel = metric_sum(
        travel_map,
        selected,
    )
    selected_wait = metric_sum(
        wait_map,
        selected,
    )

    # Preserve legacy E4 interpretation.
    if env == "e4_simple_complex":
        if journey is None:
            journey = selected_travel
        if transfer_wait is None:
            transfer_wait = selected_wait

    return {
        "environment": env,
        "environment_label": env_info["label"],
        "evaluation_role": env_info["role"],
        "metric_scope": (
            "system_all_trains"
            if env == "e6_shared_conflict"
            else "passenger_or_selected_service"
        ),
        "profile": profile,
        "profile_label": PROFILE_LABELS[profile],
        "status": status,
        "runtime_seconds": round(runtime, 3),
        "journey_time": journey,
        "transfer_wait": transfer_wait,
        "transfers": transfers,
        "turns": selected_turns,
        "train_travel_time_sum": selected_travel,
        "train_wait_time_sum": selected_wait,
        "selected_trains": ",".join(
            str(train_id)
            for train_id in selected
        ),
        "chosen_legs": " | ".join(chosen),
        "optimization_cost": ",".join(
            str(cost)
            for cost in costs
        ),
        "timeout_seconds": timeout_seconds,
    }


def rows_by_key(rows):
    return {
        (
            row["environment"],
            row["profile"],
        ): row
        for row in rows
    }


def exact_signature_check(
    rows,
    name,
    environment,
    profile,
    expected,
    description,
):
    by = rows_by_key(rows)
    row = by[(environment, profile)]

    observed = {}
    passed = True

    for key, expected_value in expected.items():
        observed[key] = row.get(key)

        if key == "selected_train_contains":
            selected = {
                token
                for token in str(
                    row.get(
                        "selected_trains",
                        "",
                    )
                ).split(",")
                if token
            }

            if str(expected_value) not in selected:
                passed = False
        else:
            if row.get(key) != expected_value:
                passed = False

    if row.get("status") != "OPTIMUM FOUND":
        passed = False

    return {
        "name": name,
        "environment": environment,
        "profile": profile,
        "description": description,
        "expected": expected,
        "observed": observed,
        "status": row.get("status"),
        "pass": passed,
    }


def comparative_check(
    rows,
    name,
    environment,
    left_profile,
    left_metric,
    operator,
    right_profile,
    right_metric,
    description,
):
    by = rows_by_key(rows)

    left_row = by[
        (
            environment,
            left_profile,
        )
    ]
    right_row = by[
        (
            environment,
            right_profile,
        )
    ]

    left = left_row.get(left_metric)
    right = right_row.get(right_metric)

    passed = False

    if (
        left_row.get("status") == "OPTIMUM FOUND"
        and right_row.get("status") == "OPTIMUM FOUND"
        and left is not None
        and right is not None
    ):
        if operator == "<":
            passed = left < right
        elif operator == ">":
            passed = left > right
        elif operator == "==":
            passed = left == right
        else:
            raise ValueError(operator)

    return {
        "name": name,
        "environment": environment,
        "description": description,
        "left_profile": left_profile,
        "left_metric": left_metric,
        "left_value": left,
        "operator": operator,
        "right_profile": right_profile,
        "right_metric": right_metric,
        "right_value": right,
        "pass": passed,
    }


def build_primary_checks(rows):
    checks = []

    checks.append(
        exact_signature_check(
            rows,
            "E1 Fastest selects the known fast service",
            "e1_fast_slow",
            "fastest",
            {
                "journey_time": 10,
                "selected_train_contains": 0,
            },
            (
                "Curved E1 preserves the isolated fast-vs-slow "
                "travel-time result."
            ),
        )
    )

    checks.append(
        exact_signature_check(
            rows,
            "E2 Fastest selects the multi-transfer route",
            "e2_transfer_network",
            "fastest",
            {
                "journey_time": 14,
                "transfers": 2,
            },
            (
                "Fastest should accept two transfers for the "
                "14-step passenger journey."
            ),
        )
    )

    checks.append(
        exact_signature_check(
            rows,
            "E2 Fewer Transfers selects direct service",
            "e2_transfer_network",
            "fewest_transfers",
            {
                "journey_time": 18,
                "transfers": 0,
            },
            (
                "Fewer Transfers should accept the longer direct "
                "18-step journey."
            ),
        )
    )

    checks.append(
        exact_signature_check(
            rows,
            "E3 Fastest accepts the longer connection wait",
            "e3_waiting_network",
            "fastest",
            {
                "journey_time": 11,
                "transfer_wait": 5,
                "transfers": 1,
            },
            (
                "Fastest should select the 11-step itinerary even "
                "though its connection wait is five."
            ),
        )
    )

    checks.append(
        exact_signature_check(
            rows,
            "E3 Less Waiting selects the low-wait itinerary",
            "e3_waiting_network",
            "least_waiting",
            {
                "journey_time": 13,
                "transfer_wait": 1,
                "transfers": 1,
            },
            (
                "Less Waiting should select the 13-step itinerary "
                "with one unit of connection wait."
            ),
        )
    )

    checks.append(
        comparative_check(
            rows,
            "E4 Fastest is quicker than Simple Journey",
            "e4_simple_complex",
            "fastest",
            "journey_time",
            "<",
            "simple",
            "journey_time",
            (
                "The original E4 should preserve the travel-time "
                "versus route-simplicity trade-off."
            ),
        )
    )

    checks.append(
        comparative_check(
            rows,
            "E4 Simple Journey uses fewer turns",
            "e4_simple_complex",
            "simple",
            "turns",
            "<",
            "fastest",
            "turns",
            (
                "Simple Journey should reduce route turns relative "
                "to Fastest."
            ),
        )
    )

    checks.append(
        exact_signature_check(
            rows,
            "E5 Fastest selects alternative A",
            "e5_mixed_preferences",
            "fastest",
            {
                "journey_time": 14,
                "transfer_wait": 2,
                "transfers": 2,
            },
            (
                "The integrated Fastest alternative is the "
                "14-step, two-transfer service."
            ),
        )
    )

    checks.append(
        exact_signature_check(
            rows,
            "E5 Less Waiting selects direct alternative B",
            "e5_mixed_preferences",
            "least_waiting",
            {
                "journey_time": 18,
                "transfer_wait": 0,
                "transfers": 0,
            },
            (
                "The direct alternative has zero transfer wait."
            ),
        )
    )

    checks.append(
        exact_signature_check(
            rows,
            "E5 Fewer Transfers selects direct alternative B",
            "e5_mixed_preferences",
            "fewest_transfers",
            {
                "journey_time": 18,
                "transfers": 0,
            },
            (
                "The direct alternative is the zero-transfer route."
            ),
        )
    )

    return checks


def build_robustness_checks(rows):
    by = rows_by_key(rows)
    checks = []

    for profile in PROFILES:
        row = by[
            (
                "e6_shared_conflict",
                profile,
            )
        ]

        checks.append(
            {
                "name": (
                    "E6 {} reaches an optimum".format(
                        PROFILE_LABELS[profile]
                    )
                ),
                "environment": "e6_shared_conflict",
                "profile": profile,
                "status": row.get("status"),
                "runtime_seconds": row.get(
                    "runtime_seconds"
                ),
                "metric_scope": row.get(
                    "metric_scope"
                ),
                "pass": (
                    row.get("status")
                    == "OPTIMUM FOUND"
                ),
            }
        )

    return checks


def run_flatland_validation(env_info):
    stem = env_info["stem"]
    pkl_path = (
        ROOT
        / "envs"
        / "pkl"
        / (stem + ".pkl")
    )

    start = time.perf_counter()

    try:
        result = subprocess.run(
            [
                sys.executable,
                "solve.py",
                str(pkl_path),
                "--no-render",
            ],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=360,
        )

        runtime = time.perf_counter() - start
        output = (
            (result.stdout or "")
            + (result.stderr or "")
        )

        passed = (
            result.returncode == 0
            and "RS42_VALIDATION: PASS" in output
        )

        status = (
            "PASS"
            if passed
            else "FAIL"
        )

        returncode = result.returncode

    except subprocess.TimeoutExpired as exc:
        runtime = time.perf_counter() - start

        stdout = exc.stdout or ""
        stderr = exc.stderr or ""

        if isinstance(stdout, bytes):
            stdout = stdout.decode(
                "utf-8",
                errors="replace",
            )

        if isinstance(stderr, bytes):
            stderr = stderr.decode(
                "utf-8",
                errors="replace",
            )

        output = stdout + stderr
        status = "TIMEOUT"
        returncode = None

    log_path = (
        LOG_DIR
        / (
            stem
            + "__flatland_validation_30run.txt"
        )
    )

    log_path.write_text(
        output,
        encoding="utf-8",
    )

    return {
        "environment": stem,
        "environment_label": env_info["label"],
        "evaluation_role": env_info["role"],
        "validation": status,
        "runtime_seconds": round(runtime, 3),
        "returncode": returncode,
        "log": str(
            log_path.relative_to(ROOT)
        ),
    }


def write_csv(path, rows, fields):
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(
    rows,
    primary_checks,
    robustness_checks,
    validation_rows,
    archived_results,
):
    write_csv(
        ALL_RUNS_CSV,
        rows,
        CSV_FIELDS,
    )

    ALL_RUNS_JSON.write_text(
        json.dumps(
            {
                "evaluation": (
                    "RS42 final six-environment evaluation"
                ),
                "version": "6env_30run_v1",
                "profile_source": (
                    "canonical asp/profiles/*.lp"
                ),
                "environment_count": 6,
                "profile_count": 5,
                "run_count": len(rows),
                "environments": ENVIRONMENTS,
                "profiles": [
                    {
                        "id": profile,
                        "label": PROFILE_LABELS[profile],
                        "file": str(
                            PROFILE_FILES[profile]
                            .relative_to(ROOT)
                        ),
                    }
                    for profile in PROFILES
                ],
                "runs": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    PRIMARY_CHECKS_JSON.write_text(
        json.dumps(
            {
                "scope": (
                    "controlled preference checks for E1-E5"
                ),
                "checks": primary_checks,
                "passed": sum(
                    1
                    for check in primary_checks
                    if check["pass"]
                ),
                "total": len(primary_checks),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    ROBUSTNESS_CHECKS_JSON.write_text(
        json.dumps(
            {
                "scope": (
                    "E6 multi-train infrastructure robustness"
                ),
                "interpretation": (
                    "solver/profile robustness only; "
                    "not passenger-transfer preference evidence"
                ),
                "checks": robustness_checks,
                "passed": sum(
                    1
                    for check in robustness_checks
                    if check["pass"]
                ),
                "total": len(robustness_checks),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    if validation_rows:
        write_csv(
            VALIDATION_CSV,
            validation_rows,
            [
                "environment",
                "environment_label",
                "evaluation_role",
                "validation",
                "runtime_seconds",
                "returncode",
                "log",
            ],
        )

    optimum_count = sum(
        1
        for row in rows
        if row["status"] == "OPTIMUM FOUND"
    )

    primary_passed = sum(
        1
        for check in primary_checks
        if check["pass"]
    )

    robustness_passed = sum(
        1
        for check in robustness_checks
        if check["pass"]
    )

    validation_passed = sum(
        1
        for row in validation_rows
        if row["validation"] == "PASS"
    )

    validations_complete = (
        len(validation_rows) == len(ENVIRONMENTS)
    )

    overall_pass = (
        optimum_count == 30
        and primary_passed == len(primary_checks)
        and robustness_passed == len(robustness_checks)
        and validations_complete
        and validation_passed == 6
    )

    completion = {
        "evaluation": "RS42 six-environment final evaluation",
        "version": "6env_30run_v1",
        "canonical_profiles_used": True,
        "total_runs": len(rows),
        "optimum_found": optimum_count,
        "primary_checks_passed": primary_passed,
        "primary_checks_total": len(primary_checks),
        "e6_robustness_passed": robustness_passed,
        "e6_robustness_total": len(robustness_checks),
        "flatland_validation_passed": validation_passed,
        "flatland_validation_total": len(validation_rows),
        "expected_flatland_validation_total": 6,
        "flatland_validation_skipped": (
            not validations_complete
        ),
        "overall_status": (
            "PASS"
            if overall_pass
            else "INCOMPLETE_OR_FAIL"
        ),
        "previous_results_archive": (
            str(archived_results.relative_to(ROOT))
            if archived_results is not None
            else None
        ),
    }

    COMPLETION_JSON.write_text(
        json.dumps(
            completion,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    MANIFEST_JSON.write_text(
        json.dumps(
            {
                "version": "6env_30run_v1",
                "environment_order": [
                    item["stem"]
                    for item in ENVIRONMENTS
                ],
                "environment_roles": {
                    item["stem"]: item["role"]
                    for item in ENVIRONMENTS
                },
                "profile_order": PROFILES,
                "profile_files": {
                    profile: str(
                        PROFILE_FILES[profile]
                        .relative_to(ROOT)
                    )
                    for profile in PROFILES
                },
                "e6_interpretation": (
                    "infrastructure robustness; "
                    "not passenger transfer evidence"
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return completion


def main():
    args = parse_args()

    ensure_dirs()
    require_files()

    archived_results = None

    if not args.no_archive:
        archived_results = archive_previous_results()

    print("RS42 FINAL SIX-ENVIRONMENT EVALUATION")
    print("6 environments x 5 canonical profiles = 30 runs")
    print("Profile source: asp/profiles/*.lp")
    print()

    if archived_results is not None:
        print(
            "Previous result summaries archived to:"
        )
        print(
            "  {}".format(
                archived_results.relative_to(ROOT)
            )
        )
        print()

    rows = []
    total = (
        len(ENVIRONMENTS)
        * len(PROFILES)
    )
    run_number = 0

    for env_info in ENVIRONMENTS:
        print(
            "=== {} ===".format(
                env_info["label"]
            )
        )

        if (
            env_info["role"]
            == "infrastructure_robustness"
        ):
            print(
                "    scope: system-level solver robustness"
            )

        for profile in PROFILES:
            run_number += 1

            print(
                "[{:02d}/{:02d}] {:<17} ... ".format(
                    run_number,
                    total,
                    PROFILE_LABELS[profile],
                ),
                end="",
                flush=True,
            )

            row = run_one(
                env_info,
                profile,
                args.timeout,
            )

            rows.append(row)

            print(
                "{} | journey={} wait={} transfers={} "
                "turns={} | {:.3f}s".format(
                    row["status"],
                    row["journey_time"],
                    row["transfer_wait"],
                    row["transfers"],
                    row["turns"],
                    row["runtime_seconds"],
                )
            )

        print()

    primary_checks = build_primary_checks(
        rows
    )
    robustness_checks = build_robustness_checks(
        rows
    )

    print("CONTROLLED CHECKS (E1-E5)")
    primary_passed = 0

    for check in primary_checks:
        mark = (
            "PASS"
            if check["pass"]
            else "FAIL"
        )

        if check["pass"]:
            primary_passed += 1

        print(
            "  {} - {}".format(
                mark,
                check["name"],
            )
        )

    print(
        "Controlled checks: {}/{}".format(
            primary_passed,
            len(primary_checks),
        )
    )
    print()

    e6_passed = sum(
        1
        for check in robustness_checks
        if check["pass"]
    )

    print(
        "E6 ROBUSTNESS: {}/{} profiles OPTIMUM FOUND".format(
            e6_passed,
            len(robustness_checks),
        )
    )
    print()

    validation_rows = []

    if not args.skip_flatland_validation:
        print(
            "ASP -> FLATLAND VALIDATION"
        )

        for env_info in ENVIRONMENTS:
            print(
                "  {} ... ".format(
                    env_info["stem"]
                ),
                end="",
                flush=True,
            )

            result = run_flatland_validation(
                env_info
            )
            validation_rows.append(result)

            print(
                result["validation"]
            )

        validation_passed = sum(
            1
            for item in validation_rows
            if item["validation"] == "PASS"
        )

        print(
            "Flatland validation: {}/{} PASS".format(
                validation_passed,
                len(validation_rows),
            )
        )
        print()
    else:
        print(
            "Flatland validation skipped by command-line option."
        )
        print()

    completion = write_outputs(
        rows,
        primary_checks,
        robustness_checks,
        validation_rows,
        archived_results,
    )

    optimum_count = sum(
        1
        for row in rows
        if row["status"] == "OPTIMUM FOUND"
    )

    print("FINAL SUMMARY")
    print(
        "  Optimization runs: {}/30 OPTIMUM FOUND".format(
            optimum_count
        )
    )
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

    if validation_rows:
        print(
            "  Flatland validation: {}/6 PASS".format(
                completion[
                    "flatland_validation_passed"
                ]
            )
        )

    print(
        "  FINAL STATUS: {}".format(
            completion["overall_status"]
        )
    )

    print()
    print("Saved:")
    print(
        "  {}".format(
            ALL_RUNS_CSV.relative_to(ROOT)
        )
    )
    print(
        "  {}".format(
            ALL_RUNS_JSON.relative_to(ROOT)
        )
    )
    print(
        "  {}".format(
            PRIMARY_CHECKS_JSON.relative_to(ROOT)
        )
    )
    print(
        "  {}".format(
            ROBUSTNESS_CHECKS_JSON.relative_to(ROOT)
        )
    )
    print(
        "  {}".format(
            COMPLETION_JSON.relative_to(ROOT)
        )
    )

    if validation_rows:
        print(
            "  {}".format(
                VALIDATION_CSV.relative_to(ROOT)
            )
        )

    if completion["overall_status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(
            "\nEvaluation interrupted.",
            file=sys.stderr,
        )
        raise SystemExit(130)
    except Exception as exc:
        print(
            "ERROR: {}".format(exc),
            file=sys.stderr,
        )
        raise SystemExit(1)
