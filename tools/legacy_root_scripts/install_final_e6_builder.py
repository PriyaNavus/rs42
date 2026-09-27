"""
Install the final RS42 E6 builder.

Run from the RS42 repository root:

    python install_final_e6_builder.py

Then run:

    python tools\\final_evaluation\\build_e6_shared_conflict.py --overwrite
"""

from __future__ import print_function

import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd().resolve()
TARGET = ROOT / "tools" / "final_evaluation" / "build_e6_shared_conflict.py"

BUILDER = r"""from __future__ import annotations

import argparse
import json
import pickle
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SOURCE_STEM = "test"
TARGET_STEM = "e6_shared_conflict"

SRC_PKL = ROOT / "envs" / "pkl" / (SOURCE_STEM + ".pkl")
SRC_LP = ROOT / "envs" / "lp" / (SOURCE_STEM + ".lp")
SRC_PNG = ROOT / "envs" / "png" / (SOURCE_STEM + ".png")
SRC_SCENARIO = ROOT / "asp" / "scenarios" / (SOURCE_STEM + ".lp")

OUT_PKL = ROOT / "envs" / "pkl" / (TARGET_STEM + ".pkl")
OUT_LP = ROOT / "envs" / "lp" / (TARGET_STEM + ".lp")
OUT_PNG = ROOT / "envs" / "png" / (TARGET_STEM + ".png")
OUT_SCENARIO = ROOT / "asp" / "scenarios" / (TARGET_STEM + ".lp")
OUT_META = (
    ROOT
    / "experiments"
    / "final_evaluation"
    / "configs"
    / (TARGET_STEM + ".json")
)
OUT_LOG = (
    ROOT
    / "experiments"
    / "final_evaluation"
    / "logs"
    / (TARGET_STEM + "_validation.txt")
)

OUTPUTS = [
    OUT_PKL,
    OUT_LP,
    OUT_PNG,
    OUT_SCENARIO,
    OUT_META,
]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def require_sources():
    required = [
        SRC_PKL,
        SRC_LP,
        SRC_SCENARIO,
    ]

    missing = [
        str(path)
        for path in required
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Missing validated RS42 test-environment assets:\\n"
            + "\\n".join(missing)
        )


def run_validation(pkl_path, timeout=300):
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
        timeout=timeout,
    )

    output = (result.stdout or "") + (result.stderr or "")

    passed = (
        result.returncode == 0
        and "RS42_VALIDATION: PASS" in output
    )

    return passed, output


def inspect_source_pickle():
    with SRC_PKL.open("rb") as handle:
        env = pickle.load(handle)

    agents = list(getattr(env, "agents", []))

    if len(agents) < 2:
        raise RuntimeError(
            "test.pkl must contain at least 2 trains; found {}."
            .format(len(agents))
        )

    details = []

    for agent_id, agent in enumerate(agents):
        details.append(
            {
                "train": agent_id,
                "start": (
                    list(agent.initial_position)
                    if agent.initial_position is not None
                    else None
                ),
                "target": (
                    list(agent.target)
                    if agent.target is not None
                    else None
                ),
                "initial_direction": (
                    int(agent.initial_direction)
                    if agent.initial_direction is not None
                    else None
                ),
                "earliest_departure": getattr(
                    agent,
                    "earliest_departure",
                    None,
                ),
                "latest_arrival": getattr(
                    agent,
                    "latest_arrival",
                    None,
                ),
            }
        )

    return details


def archive_existing():
    existing = [
        path
        for path in OUTPUTS
        if path.exists()
    ]

    if not existing:
        return None

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    archive_dir = (
        ROOT
        / "experiments"
        / "_archive"
        / ("e6_before_validated_promotion_" + timestamp)
    )

    archive_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    for path in existing:
        shutil.copy2(
            str(path),
            str(archive_dir / path.name),
        )

    return archive_dir


def copy_assets():
    for parent in [
        OUT_PKL.parent,
        OUT_LP.parent,
        OUT_PNG.parent,
        OUT_SCENARIO.parent,
        OUT_META.parent,
        OUT_LOG.parent,
    ]:
        parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    shutil.copy2(str(SRC_PKL), str(OUT_PKL))
    shutil.copy2(str(SRC_LP), str(OUT_LP))
    shutil.copy2(str(SRC_SCENARIO), str(OUT_SCENARIO))

    if SRC_PNG.exists():
        shutil.copy2(str(SRC_PNG), str(OUT_PNG))


def main():
    args = parse_args()
    require_sources()

    existing = [
        path
        for path in OUTPUTS
        if path.exists()
    ]

    if existing and not args.overwrite:
        raise FileExistsError(
            "Older E6 artifacts exist. Run with --overwrite."
        )

    print("E6 FINAL FIX: promote validated RS42 test environment")
    print()

    agents = inspect_source_pickle()

    print(
        "Source check: test.pkl contains {} trains".format(
            len(agents)
        )
    )

    for agent in agents:
        print(
            "  Train {train}: start={start}, target={target}, "
            "release={earliest_departure}, latest={latest_arrival}"
            .format(**agent)
        )

    print()
    print("Validating source test.pkl with current backend...")

    source_passed, source_output = run_validation(
        SRC_PKL,
        timeout=300,
    )

    log_dir = (
        ROOT
        / "experiments"
        / "final_evaluation"
        / "logs"
    )
    log_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_log = log_dir / "e6_source_test_validation.txt"
    source_log.write_text(
        source_output,
        encoding="utf-8",
    )

    if not source_passed:
        raise RuntimeError(
            "test.pkl no longer passes backend validation.\\n\\n"
            + source_output[-6000:]
        )

    print("  Source validation: PASS")

    archive_dir = archive_existing()

    if archive_dir is not None:
        print(
            "  Previous E6 archived to: {}".format(
                archive_dir.relative_to(ROOT)
            )
        )

    copy_assets()

    print()
    print("Validating canonical e6_shared_conflict.pkl...")

    target_passed, target_output = run_validation(
        OUT_PKL,
        timeout=300,
    )

    OUT_LOG.write_text(
        target_output,
        encoding="utf-8",
    )

    if not target_passed:
        raise RuntimeError(
            "Copied E6 failed validation.\\n\\n"
            + target_output[-6000:]
        )

    print("  Canonical validation: PASS")

    metadata = {
        "environment": TARGET_STEM,
        "source_environment": SOURCE_STEM,
        "experiment_type": "infrastructure_robustness",
        "purpose": (
            "multi-train conflict-free scheduling and "
            "ASP-to-Flatland executability"
        ),
        "construction_policy": (
            "promoted from existing validated RS42 test environment"
        ),
        "passenger_preference_claims": False,
        "agent_count": len(agents),
        "agents": agents,
        "source_validation": "PASS",
        "canonical_e6_validation": "PASS",
    }

    OUT_META.write_text(
        json.dumps(metadata, indent=2) + "\\n",
        encoding="utf-8",
    )

    print()
    print("E6 PROMOTION: PASS")
    print("  ASP -> Flatland validation: PASS")
    print("  Source: test.pkl")
    print("  Canonical: e6_shared_conflict.pkl")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            "ERROR: {}".format(exc),
            file=sys.stderr,
        )
        raise SystemExit(1)
"""


def main():
    if not (ROOT / "solve.py").exists():
        raise RuntimeError(
            "Run this installer from the RS42 repository root."
        )

    TARGET.parent.mkdir(parents=True, exist_ok=True)

    if TARGET.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = TARGET.with_name(
            "build_e6_shared_conflict_before_final_{}.py".format(
                timestamp
            )
        )
        shutil.copy2(str(TARGET), str(backup))
        print("Backup:", backup.relative_to(ROOT))

    TARGET.write_text(BUILDER, encoding="utf-8")
    compile(BUILDER, str(TARGET), "exec")

    print("Installed:", TARGET.relative_to(ROOT))
    print()
    print("VERIFY THIS LINE:")
    print(
        '  findstr /C:"E6 FINAL FIX" '
        'tools\\final_evaluation\\build_e6_shared_conflict.py'
    )
    print()
    print("Then run:")
    print(
        "  python tools\\final_evaluation\\"
        "build_e6_shared_conflict.py --overwrite"
    )


if __name__ == "__main__":
    main()
