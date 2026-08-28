"""
Common RS42 final-evaluation builder helpers.
"""

import json
import re
import subprocess
import sys
from pathlib import Path


def backend_paths(root):
    return [
        root / "asp" / "custom" / "connection.lp",
        root / "asp" / "custom" / "encoding.lp",
        root / "asp" / "custom" / "waypoint.lp",
        root / "asp" / "custom" / "passenger_transfer.lp",
        root / "asp" / "custom" / "visual.lp",
        root / "asp" / "custom" / "objectives.lp",
    ]


def require_backend(root):
    missing = [str(path) for path in backend_paths(root) if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing validated RS42 backend files:\n" + "\n".join(missing)
        )


def run_clingo(
    root,
    env_lp,
    scenario_file,
    profile_file,
    extra_show_file=None,
    timeout=90,
):
    cmd = [
        sys.executable,
        "-m",
        "clingo",
        str(env_lp),
    ]
    cmd.extend(str(path) for path in backend_paths(root))
    cmd.extend(
        [
            str(profile_file),
            str(scenario_file),
        ]
    )

    if extra_show_file is not None:
        cmd.append(str(extra_show_file))

    cmd.extend(["--outf=2", "--opt-mode=opt"])

    result = subprocess.run(
        cmd,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if not result.stdout.strip():
        raise RuntimeError(
            "Clingo produced no JSON output.\n" + result.stderr[-5000:]
        )

    try:
        data = json.loads(result.stdout)
    except Exception:
        raise RuntimeError(
            "Could not parse Clingo JSON.\nSTDOUT:\n"
            + result.stdout[-5000:]
            + "\nSTDERR:\n"
            + result.stderr[-5000:]
        )

    status = str(data.get("Result", "UNKNOWN")).upper()
    calls = data.get("Call", [])
    witnesses = calls[-1].get("Witnesses", []) if calls else []

    if status != "OPTIMUM FOUND" or not witnesses:
        raise RuntimeError(
            "Expected OPTIMUM FOUND, got {}.\n{}".format(
                status,
                result.stderr[-3000:],
            )
        )

    witness = witnesses[-1]
    return status, witness.get("Value", []), witness.get("Costs", [])


def passenger_metric(atoms, predicate, passenger="p1"):
    pattern = re.compile(
        r"^{}\({},(-?\d+)\)$".format(
            re.escape(predicate),
            re.escape(passenger),
        )
    )
    for atom in atoms:
        match = pattern.match(atom)
        if match:
            return int(match.group(1))
    return None


def chosen_legs(atoms, passenger="p1"):
    pattern = re.compile(
        r"^chosen_leg\({},(\d+),(\d+),([^,]+),([^,]+),(-?\d+),(-?\d+)\)$"
        .format(re.escape(passenger))
    )

    rows = []
    for atom in atoms:
        match = pattern.match(atom)
        if match:
            rows.append(
                {
                    "leg": int(match.group(1)),
                    "train": int(match.group(2)),
                    "from": match.group(3),
                    "to": match.group(4),
                    "board": int(match.group(5)),
                    "alight": int(match.group(6)),
                    "atom": atom,
                }
            )

    return sorted(rows, key=lambda row: row["leg"])


def profile_path(root, profile):
    mapping = {
        "fastest": "profile_fastest.lp",
        "least_waiting": "profile_least_waiting.lp",
        "fewest_transfers": "profile_fewest_transfers.lp",
        "simple": "profile_comfort.lp",
        "balanced": "profile_balanced.lp",
    }
    return root / "asp" / "profiles" / mapping[profile]


def metric_show_text():
    return """#show chosen_leg/7.
#show passenger_journey_time/2.
#show passenger_transfer_wait/2.
#show transfer_count/2.
#show turns/2.
#show travel_time/2.
"""


def validate_with_solve(root, pkl_path, timeout=240):
    result = subprocess.run(
        [
            sys.executable,
            "solve.py",
            str(pkl_path),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = result.stdout + result.stderr
    return (
        result.returncode == 0
        and "RS42_VALIDATION: PASS" in output,
        output,
    )
