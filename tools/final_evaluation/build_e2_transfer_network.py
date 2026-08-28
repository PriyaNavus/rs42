"""
RS42 E2 — Transfer Network, meaningful-network v2.

The direct service and all three transfer legs now contain bends. The
controlled time/transfer relation remains unchanged:

- Fast transfer itinerary: journey 23, wait 2, transfers 2.
- Direct service: journey 28, wait 0, transfers 0.

Expected:
- Fastest -> trains 1,2,3.
- Fewer Transfers -> train 0.
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

STEM = "e2_transfer_network"
WIDTH = 21
HEIGHT = 13
HORIZON = 30

# Solver-balanced final E2.
# Still visibly more complex than the original 18-vs-4/4/4 setup,
# but small enough for repeated five-profile evaluation.
DIRECT_PATH = manhattan_path([
    (2, 0),
    (2, 5),
    (5, 5),
    (5, 9),
    (2, 9),
    (2, 13),
    (5, 13),
    (5, 17),
])

T1_PATH = manhattan_path([
    (9, 0),
    (9, 3),
    (11, 3),
    (11, 5),
    (10, 5),
    (9, 5),
])

T2_PATH = manhattan_path([
    (9, 7),
    (9, 10),
    (11, 10),
    (11, 12),
    (10, 12),
    (9, 12),
])

T3_PATH = manhattan_path([
    (9, 14),
    (9, 17),
    (11, 17),
    (11, 19),
    (10, 19),
    (9, 19),
])

DIRECT_ORIGIN, DIRECT_DESTINATION = (2, 1), (5, 16)
T1_ORIGIN, T1_B = (9, 1), (10, 5)
T2_B, T2_C = (9, 8), (10, 12)
T3_C, T3_DESTINATION = (9, 15), (10, 19)

PATHS = [DIRECT_PATH, T1_PATH, T2_PATH, T3_PATH]
STARTS = [DIRECT_ORIGIN, T1_ORIGIN, T2_B, T3_C]
TARGETS = [DIRECT_DESTINATION, T1_B, T2_C, T3_DESTINATION]

# first_station_visit = earliest_departure + 2
# transfer itinerary: 2->8, 9->15, 16->22
RELEASES = [0, 0, 8, 16]

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
            "direct": DIRECT_PATH,
            "leg1": T1_PATH,
            "leg2": T2_PATH,
            "leg3": T3_PATH,
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
    return f"""% RS42 E2 - Curved Transfer Network

flatland_waypoint(0,wp_direct_origin,{DIRECT_ORIGIN[0]},{DIRECT_ORIGIN[1]}).
flatland_waypoint(0,wp_direct_destination,{DIRECT_DESTINATION[0]},{DIRECT_DESTINATION[1]}).
station(origin,0,wp_direct_origin).
station(destination,0,wp_direct_destination).
must_visit(0,origin).
must_visit(0,destination).
station_order(0,origin,destination).

flatland_waypoint(1,wp_t1_origin,{T1_ORIGIN[0]},{T1_ORIGIN[1]}).
flatland_waypoint(1,wp_t1_b,{T1_B[0]},{T1_B[1]}).
station(origin,1,wp_t1_origin).
station(station_b,1,wp_t1_b).
must_visit(1,origin).
must_visit(1,station_b).
station_order(1,origin,station_b).

flatland_waypoint(2,wp_t2_b,{T2_B[0]},{T2_B[1]}).
flatland_waypoint(2,wp_t2_c,{T2_C[0]},{T2_C[1]}).
station(station_b,2,wp_t2_b).
station(station_c,2,wp_t2_c).
must_visit(2,station_b).
must_visit(2,station_c).
station_order(2,station_b,station_c).

flatland_waypoint(3,wp_t3_c,{T3_C[0]},{T3_C[1]}).
flatland_waypoint(3,wp_t3_destination,{T3_DESTINATION[0]},{T3_DESTINATION[1]}).
station(station_c,3,wp_t3_c).
station(destination,3,wp_t3_destination).
must_visit(3,station_c).
must_visit(3,destination).
station_order(3,station_c,destination).

passenger(p1).
passenger_origin(p1,origin).
passenger_destination(p1,destination).

% Final E2 timetable using the actual route lengths.
% Direct:   2 -> 26 = journey 24
% Transfer: 2 -> 9, 10 -> 17, 18 -> 25 = journey 23, wait 2
:- first_station_visit(0,origin,T), T != 2.
:- first_station_visit(0,destination,T), T != 26.

:- first_station_visit(1,origin,T), T != 2.
:- first_station_visit(1,station_b,T), T != 9.
:- first_station_visit(2,station_b,T), T != 10.
:- first_station_visit(2,station_c,T), T != 17.
:- first_station_visit(3,station_c,T), T != 18.
:- first_station_visit(3,destination,T), T != 25.
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
        for profile in ["fastest", "fewest_transfers"]:
            status, atoms, _ = run_clingo(
                ROOT,
                env_lp,
                scenario_file,
                profile_path(ROOT, profile),
                show_file,
                timeout=150,
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

    if STEPS != [24, 7, 7, 7]:
        raise RuntimeError("Unexpected E2 movement lengths: {}".format(STEPS))
    if TURNS != [6, 3, 3, 3]:
        raise RuntimeError("Unexpected E2 route turns: {}".format(TURNS))
    assert_internal_stations()

    existing = [path for path in outputs() if path.exists()]
    if existing and not args.overwrite:
        raise RuntimeError("E2 exists. Run with --overwrite after verification.")

    print("Building curved E2...")
    env = build_environment()
    env_lp_text = convert_to_clingo(env)
    scenario = scenario_text()
    results = verify(env_lp_text, scenario)

    fastest = results["fastest"]
    fewest = results["fewest_transfers"]

    if (
        fastest["journey"] != 23
        or fastest["transfers"] != 2
        or [leg["train"] for leg in fastest["legs"]] != [1, 2, 3]
    ):
        raise RuntimeError("Fastest trade-off failed: {}".format(fastest))

    if (
        fewest["journey"] != 24
        or fewest["transfers"] != 0
        or [leg["train"] for leg in fewest["legs"]] != [0]
    ):
        raise RuntimeError("Fewer Transfers trade-off failed: {}".format(fewest))

    if args.overwrite:
        archive = (
            ROOT / "experiments" / "_archive" /
            ("e2_before_curved_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
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

    print("E2 CURVED BUILD: PASS")
    print("  Fastest: journey=23, transfers=2")
    print("  Fewer Transfers: journey=24, transfers=0")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
