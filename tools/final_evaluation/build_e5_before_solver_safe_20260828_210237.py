"""
RS42 E5 — Mixed Preference Network.

Integrated passenger-choice experiment with three simultaneous alternatives:

A) Fast multi-transfer:
   journey 26, wait 2, transfers 2
B) Direct:
   journey 32, wait 0, transfers 0
C) Compromise:
   journey 28, wait 1, transfers 1

Unlike E1-E4, E5 intentionally puts several preference dimensions into the
same environment. Primary expected checks:
- Fastest -> A
- Less Waiting -> B
- Fewer Transfers -> B

Balanced and Simple are measured rather than hard-coded; their behavior is
part of the integrated result.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
import tempfile
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

STEM = "e5_mixed_preferences"
WIDTH = 23
HEIGHT = 21
HORIZON = 34

# Solver-balanced final E5.
# E5 remains the richest passenger experiment, but avoids the 32-step /
# 8-turn direct route that made repeated optimization too expensive.
DIRECT = manhattan_path([
    (2, 0),
    (2, 5),
    (5, 5),
    (5, 9),
    (2, 9),
    (2, 13),
    (5, 13),
    (5, 17),
    (3, 17),
    (3, 21),
])

FAST1 = manhattan_path([
    (9, 0),
    (9, 3),
    (11, 3),
    (11, 5),
    (10, 5),
    (9, 5),
])

FAST2 = manhattan_path([
    (9, 7),
    (9, 10),
    (11, 10),
    (11, 12),
    (10, 12),
    (9, 12),
])

FAST3 = manhattan_path([
    (9, 14),
    (9, 17),
    (11, 17),
    (11, 19),
    (10, 19),
    (9, 19),
])

COMP1 = manhattan_path([
    (16, 0),
    (16, 5),
    (19, 5),
    (19, 8),
    (17, 8),
])

COMP2 = manhattan_path([
    (16, 10),
    (16, 15),
    (19, 15),
    (19, 19),
    (17, 19),
])

PATHS = [DIRECT, FAST1, FAST2, FAST3, COMP1, COMP2]

STARTS = [
    (2, 1),
    (9, 1),
    (9, 8),
    (9, 15),
    (16, 1),
    (16, 11),
]

TARGETS = [
    (3, 20),
    (10, 5),
    (10, 12),
    (10, 19),
    (18, 8),
    (18, 19),
]

# first_station_visit = earliest_departure + 2
RELEASES = [0, 0, 8, 16, 0, 12]

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
            "direct": DIRECT,
            "fast1": FAST1,
            "fast2": FAST2,
            "fast3": FAST3,
            "comp1": COMP1,
            "comp2": COMP2,
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
            speeds=[1.0] * 6,
        ),
        number_of_agents=6,
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
    coords = list(zip(STARTS, TARGETS))
    return f"""% RS42 E5 - Mixed Preference Network

% Direct Train 0
flatland_waypoint(0,wp_d_o,{coords[0][0][0]},{coords[0][0][1]}).
flatland_waypoint(0,wp_d_d,{coords[0][1][0]},{coords[0][1][1]}).
station(origin,0,wp_d_o).
station(destination,0,wp_d_d).
must_visit(0,origin).
must_visit(0,destination).
station_order(0,origin,destination).

% Fast route: 1 -> 2 -> 3
flatland_waypoint(1,wp_f1_o,{coords[1][0][0]},{coords[1][0][1]}).
flatland_waypoint(1,wp_f1_b,{coords[1][1][0]},{coords[1][1][1]}).
station(origin,1,wp_f1_o).
station(station_b,1,wp_f1_b).
must_visit(1,origin).
must_visit(1,station_b).
station_order(1,origin,station_b).

flatland_waypoint(2,wp_f2_b,{coords[2][0][0]},{coords[2][0][1]}).
flatland_waypoint(2,wp_f2_c,{coords[2][1][0]},{coords[2][1][1]}).
station(station_b,2,wp_f2_b).
station(station_c,2,wp_f2_c).
must_visit(2,station_b).
must_visit(2,station_c).
station_order(2,station_b,station_c).

flatland_waypoint(3,wp_f3_c,{coords[3][0][0]},{coords[3][0][1]}).
flatland_waypoint(3,wp_f3_d,{coords[3][1][0]},{coords[3][1][1]}).
station(station_c,3,wp_f3_c).
station(destination,3,wp_f3_d).
must_visit(3,station_c).
must_visit(3,destination).
station_order(3,station_c,destination).

% Compromise route: 4 -> 5
flatland_waypoint(4,wp_c1_o,{coords[4][0][0]},{coords[4][0][1]}).
flatland_waypoint(4,wp_c1_h,{coords[4][1][0]},{coords[4][1][1]}).
station(origin,4,wp_c1_o).
station(station_h,4,wp_c1_h).
must_visit(4,origin).
must_visit(4,station_h).
station_order(4,origin,station_h).

flatland_waypoint(5,wp_c2_h,{coords[5][0][0]},{coords[5][0][1]}).
flatland_waypoint(5,wp_c2_d,{coords[5][1][0]},{coords[5][1][1]}).
station(station_h,5,wp_c2_h).
station(destination,5,wp_c2_d).
must_visit(5,station_h).
must_visit(5,destination).
station_order(5,station_h,destination).

passenger(p1).
passenger_origin(p1,origin).
passenger_destination(p1,destination).

% Final E5 timetable using the actual route lengths.
% Direct:      2 -> 32 = journey 30, wait 0, transfers 0
% Fast:        2 -> 9, 10 -> 17, 18 -> 25
%              journey 23, wait 2, transfers 2
% Compromise:  2 -> 13, 14 -> 26
%              journey 24, wait 1, transfers 1
:- first_station_visit(0,origin,T), T != 2.
:- first_station_visit(0,destination,T), T != 32.

:- first_station_visit(1,origin,T), T != 2.
:- first_station_visit(1,station_b,T), T != 9.
:- first_station_visit(2,station_b,T), T != 10.
:- first_station_visit(2,station_c,T), T != 17.
:- first_station_visit(3,station_c,T), T != 18.
:- first_station_visit(3,destination,T), T != 25.

:- first_station_visit(4,origin,T), T != 2.
:- first_station_visit(4,station_h,T), T != 13.
:- first_station_visit(5,station_h,T), T != 14.
:- first_station_visit(5,destination,T), T != 26.
"""


def evaluate(env_lp_text, scenario):
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        env_lp = tmpdir / "environment.lp"
        scenario_file = tmpdir / "scenario.lp"
        show_file = tmpdir / "show.lp"
        env_lp.write_text(env_lp_text, encoding="utf-8")
        scenario_file.write_text(scenario, encoding="utf-8")
        show_file.write_text(metric_show_text(), encoding="utf-8")

        results = {}
        for profile in [
            "fastest",
            "least_waiting",
            "fewest_transfers",
            "simple",
            "balanced",
        ]:
            status, atoms, costs = run_clingo(
                ROOT,
                env_lp,
                scenario_file,
                profile_path(ROOT, profile),
                show_file,
                timeout=300,
            )
            results[profile] = {
                "status": status,
                "journey": passenger_metric(atoms, "passenger_journey_time"),
                "wait": passenger_metric(atoms, "passenger_transfer_wait"),
                "transfers": passenger_metric(atoms, "transfer_count"),
                "legs": chosen_legs(atoms),
                "costs": costs,
            }
        return results


def main():
    args = parse_args()
    require_backend(ROOT)

    if STEPS != [30, 7, 7, 7, 11, 12]:
        raise RuntimeError("Unexpected E5 movement lengths: {}".format(STEPS))
    if TURNS != [8, 3, 3, 3, 3, 3]:
        raise RuntimeError("Unexpected E5 route turns: {}".format(TURNS))
    assert_internal_stations()

    if OUT_PKL.exists() and not args.overwrite:
        raise RuntimeError("E5 exists. Use --overwrite to intentionally rebuild.")

    print("Building E5 Mixed Preference Network...")
    env = build_environment()
    env_lp_text = convert_to_clingo(env)
    scenario = scenario_text()
    results = evaluate(env_lp_text, scenario)

    fastest = results["fastest"]
    least = results["least_waiting"]
    fewest = results["fewest_transfers"]

    if not (fastest["journey"] == 23 and fastest["transfers"] == 2):
        raise RuntimeError("E5 Fastest check failed: {}".format(fastest))
    if not (least["journey"] == 30 and least["wait"] == 0):
        raise RuntimeError("E5 Less Waiting check failed: {}".format(least))
    if not (fewest["journey"] == 30 and fewest["transfers"] == 0):
        raise RuntimeError("E5 Fewer Transfers check failed: {}".format(fewest))

    for path in [OUT_PKL, OUT_LP, OUT_PNG, OUT_SCENARIO, OUT_META]:
        path.parent.mkdir(parents=True, exist_ok=True)

    with OUT_PKL.open("wb") as handle:
        pickle.dump(env, handle, protocol=pickle.HIGHEST_PROTOCOL)
    OUT_LP.write_text(env_lp_text, encoding="utf-8")
    OUT_SCENARIO.write_text(scenario, encoding="utf-8")
    OUT_META.write_text(
        json.dumps(
            {
                "environment": STEM,
                "purpose": "integrated mixed-preference passenger network",
                "movement_steps": STEPS,
                "route_turns": TURNS,
                "results": results,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    prefix = str(ROOT / "envs") + str(Path("/"))
    save_png(env, STEM, prefix)

    print("E5 BUILD: PASS")
    for profile, result in results.items():
        print(
            "  {}: journey={}, wait={}, transfers={}".format(
                profile,
                result["journey"],
                result["wait"],
                result["transfers"],
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
