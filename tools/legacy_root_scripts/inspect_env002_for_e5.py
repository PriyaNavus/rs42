"""
Inspect an existing RS42 env_002 Flatland environment before promoting it to E5.

This script does NOT overwrite E5.

It:
1. Searches envs/pkl for env_002*.pkl.
2. Loads the environment.
3. Prints every train's start, target, direction and timing.
4. Generates a fresh LP and PNG preview in:
       experiments/final_evaluation/e5_env002_staging/
5. Writes the inspection information to JSON.

Run from RS42 repository root:
    python inspect_env002_for_e5.py

If more than one env_002 candidate exists:
    python inspect_env002_for_e5.py --source envs/pkl/<exact-file>.pkl
"""

from __future__ import annotations

import argparse
import json
import pickle
import shutil
import sys
from pathlib import Path


ROOT = Path.cwd().resolve()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Optional exact env_002 .pkl path.",
    )
    return parser.parse_args()


def discover_source(explicit=None):
    if explicit:
        path = (ROOT / explicit).resolve()

        if not path.exists():
            raise RuntimeError(
                "Specified source does not exist: {}".format(path)
            )

        return path

    pkl_dir = ROOT / "envs" / "pkl"

    if not pkl_dir.exists():
        raise RuntimeError(
            "envs/pkl directory not found."
        )

    candidates = sorted(
        [
            path
            for path in pkl_dir.glob("*.pkl")
            if (
                path.stem.lower().startswith("env_002")
                or path.stem.lower() == "env002"
                or "env_002" in path.stem.lower()
            )
        ]
    )

    if not candidates:
        raise RuntimeError(
            "No env_002*.pkl file found under envs/pkl."
        )

    if len(candidates) > 1:
        print("Multiple env_002 candidates found:")
        for index, path in enumerate(candidates, start=1):
            print(
                "  {}. {}".format(
                    index,
                    path.relative_to(ROOT),
                )
            )

        raise RuntimeError(
            "Run again with --source and the exact file you want."
        )

    return candidates[0]


def to_plain(value):
    if value is None:
        return None

    if hasattr(value, "tolist"):
        value = value.tolist()

    if isinstance(value, tuple):
        return [to_plain(item) for item in value]

    if isinstance(value, list):
        return [to_plain(item) for item in value]

    if isinstance(value, dict):
        return {
            str(key): to_plain(val)
            for key, val in value.items()
        }

    try:
        import numpy as np

        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass

    return value


def agent_record(index, agent):
    start = getattr(
        agent,
        "initial_position",
        getattr(agent, "position", None),
    )

    target = getattr(
        agent,
        "target",
        None,
    )

    direction = getattr(
        agent,
        "initial_direction",
        getattr(agent, "direction", None),
    )

    earliest = getattr(
        agent,
        "earliest_departure",
        None,
    )

    latest = getattr(
        agent,
        "latest_arrival",
        None,
    )

    speed = None
    speed_counter = getattr(
        agent,
        "speed_counter",
        None,
    )

    if speed_counter is not None:
        speed = getattr(
            speed_counter,
            "speed",
            None,
        )

    return {
        "train": int(index),
        "start": to_plain(start),
        "target": to_plain(target),
        "direction": to_plain(direction),
        "earliest_departure": to_plain(earliest),
        "latest_arrival": to_plain(latest),
        "speed": to_plain(speed),
    }


def count_rail_cells(env):
    rail = getattr(env, "rail", None)

    if rail is None:
        return None

    grid = getattr(rail, "grid", None)

    if grid is None:
        return None

    try:
        return int((grid != 0).sum())
    except Exception:
        count = 0

        for row in grid:
            for cell in row:
                if int(cell) != 0:
                    count += 1

        return count


def main():
    if not (ROOT / "solve.py").exists():
        raise RuntimeError(
            "Run this script from the RS42 repository root."
        )

    args = parse_args()
    source = discover_source(args.source)

    print()
    print("RS42 ENV_002 -> E5 INSPECTION")
    print("============================")
    print()
    print(
        "Source:",
        source.relative_to(ROOT),
    )

    with source.open("rb") as handle:
        env = pickle.load(handle)

    width = getattr(env, "width", None)
    height = getattr(env, "height", None)

    agents = list(
        getattr(env, "agents", [])
    )

    print(
        "Grid: {} x {}".format(
            width,
            height,
        )
    )

    print(
        "Trains:",
        len(agents),
    )

    rail_cells = count_rail_cells(env)

    if rail_cells is not None:
        print(
            "Active rail cells:",
            rail_cells,
        )

    print()
    print("TRAIN LAYOUT")
    print("------------")

    records = []

    for index, agent in enumerate(agents):
        record = agent_record(
            index,
            agent,
        )

        records.append(record)

        print()
        print(
            "Train {}".format(index)
        )

        print(
            "  start:   {}".format(
                record["start"]
            )
        )

        print(
            "  target:  {}".format(
                record["target"]
            )
        )

        print(
            "  direction: {}".format(
                record["direction"]
            )
        )

        print(
            "  release: {}".format(
                record["earliest_departure"]
            )
        )

        print(
            "  latest:  {}".format(
                record["latest_arrival"]
            )
        )

    staging = (
        ROOT
        / "experiments"
        / "final_evaluation"
        / "e5_env002_staging"
    )

    staging.mkdir(
        parents=True,
        exist_ok=True,
    )

    staged_pkl = (
        staging
        / "env_002_source.pkl"
    )

    shutil.copy2(
        str(source),
        str(staged_pkl),
    )

    # Generate LP from the actual environment.
    try:
        from modules.convert import convert_to_clingo

        lp_text = convert_to_clingo(env)

        staged_lp = (
            staging
            / "env_002_source.lp"
        )

        staged_lp.write_text(
            lp_text,
            encoding="utf-8",
        )

        print()
        print(
            "Generated:",
            staged_lp.relative_to(ROOT),
        )

    except Exception as exc:
        print()
        print(
            "LP preview generation failed:",
            exc,
        )

    # Generate PNG from the actual environment.
    try:
        from modules.save import save_png

        prefix = (
            str(staging)
            + str(Path("/"))
        )

        save_png(
            env,
            "env_002_e5_preview",
            prefix,
        )

        preview = (
            staging
            / "png"
            / "env_002_e5_preview.png"
        )

        if not preview.exists():
            # Some save helpers place it directly in the supplied prefix.
            direct_preview = (
                staging
                / "env_002_e5_preview.png"
            )

            if direct_preview.exists():
                preview = direct_preview

        print(
            "Preview generated under:",
            staging.relative_to(ROOT),
        )

    except Exception as exc:
        print()
        print(
            "PNG preview generation failed:",
            exc,
        )

    inspection = {
        "source": str(
            source.relative_to(ROOT)
        ),
        "width": to_plain(width),
        "height": to_plain(height),
        "rail_cells": rail_cells,
        "number_of_trains": len(agents),
        "trains": records,
    }

    inspection_path = (
        staging
        / "env_002_inspection.json"
    )

    inspection_path.write_text(
        json.dumps(
            inspection,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print(
        "Inspection JSON:",
        inspection_path.relative_to(ROOT),
    )

    print()
    print("NEXT STEP")
    print("---------")
    print(
        "Do not overwrite E5 yet."
    )

    print(
        "Send the TRAIN LAYOUT output from this script."
    )

    print(
        "Then E5 can be mapped onto the actual env_002 topology "
        "instead of inventing another synthetic network."
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
