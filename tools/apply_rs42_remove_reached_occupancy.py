"""
RS42 backend fix: remove reached trains from ASP occupancy.

Why:
Current encoding.lp contains:
    pos(..., T+1) :- pos(..., T), reached(ID,T), ...
which keeps a completed train occupying its target for the rest of the
planning horizon.

Flatland RS42 environments use remove_agents_at_target=True, so completed
trains disappear from active occupancy. This installer aligns ASP safety
semantics with Flatland execution.

Run from rs42 root:
    conda activate flatlandrs42
    python tools/apply_rs42_remove_reached_occupancy.py

The script:
1. backs up encoding.lp
2. removes the target-anchoring rule
3. runs env_001--2_4 and test regressions
4. automatically restores the backup if either regression fails
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENCODING = ROOT / "asp" / "custom" / "encoding.lp"

REGRESSIONS = [
    ROOT / "envs" / "pkl" / "env_001--2_4.pkl",
    ROOT / "envs" / "pkl" / "test.pkl",
]

OLD_BLOCK = """% after reaching the goal, the train stays anchored at its target cell
pos(ID, X, Y, Dir, T+1) :-
    pos(ID, X, Y, Dir, T), reached(ID, T), max_time(MT), T < MT.
"""

NEW_BLOCK = """% after reaching the goal, the train leaves active occupancy.
% This matches Flatland environments configured with
% remove_agents_at_target=True.
%
% Do NOT propagate pos/5 after reached(ID,T).  Safety constraints therefore
% stop treating a completed train as a permanently parked obstacle.
removed(ID, T+1) :-
    reached(ID, T), max_time(MT), T < MT.

% once removed, remain logically removed (but not physically occupying rail)
removed(ID, T+1) :-
    removed(ID, T), max_time(MT), T < MT.
"""


def run_regression(env_path: Path):
    result = subprocess.run(
        [
            sys.executable,
            "solve.py",
            str(env_path),
            "--no-render",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=240,
    )

    output = result.stdout + result.stderr
    passed = (
        result.returncode == 0
        and "RS42_VALIDATION: PASS" in output
    )

    return passed, output


def main():
    if not ENCODING.exists():
        raise FileNotFoundError(f"Missing {ENCODING}")

    for path in REGRESSIONS:
        if not path.exists():
            raise FileNotFoundError(
                f"Missing regression environment: {path}"
            )

    original = ENCODING.read_text(encoding="utf-8")

    if NEW_BLOCK.strip() in original:
        print("Reached-train occupancy fix is already installed.")
        patched = original
    else:
        if OLD_BLOCK not in original:
            raise RuntimeError(
                "Expected reached-train anchoring block was not found in "
                "asp/custom/encoding.lp. No files were changed."
            )

        patched = original.replace(OLD_BLOCK, NEW_BLOCK, 1)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup = ENCODING.with_name(
        f"encoding.lp.before_remove_reached_{timestamp}.bak"
    )
    shutil.copy2(ENCODING, backup)

    print(f"Backup: {backup.relative_to(ROOT)}")

    try:
        ENCODING.write_text(patched, encoding="utf-8")
        print("Patched asp/custom/encoding.lp")
        print()

        for env_path in REGRESSIONS:
            print(f"Regression: {env_path.name}")
            passed, output = run_regression(env_path)

            if not passed:
                print("  FAIL")
                print()
                print(output[-8000:])
                raise RuntimeError(
                    f"Regression failed for {env_path.name}"
                )

            print("  PASS: RS42_VALIDATION: PASS")

        print()
        print("SUCCESS")
        print(
            "Reached trains are no longer kept as permanent ASP rail "
            "obstacles, and both known Flatland regressions still pass."
        )
        print()
        print("Next:")
        print(
            r"  python tools\build_od_transfer_01_v5.py"
        )
        print(
            "The existing candidate search can now be reused; do not "
            "continue with the custom crossing builders."
        )

    except Exception:
        shutil.copy2(backup, ENCODING)
        print()
        print("RESTORED original encoding.lp because validation failed.")
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
