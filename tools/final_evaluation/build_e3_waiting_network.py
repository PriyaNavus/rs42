"""
RS42 E3 — Waiting Network, meaningful-network v2.

Both alternatives still use exactly one transfer. Curved physical routes are
used, while the controlled timetable preserves the validated comparison:

- Fast/high-wait route: journey 20, wait 4.
- Slower/low-wait route: journey 21, wait 1.
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

STEM = "e3_waiting_network"
WIDTH = 22
HEIGHT = 13
HORIZON = 30

# Final moderate-complexity waiting network.
# Both alternatives still have one transfer and equal total turn complexity.
# The train legs are now 8/8 and 10/10 rather than 3/3 and 6/6.
A1_PATH = manhattan_path([
    (2, 0),
    (2, 3),
    (4, 3),
    (4, 5),
    (3, 5),
    (3, 7),
])

A2_PATH = manhattan_path([
    (2, 9),
    (2, 12),
    (4, 12),
    (4, 14),
    (3, 14),
    (3, 16),
])

B1_PATH = manhattan_path([
    (8, 0),
    (8, 4),
    (10, 4),
    (10, 6),
    (9, 6),
    (9, 9),
])

B2_PATH = manhattan_path([
    (8, 11),
    (8, 15),
    (10, 15),
    (10, 17),
    (9, 17),
    (9, 20),
])

A1_ORIGIN, A1_B = (2, 1), (3, 6)
A2_B, A2_DESTINATION = (2, 10), (3, 15)
B1_ORIGIN, B1_C = (8, 1), (9, 8)
B2_C, B2_DESTINATION = (8, 12), (9, 19)

PATHS = [A1_PATH, A2_PATH, B1_PATH, B2_PATH]
STARTS = [A1_ORIGIN, A2_B, B1_ORIGIN, B2_C]
TARGETS = [A1_B, A2_DESTINATION, B1_C, B2_DESTINATION]

# Fast/high-wait: 2->10, 14->22 => wait 4, journey 20
# Low-wait:       2->12, 13->23 => wait 1, journey 21
RELEASES = [0, 12, 0, 11]

STEPS = [
    route_steps(path, start, target)
    for path, start, target in zip(PATHS, STARTS, TARGETS)
]
TURNS = [
    route_turns(path, start, target)
    for path, start, target in zip(PATHS, STARTS, TARGETS)
]

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



def assert_internal_stations():
    """RS42 train start/target cells must not be raw rail endpoints."""
    for name, path, start, target in zip(
        ["route{}".format(i) for i in range(len(PATHS))],
        PATHS,
        STARTS,
        TARGETS,
    ):
        start_i = path.index(tuple(start))
        target_i = path.index(tuple(target))

        if start_i <= 0:
            raise RuntimeError(
                "{} start {} is on the rail endpoint; "
                "leave one rail cell before every train start."
                .format(name, start)
            )

        if target_i >= len(path) - 1:
            raise RuntimeError(
                "{} target {} is on the rail endpoint; "
                "leave one rail cell after every train target."
                .format(name, target)
            )

        if target_i <= start_i:
            raise RuntimeError(
                "{} target must occur after its start."
                .format(name)
            )

def build_environment():
    rail = build_disjoint_rail(
        WIDTH,
        HEIGHT,
        {
            "fast_leg1": A1_PATH,
            "fast_leg2": A2_PATH,
            "lowwait_leg1": B1_PATH,
            "lowwait_leg2": B2_PATH,
        },
    )

    env = RailEnv(
        width=WIDTH,
        height=HEIGHT,
        rail_generator=rail_from_grid_transition_map(rail),
        line_generator=EvaluationLineGenerator(
            positions=STARTS,
            directions=[
                initial_direction(path, start)
                for path, start in zip(PATHS, STARTS)
            ],
            targets=TARGETS,
            speeds=[1.0] * 4,
        ),
        number_of_agents=4,
        obs_builder_object=GlobalObsForRailEnv(),
        malfunction_generator=ParamMalfunctionGen(
            MalfunctionParameters(0.0, 0, 0)
        ),
        remove_agents_at_target=True,
        random_seed=42,
    )
    env.reset(random_seed=42)
    env._max_episode_steps = HORIZON

    for agent, release, steps in zip(env.agents, RELEASES, STEPS):
        agent.earliest_departure = release
        try:
            agent.latest_arrival = release + 2 + steps
        except Exception:
            pass

    return env


def scenario_text():
    return f"""% RS42 E3 - Curved Waiting Network

flatland_waypoint(0,wp_a1_origin,{A1_ORIGIN[0]},{A1_ORIGIN[1]}).
flatland_waypoint(0,wp_a1_b,{A1_B[0]},{A1_B[1]}).
station(origin,0,wp_a1_origin).
station(station_b,0,wp_a1_b).
must_visit(0,origin).
must_visit(0,station_b).
station_order(0,origin,station_b).

flatland_waypoint(1,wp_a2_b,{A2_B[0]},{A2_B[1]}).
flatland_waypoint(1,wp_a2_destination,{A2_DESTINATION[0]},{A2_DESTINATION[1]}).
station(station_b,1,wp_a2_b).
station(destination,1,wp_a2_destination).
must_visit(1,station_b).
must_visit(1,destination).
station_order(1,station_b,destination).

flatland_waypoint(2,wp_b1_origin,{B1_ORIGIN[0]},{B1_ORIGIN[1]}).
flatland_waypoint(2,wp_b1_c,{B1_C[0]},{B1_C[1]}).
station(origin,2,wp_b1_origin).
station(station_c,2,wp_b1_c).
must_visit(2,origin).
must_visit(2,station_c).
station_order(2,origin,station_c).

flatland_waypoint(3,wp_b2_c,{B2_C[0]},{B2_C[1]}).
flatland_waypoint(3,wp_b2_destination,{B2_DESTINATION[0]},{B2_DESTINATION[1]}).
station(station_c,3,wp_b2_c).
station(destination,3,wp_b2_destination).
must_visit(3,station_c).
must_visit(3,destination).
station_order(3,station_c,destination).

passenger(p1).
passenger_origin(p1,origin).
passenger_destination(p1,destination).

% Fixed service timetable for the longer E3.
:- first_station_visit(0,origin,T), T != 2.
:- first_station_visit(0,station_b,T), T != 10.
:- first_station_visit(1,station_b,T), T != 14.
:- first_station_visit(1,destination,T), T != 22.

:- first_station_visit(2,origin,T), T != 2.
:- first_station_visit(2,station_c,T), T != 12.
:- first_station_visit(3,station_c,T), T != 13.
:- first_station_visit(3,destination,T), T != 23.
"""


def verify(env_lp_text, scenario):
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        env_lp = tmpdir / "environment.lp"
        scenario_file = tmpdir / "scenario.lp"
        show_file = tmpdir / "show.lp"
        env_lp.write_text(env_lp_text, encoding="utf-8")
        scenario_file.write_text(scenario, encoding="utf-8")
        show_file.write_text(metric_show_text(), encoding="utf-8")

        results = {}
        for profile in ["fastest", "least_waiting"]:
            status, atoms, _ = run_clingo(
                ROOT,
                env_lp,
                scenario_file,
                profile_path(ROOT, profile),
                show_file,
                timeout=90,
            )
            results[profile] = {
                "status": status,
                "journey": passenger_metric(atoms, "passenger_journey_time"),
                "wait": passenger_metric(atoms, "passenger_transfer_wait"),
                "transfers": passenger_metric(atoms, "transfer_count"),
                "legs": chosen_legs(atoms),
            }
        return results


def main():
    args = parse_args()
    require_backend(ROOT)

    if STEPS != [8, 8, 10, 10]:
        raise RuntimeError("Unexpected E3 movement lengths: {}".format(STEPS))
    if TURNS != [4, 4, 4, 4]:
        raise RuntimeError("Unexpected E3 route turns: {}".format(TURNS))
    assert_internal_stations()

    existing = [path for path in outputs() if path.exists()]
    if existing and not args.overwrite:
        raise RuntimeError("E3 exists. Run with --overwrite after verification.")

    print("Building curved E3...")
    env = build_environment()
    env_lp_text = convert_to_clingo(env)
    scenario = scenario_text()
    results = verify(env_lp_text, scenario)

    fastest = results["fastest"]
    least = results["least_waiting"]

    if not (
        fastest["journey"] == 20
        and fastest["wait"] == 4
        and fastest["transfers"] == 1
    ):
        raise RuntimeError("Fastest waiting trade-off failed: {}".format(fastest))

    if not (
        least["journey"] == 21
        and least["wait"] == 1
        and least["transfers"] == 1
    ):
        raise RuntimeError("Less Waiting trade-off failed: {}".format(least))

    if args.overwrite:
        archive = (
            ROOT / "experiments" / "_archive" /
            ("e3_before_curved_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
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
                "movement_steps": STEPS,
                "route_turns": TURNS,
                "verification": results,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    prefix = str(ROOT / "envs") + str(Path("/"))
    save_png(env, STEM, prefix)

    print("E3 CURVED BUILD: PASS")
    print("  Fastest: journey=20, wait=4, transfers=1")
    print("  Less Waiting: journey=21, wait=1, transfers=1")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
