"""
RS42: inspect all Flatland Test_02 benchmark levels for use as E5.

IMPORTANT:
These benchmark .pkl files are Flatland persistence dictionaries, NOT raw
pickled RailEnv objects. They must be loaded with:

    RailEnvPersister.load_new(...)

Run from the RS42 repository root:

    conda activate flatlandrs42
    python inspect_test02_levels_for_e5.py

Outputs:
    experiments/final_evaluation/test02_e5_candidates/
        summary.csv
        summary.json
        Level_0.json
        ...
        previews/   (when PNG rendering succeeds)
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path.cwd().resolve()

if not (ROOT / "solve.py").exists():
    raise SystemExit(
        "ERROR: Run this script from the RS42 repository root."
    )

try:
    from flatland.envs.persistence import RailEnvPersister
except Exception as exc:
    raise SystemExit(
        "ERROR: Could not import RailEnvPersister: {}".format(exc)
    )


SOURCE_DIR = (
    ROOT
    / "benchmarks"
    / "environments"
    / "Test_02"
)

OUTPUT_DIR = (
    ROOT
    / "experiments"
    / "final_evaluation"
    / "test02_e5_candidates"
)

PREVIEW_DIR = OUTPUT_DIR / "previews"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def plain(value):
    if value is None:
        return None

    if hasattr(value, "tolist"):
        value = value.tolist()

    if isinstance(value, tuple):
        return [plain(x) for x in value]

    if isinstance(value, list):
        return [plain(x) for x in value]

    try:
        import numpy as np

        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass

    if isinstance(value, (int, float, str, bool)):
        return value

    return str(value)


def get_speed(agent):
    counter = getattr(agent, "speed_counter", None)

    if counter is None:
        return None

    return plain(
        getattr(counter, "speed", None)
    )


def agent_record(index, agent):
    return {
        "train": index,
        "start": plain(
            getattr(agent, "initial_position", None)
        ),
        "target": plain(
            getattr(agent, "target", None)
        ),
        "direction": plain(
            getattr(agent, "initial_direction", None)
        ),
        "earliest_departure": plain(
            getattr(agent, "earliest_departure", None)
        ),
        "latest_arrival": plain(
            getattr(agent, "latest_arrival", None)
        ),
        "speed": get_speed(agent),
    }


def rail_cell_count(env):
    grid = getattr(
        getattr(env, "rail", None),
        "grid",
        None,
    )

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


def render_preview(env, level_name):
    """
    Try RS42's own image helper first.
    Preview failure is non-fatal.
    """
    try:
        from modules.save import save_png

        prefix = str(PREVIEW_DIR) + str(Path("/"))

        save_png(
            env,
            level_name,
            prefix,
        )

        return "generated"

    except Exception as exc:
        return "failed: {}".format(exc)


def main():
    if not SOURCE_DIR.exists():
        raise RuntimeError(
            "Missing benchmark directory: {}".format(
                SOURCE_DIR
            )
        )

    levels = sorted(
        SOURCE_DIR.glob("Level_*.pkl")
    )

    if not levels:
        raise RuntimeError(
            "No Level_*.pkl files found under {}".format(
                SOURCE_DIR
            )
        )

    print()
    print("=" * 76)
    print("RS42 TEST_02 -> E5 CANDIDATE SCAN")
    print("=" * 76)
    print()
    print("Correct loader: RailEnvPersister.load_new()")
    print("Levels found:", len(levels))
    print()

    summaries = []

    for level_path in levels:
        level_name = level_path.stem

        print("-" * 76)
        print(level_name)
        print("-" * 76)

        try:
            env, env_dict = RailEnvPersister.load_new(
                str(level_path)
            )

        except Exception as exc:
            print("LOAD ERROR:", exc)

            summaries.append(
                {
                    "level": level_name,
                    "status": "LOAD_ERROR",
                    "width": None,
                    "height": None,
                    "trains": None,
                    "rail_cells": None,
                    "max_episode_steps": None,
                    "preview": "",
                    "error": str(exc),
                }
            )

            continue

        width = getattr(env, "width", None)
        height = getattr(env, "height", None)
        agents = list(
            getattr(env, "agents", [])
        )

        rail_cells = rail_cell_count(env)

        max_steps = getattr(
            env,
            "_max_episode_steps",
            None,
        )

        if not max_steps:
            max_steps = env_dict.get(
                "max_episode_steps",
                None,
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

        print(
            "Active rail cells:",
            rail_cells,
        )

        print(
            "Max episode steps:",
            max_steps,
        )

        records = []

        for index, agent in enumerate(agents):
            record = agent_record(
                index,
                agent,
            )

            records.append(record)

            print(
                "  Train {}: {} -> {} | dir={} | release={} | latest={}"
                .format(
                    index,
                    record["start"],
                    record["target"],
                    record["direction"],
                    record["earliest_departure"],
                    record["latest_arrival"],
                )
            )

        preview_status = render_preview(
            env,
            level_name,
        )

        print(
            "Preview:",
            preview_status,
        )

        level_json = (
            OUTPUT_DIR
            / "{}.json".format(level_name)
        )

        level_json.write_text(
            json.dumps(
                {
                    "source": str(
                        level_path.relative_to(ROOT)
                    ),
                    "width": plain(width),
                    "height": plain(height),
                    "rail_cells": rail_cells,
                    "number_of_trains": len(agents),
                    "max_episode_steps": plain(max_steps),
                    "trains": records,
                    "env_dict_keys": sorted(
                        str(key)
                        for key in env_dict.keys()
                    ),
                    "preview": preview_status,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        summaries.append(
            {
                "level": level_name,
                "status": "OK",
                "width": width,
                "height": height,
                "trains": len(agents),
                "rail_cells": rail_cells,
                "max_episode_steps": max_steps,
                "preview": preview_status,
                "error": "",
            }
        )

        print()

    summary_csv = OUTPUT_DIR / "summary.csv"

    with summary_csv.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "level",
                "status",
                "width",
                "height",
                "trains",
                "rail_cells",
                "max_episode_steps",
                "preview",
                "error",
            ],
        )

        writer.writeheader()
        writer.writerows(summaries)

    summary_json = OUTPUT_DIR / "summary.json"

    summary_json.write_text(
        json.dumps(
            summaries,
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )

    print("=" * 76)
    print("COMPACT SUMMARY")
    print("=" * 76)

    for row in summaries:
        if row["status"] == "OK":
            print(
                "{:<8} grid={:>2}x{:<2} trains={:<3} rail_cells={:<4} max_steps={}"
                .format(
                    row["level"],
                    row["width"],
                    row["height"],
                    row["trains"],
                    row["rail_cells"],
                    row["max_episode_steps"],
                )
            )
        else:
            print(
                "{} LOAD ERROR".format(
                    row["level"]
                )
            )

    print()
    print(
        "Saved:",
        summary_csv.relative_to(ROOT),
    )

    print(
        "Saved:",
        summary_json.relative_to(ROOT),
    )

    print()
    print(
        "Preview directory:",
        PREVIEW_DIR.relative_to(ROOT),
    )

    print()
    print(
        "Send me only the COMPACT SUMMARY section."
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
