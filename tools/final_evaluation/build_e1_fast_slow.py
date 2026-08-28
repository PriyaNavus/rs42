"""
RS42 E1 — Fast vs Slow, meaningful-network v2.

Same controlled question as the validated straight-line prototype, but both
services now use clearly visible S-shaped rail geometry. Both routes have exactly
four turns so geometry does not confound the travel-time experiment.

Expected:
- Fast route: 18 movement steps, 6 turns.
- Slow route: 26 movement steps, 6 turns.
- Fastest selects Train 0.
"""

from __future__ import annotations

import argparse
import json
import pickle
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.convert import convert_to_clingo
from modules.save import save_png
from flatland.envs.rail_generators import rail_from_grid_transition_map
from flatland.envs.rail_env import RailEnv
from flatland.envs.observations import GlobalObsForRailEnv
from flatland.envs.malfunction_generators import MalfunctionParameters, ParamMalfunctionGen

from tools.final_evaluation.evaluation_generators import EvaluationLineGenerator
from tools.final_evaluation.final_eval_rail_geometry import (
    build_disjoint_rail,
    initial_direction,
    manhattan_path,
    route_steps,
    route_turns,
)
from tools.final_evaluation.final_eval_builder_common import (
    chosen_legs,
    metric_show_text,
    passenger_metric,
    profile_path,
    require_backend,
    run_clingo,
)

STEM = "e1_fast_slow"
WIDTH = 21
HEIGHT = 16
HORIZON = 34

# Final moderate-complexity E1.
# Both services use six turns, so the experimental difference remains
# journey length rather than route simplicity.
FAST_PATH = manhattan_path([
    (2, 0),
    (2, 4),
    (4, 4),
    (4, 7),
    (2, 7),
    (2, 10),
    (4, 10),
    (4, 14),
])

SLOW_PATH = manhattan_path([
    (10, 0),
    (10, 6),
    (13, 6),
    (13, 10),
    (10, 10),
    (10, 14),
    (13, 14),
    (13, 19),
])

FAST_ORIGIN = (2, 1)
FAST_DESTINATION = (4, 13)
SLOW_ORIGIN = (10, 1)
SLOW_DESTINATION = (13, 18)

FAST_STEPS = route_steps(FAST_PATH, FAST_ORIGIN, FAST_DESTINATION)
SLOW_STEPS = route_steps(SLOW_PATH, SLOW_ORIGIN, SLOW_DESTINATION)
FAST_TURNS = route_turns(FAST_PATH, FAST_ORIGIN, FAST_DESTINATION)
SLOW_TURNS = route_turns(SLOW_PATH, SLOW_ORIGIN, SLOW_DESTINATION)

OUT_PKL = ROOT / "envs" / "pkl" / f"{STEM}.pkl"
OUT_LP = ROOT / "envs" / "lp" / f"{STEM}.lp"
OUT_PNG = ROOT / "envs" / "png" / f"{STEM}.png"
OUT_SCENARIO = ROOT / "asp" / "scenarios" / f"{STEM}.lp"
OUT_META = ROOT / "experiments" / "final_evaluation" / "configs" / f"{STEM}.json"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def outputs():
    return [OUT_PKL, OUT_LP, OUT_PNG, OUT_SCENARIO, OUT_META]


def build_environment():
    rail = build_disjoint_rail(
        WIDTH,
        HEIGHT,
        {
            "fast": FAST_PATH,
            "slow": SLOW_PATH,
        },
    )

    line_gen = EvaluationLineGenerator(
        positions=[FAST_ORIGIN, SLOW_ORIGIN],
        directions=[
            initial_direction(FAST_PATH, FAST_ORIGIN),
            initial_direction(SLOW_PATH, SLOW_ORIGIN),
        ],
        targets=[FAST_DESTINATION, SLOW_DESTINATION],
        speeds=[1.0, 1.0],
    )

    env = RailEnv(
        width=WIDTH,
        height=HEIGHT,
        rail_generator=rail_from_grid_transition_map(rail),
        line_generator=line_gen,
        number_of_agents=2,
        obs_builder_object=GlobalObsForRailEnv(),
        malfunction_generator=ParamMalfunctionGen(
            MalfunctionParameters(
                malfunction_rate=0.0,
                min_duration=0,
                max_duration=0,
            )
        ),
        remove_agents_at_target=True,
        random_seed=42,
    )
    env.reset(random_seed=42)
    env._max_episode_steps = HORIZON

    for agent, steps in zip(env.agents, [FAST_STEPS, SLOW_STEPS]):
        agent.earliest_departure = 0
        try:
            agent.latest_arrival = 2 + steps
        except Exception:
            pass

    return env


def scenario_text():
    return f"""% RS42 E1 - Curved Fast vs Slow

flatland_waypoint(0,wp_fast_origin,{FAST_ORIGIN[0]},{FAST_ORIGIN[1]}).
flatland_waypoint(0,wp_fast_destination,{FAST_DESTINATION[0]},{FAST_DESTINATION[1]}).
station(origin,0,wp_fast_origin).
station(destination,0,wp_fast_destination).
must_visit(0,origin).
must_visit(0,destination).
station_order(0,origin,destination).

flatland_waypoint(1,wp_slow_origin,{SLOW_ORIGIN[0]},{SLOW_ORIGIN[1]}).
flatland_waypoint(1,wp_slow_destination,{SLOW_DESTINATION[0]},{SLOW_DESTINATION[1]}).
station(origin,1,wp_slow_origin).
station(destination,1,wp_slow_destination).
must_visit(1,origin).
must_visit(1,destination).
station_order(1,origin,destination).

passenger(p1).
passenger_origin(p1,origin).
passenger_destination(p1,destination).
"""


def main():
    args = parse_args()
    require_backend(ROOT)

    existing = [path for path in outputs() if path.exists()]
    if existing and not args.overwrite:
        raise RuntimeError("E1 exists. Run with --overwrite to replace it after verification.")

    if FAST_STEPS != 18 or SLOW_STEPS != 26:
        raise RuntimeError("Unexpected E1 path lengths.")
    if FAST_TURNS != 6 or SLOW_TURNS != 6:
        raise RuntimeError("E1 must keep equal turn counts (6 vs 6).")

    print("Building curved E1...")
    env = build_environment()
    env_lp_text = convert_to_clingo(env)
    scenario = scenario_text()

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        env_lp = tmpdir / "environment.lp"
        scenario_file = tmpdir / "scenario.lp"
        show_file = tmpdir / "show.lp"
        env_lp.write_text(env_lp_text, encoding="utf-8")
        scenario_file.write_text(scenario, encoding="utf-8")
        show_file.write_text(metric_show_text(), encoding="utf-8")

        status, atoms, _ = run_clingo(
            ROOT,
            env_lp,
            scenario_file,
            profile_path(ROOT, "fastest"),
            show_file,
            timeout=90,
        )

    legs = chosen_legs(atoms)
    journey = passenger_metric(atoms, "passenger_journey_time")
    if len(legs) != 1 or legs[0]["train"] != 0 or journey != 18:
        raise RuntimeError(
            "Curved E1 verification failed: legs={}, journey={}".format(
                legs, journey
            )
        )

    # Only after verification do we replace canonical artifacts.
    if args.overwrite:
        archive = (
            ROOT / "experiments" / "_archive" /
            ("e1_before_curved_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        )
        archive.mkdir(parents=True, exist_ok=True)
        for path in outputs():
            if path.exists():
                shutil.copy2(str(path), str(archive / path.name))

    for path in outputs():
        path.parent.mkdir(parents=True, exist_ok=True)

    with OUT_PKL.open("wb") as handle:
        pickle.dump(env, handle, protocol=pickle.HIGHEST_PROTOCOL)
    OUT_LP.write_text(env_lp_text, encoding="utf-8")
    OUT_SCENARIO.write_text(scenario, encoding="utf-8")
    OUT_META.write_text(
        json.dumps(
            {
                "environment": STEM,
                "geometry_version": "final_moderate_routes_v3",
                "fast": {"steps": FAST_STEPS, "turns": FAST_TURNS},
                "slow": {"steps": SLOW_STEPS, "turns": SLOW_TURNS},
                "verification": {
                    "status": status,
                    "fastest_train": 0,
                    "journey_time": journey,
                },
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    prefix = str(ROOT / "envs") + str(Path("/"))
    save_png(env, STEM, prefix)

    print("E1 CURVED BUILD: PASS")
    print("  fast: steps=18, turns=6")
    print("  slow: steps=26, turns=6")
    print("  Fastest -> Train 0, journey=18")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
