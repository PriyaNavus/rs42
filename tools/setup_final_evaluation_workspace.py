"""
Reset RS42 into a clean FINAL EVALUATION workspace.

This script does NOT modify the validated backend.
It archives only failed/obsolete experimental prototype files and creates
the final experiment directory structure.

Run from the rs42 repository root:

    conda activate flatlandrs42
    python tools/setup_final_evaluation_workspace.py

Safe behavior:
- moves obsolete prototype files into experiments/_archive/
- never deletes validated backend files
- never overwrites an existing final-evaluation file
- writes a manifest of everything moved
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FINAL = ROOT / "experiments" / "final_evaluation"
ARCHIVE_ROOT = ROOT / "experiments" / "_archive"

# Only obsolete experiment-generation attempts go here.
# Core ASP/backend files are intentionally NOT included.
PROTOTYPE_PATTERNS = [
    ("tools", "build_od_transfer_01*.py"),
    ("tools", "run_exp1_transfer_preference.py"),
]

# Old generated benchmark artifacts.
PROTOTYPE_OUTPUTS = [
    ROOT / "envs" / "pkl" / "od_transfer_01.pkl",
    ROOT / "envs" / "lp" / "od_transfer_01.lp",
    ROOT / "envs" / "png" / "od_transfer_01.png",
    ROOT / "asp" / "scenarios" / "od_transfer_01.lp",
    ROOT / "asp" / "scenarios" / "od_transfer_01.json",
]

FINAL_DIRS = [
    FINAL / "configs",
    FINAL / "results" / "runs",
    FINAL / "results" / "summaries",
    FINAL / "results" / "validation",
    FINAL / "raw",
    FINAL / "plots",
    FINAL / "logs",
    ROOT / "tools" / "final_evaluation",
]

README = """# RS42 Final Evaluation

This folder contains the final controlled evaluation of the RS42
preference-aware railway scheduling system.

## Frozen backend

The evaluation assumes the validated backend is frozen:
- scenario isolation
- semantic objective profiles
- passenger OD itinerary selection
- ASP -> Flatland execution validation
- reached trains removed from active ASP occupancy after reaching target

Do not modify those components during evaluation unless a regression fails.

## Environments

Four deterministic Flatland environments are used.

### E1 - Fast vs Slow Route
Two passenger services from the same origin to destination with a clear
journey-time difference.

Primary question:
Does Fastest choose the lower-time service?

### E2 - Transfer Network
A slower direct service competes with a faster journey through multiple
intermediate stations/trains.

Primary question:
Does Fastest accept transfers while Fewer Transfers prefers the slower
direct service?

### E3 - Waiting Network
A lower-total-time itinerary contains more connection waiting while an
alternative has lower waiting but a longer journey.

Primary question:
Does Less Waiting sacrifice journey time to reduce waiting?

### E4 - Simple vs Complex Route
A short route has greater turn/route complexity while a longer route is
simpler.

Primary question:
Does Simple Journey accept longer travel for fewer turns?

## Profiles

Every environment is evaluated with the same five profiles:
1. Fastest
2. Less Waiting
3. Fewer Transfers
4. Simple Journey
5. Balanced

This produces 4 x 5 = 20 primary optimization runs.

## Output policy

Never save final experiment outputs into temporary tool folders.

- results/runs/       one row/result per environment-profile run
- results/summaries/  consolidated CSV/JSON tables
- results/validation/ Flatland execution validation
- raw/                raw ASP/solver output
- plots/              report-ready figures
- logs/               execution logs
- configs/            immutable experiment metadata/configuration

Each environment should also keep canonical assets in:
- envs/pkl/
- envs/lp/
- envs/png/
- asp/scenarios/

Final environment names:
- e1_fast_slow
- e2_transfer_network
- e3_waiting_network
- e4_simple_complex

## Evaluation rule

Within an environment, the railway and passenger OD remain fixed.
Only the preference profile changes.

Across environments, the physical/timetable structure changes to expose
a different controlled trade-off.
"""

CONFIG = {
    "evaluation_name": "RS42 final controlled evaluation",
    "environments": [
        "e1_fast_slow",
        "e2_transfer_network",
        "e3_waiting_network",
        "e4_simple_complex",
    ],
    "profiles": [
        "fastest",
        "least_waiting",
        "fewest_transfers",
        "simple",
        "balanced",
    ],
    "primary_runs": 20,
    "backend_policy": "frozen_during_evaluation",
    "output_root": "experiments/final_evaluation",
}


def unique_archive_dir():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return ARCHIVE_ROOT / ("failed_prototypes_" + stamp)


def move_safely(src: Path, archive_dir: Path, moved):
    if not src.exists():
        return

    try:
        rel = src.relative_to(ROOT)
    except ValueError:
        rel = Path(src.name)

    dst = archive_dir / rel
    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists():
        raise FileExistsError("Archive collision: {}".format(dst))

    shutil.move(str(src), str(dst))
    moved.append({
        "from": str(rel),
        "to": str(dst.relative_to(ROOT)),
    })


def main():
    archive_dir = unique_archive_dir()
    moved = []

    print("RS42 final evaluation workspace")
    print()

    # 1. Archive obsolete prototype scripts.
    for folder_name, pattern in PROTOTYPE_PATTERNS:
        folder = ROOT / folder_name
        if not folder.exists():
            continue
        for path in sorted(folder.glob(pattern)):
            # Never archive this setup script itself.
            if path.name == Path(__file__).name:
                continue
            move_safely(path, archive_dir, moved)

    # 2. Archive old generated transfer benchmark outputs.
    for path in PROTOTYPE_OUTPUTS:
        move_safely(path, archive_dir, moved)

    # 3. Archive obsolete synthetic controlled-result folder if present.
    old_controlled = ROOT / "experiments" / "controlled"
    if old_controlled.exists():
        move_safely(old_controlled, archive_dir, moved)

    # 4. Create clean final directories.
    for folder in FINAL_DIRS:
        folder.mkdir(parents=True, exist_ok=True)

    # 5. Create immutable-ish documentation/config only if absent.
    readme_path = FINAL / "README.md"
    if not readme_path.exists():
        readme_path.write_text(README, encoding="utf-8")

    config_path = FINAL / "configs" / "evaluation_plan.json"
    if not config_path.exists():
        config_path.write_text(
            json.dumps(CONFIG, indent=2) + "\n",
            encoding="utf-8",
        )

    # 6. Archive manifest.
    if moved:
        archive_dir.mkdir(parents=True, exist_ok=True)
        manifest = archive_dir / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "purpose": "obsolete RS42 experiment prototypes",
                    "files_moved": moved,
                },
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

    print("Archived prototype files: {}".format(len(moved)))
    if moved:
        print("Archive:")
        print("  {}".format(archive_dir.relative_to(ROOT)))

    print()
    print("Final evaluation workspace:")
    print("  experiments/final_evaluation/")
    print("    configs/")
    print("    results/runs/")
    print("    results/summaries/")
    print("    results/validation/")
    print("    raw/")
    print("    plots/")
    print("    logs/")
    print()
    print("Builder folder:")
    print("  tools/final_evaluation/")
    print()
    print("Canonical environment names:")
    for name in CONFIG["environments"]:
        print("  " + name)

    print()
    print("BACKEND LEFT UNCHANGED.")
    print("Workspace reset complete.")


if __name__ == "__main__":
    main()
