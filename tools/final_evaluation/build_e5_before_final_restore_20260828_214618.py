"""
RS42 E5 — Final Frozen Mixed Preference Network.

This is the previously validated E5 configuration.

Important:
- Do not enlarge this environment again.
- The builder only constructs and saves the environment.
- Profile optimization belongs in the final evaluation runner, not here.

Previously validated passenger outcomes:
Fastest         -> journey 14, wait 2, transfers 2
Less Waiting    -> journey 18, wait 0, transfers 0
Fewer Transfers -> journey 18, wait 0, transfers 0
Simple Journey  -> journey 16, wait 1, transfers 1
Balanced        -> journey 18, wait 0, transfers 0
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.convert import convert_to_clingo
from modules.save import save_png

from flatland.envs.rail_generators import rail_from_grid_transition_map
from flatland.envs.rail_env import RailEnv
from flatland.envs.observations import GlobalObsForRailEnv
from flatland.envs.malfunction_generators import (
    MalfunctionParameters,
    ParamMalfunctionGen,
)

from tools.final_evaluation.evaluation_generators import (
    EvaluationLineGenerator,
)

from tools.final_evaluation.final_eval_rail_geometry import (
    build_disjoint_rail,
    initial_direction,
    manhattan_path,
    route_steps,
    route_turns,
)


STEM = "e5_mixed_preferences"

WIDTH = 20
HEIGHT = 24
HORIZON = 22


# ----------------------------------------------------------------------
# EXACT PREVIOUSLY VALIDATED E5 GEOMETRY
# ----------------------------------------------------------------------

DIRECT = manhattan_path([
    (2, 0),
    (2, 6),
    (4, 6),
    (4, 12),
    (2, 12),
    (2, 16),
])

FAST1 = manhattan_path([
    (7, 0),
    (7, 2),
    (6, 2),
    (6, 5),
])

FAST2 = manhattan_path([
    (9, 4),
    (9, 6),
    (10, 6),
    (10, 9),
])

FAST3 = manhattan_path([
    (12, 8),
    (12, 10),
    (11, 10),
    (11, 13),
])

COMP1 = manhattan_path([
    (18, 0),
    (18, 4),
    (16, 4),
    (16, 7),
])

COMP2 = manhattan_path([
    (22, 6),
    (22, 10),
    (20, 10),
    (20, 14),
])


PATHS = [
    DIRECT,
    FAST1,
    FAST2,
    FAST3,
    COMP1,
    COMP2,
]


STARTS = [
    (2, 1),
    (7, 1),
    (9, 5),
    (12, 9),
    (18, 1),
    (22, 7),
]


TARGETS = [
    (2, 15),
    (6, 4),
    (10, 8),
    (11, 12),
    (16, 6),
    (20, 13),
]


RELEASES = [
    0,
    0,
    5,
    10,
    0,
    8,
]


STEPS = [
    route_steps(path, start, target)
    for path, start, target
    in zip(PATHS, STARTS, TARGETS)
]


TURNS = [
    route_turns(path, start, target)
    for path, start, target
    in zip(PATHS, STARTS, TARGETS)
]


OUT_PKL = (
    ROOT
    / "envs"
    / "pkl"
    / f"{STEM}.pkl"
)

OUT_LP = (
    ROOT
    / "envs"
    / "lp"
    / f"{STEM}.lp"
)

OUT_PNG = (
    ROOT
    / "envs"
    / "png"
    / f"{STEM}.png"
)

OUT_SCENARIO = (
    ROOT
    / "asp"
    / "scenarios"
    / f"{STEM}.lp"
)

OUT_META = (
    ROOT
    / "experiments"
    / "final_evaluation"
    / "configs"
    / f"{STEM}.json"
)


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--overwrite",
        action="store_true",
    )

    return parser.parse_args()


def validate_geometry():
    if STEPS != [
        18,
        4,
        4,
        4,
        7,
        8,
    ]:
        raise RuntimeError(
            "Unexpected E5 movement lengths: {}"
            .format(STEPS)
        )

    # The original validated setup has:
    # direct = 4 turns
    # fast legs = 2 each
    # compromise legs = 2 each
    if TURNS != [
        4,
        2,
        2,
        2,
        2,
        2,
    ]:
        raise RuntimeError(
            "Unexpected E5 turn counts: {}"
            .format(TURNS)
        )

    # Confirm start/target cells are internal to every path.
    for index, (
        path,
        start,
        target,
    ) in enumerate(
        zip(
            PATHS,
            STARTS,
            TARGETS,
        )
    ):
        start_i = path.index(start)
        target_i = path.index(target)

        if start_i <= 0:
            raise RuntimeError(
                "Route {} start is not internal."
                .format(index)
            )

        if target_i >= len(path) - 1:
            raise RuntimeError(
                "Route {} target is not internal."
                .format(index)
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
        rail_generator=rail_from_grid_transition_map(
            rail
        ),
        line_generator=EvaluationLineGenerator(
            positions=STARTS,
            directions=[
                initial_direction(
                    path,
                    start,
                )
                for path, start
                in zip(
                    PATHS,
                    STARTS,
                )
            ],
            targets=TARGETS,
            speeds=[1.0] * 6,
        ),
        number_of_agents=6,
        obs_builder_object=GlobalObsForRailEnv(),
        malfunction_generator=ParamMalfunctionGen(
            MalfunctionParameters(
                0.0,
                0,
                0,
            )
        ),
        remove_agents_at_target=True,
        random_seed=42,
    )

    env.reset(
        random_seed=42
    )

    env._max_episode_steps = HORIZON

    for agent, release, steps in zip(
        env.agents,
        RELEASES,
        STEPS,
    ):
        agent.earliest_departure = release

        try:
            agent.latest_arrival = (
                release
                + 2
                + steps
            )
        except Exception:
            pass

    return env


def scenario_text():
    coords = list(
        zip(
            STARTS,
            TARGETS,
        )
    )

    return f"""% RS42 E5 - Frozen Validated Mixed Preference Network

% Direct Train 0
flatland_waypoint(0,wp_d_o,{coords[0][0][0]},{coords[0][0][1]}).
flatland_waypoint(0,wp_d_d,{coords[0][1][0]},{coords[0][1][1]}).
station(origin,0,wp_d_o).
station(destination,0,wp_d_d).
must_visit(0,origin).
must_visit(0,destination).
station_order(0,origin,destination).

% Fast route: Train 1 -> Train 2 -> Train 3
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

% Compromise route: Train 4 -> Train 5
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

% Fixed service timetable.
%
% Direct:
%   2 -> 20
%   journey 18
%   wait 0
%   transfers 0
%
% Fast:
%   2 -> 6
%   7 -> 11
%   12 -> 16
%   journey 14
%   wait 2
%   transfers 2
%
% Compromise:
%   2 -> 9
%   10 -> 18
%   journey 16
%   wait 1
%   transfers 1

:- first_station_visit(0,origin,T), T != 2.
:- first_station_visit(0,destination,T), T != 20.

:- first_station_visit(1,origin,T), T != 2.
:- first_station_visit(1,station_b,T), T != 6.

:- first_station_visit(2,station_b,T), T != 7.
:- first_station_visit(2,station_c,T), T != 11.

:- first_station_visit(3,station_c,T), T != 12.
:- first_station_visit(3,destination,T), T != 16.

:- first_station_visit(4,origin,T), T != 2.
:- first_station_visit(4,station_h,T), T != 9.

:- first_station_visit(5,station_h,T), T != 10.
:- first_station_visit(5,destination,T), T != 18.
"""


def save_outputs(
    env,
    env_lp_text,
    scenario,
):
    for path in [
        OUT_PKL,
        OUT_LP,
        OUT_PNG,
        OUT_SCENARIO,
        OUT_META,
    ]:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    with OUT_PKL.open(
        "wb"
    ) as handle:
        pickle.dump(
            env,
            handle,
            protocol=pickle.HIGHEST_PROTOCOL,
        )

    OUT_LP.write_text(
        env_lp_text,
        encoding="utf-8",
    )

    OUT_SCENARIO.write_text(
        scenario,
        encoding="utf-8",
    )

    OUT_META.write_text(
        json.dumps(
            {
                "environment": STEM,
                "status": "FROZEN_VALIDATED_CONFIGURATION",
                "purpose": (
                    "integrated mixed-preference "
                    "passenger experiment"
                ),
                "movement_steps": STEPS,
                "route_turns": TURNS,
                "validated_reference_results": {
                    "fastest": {
                        "journey": 14,
                        "wait": 2,
                        "transfers": 2,
                    },
                    "least_waiting": {
                        "journey": 18,
                        "wait": 0,
                        "transfers": 0,
                    },
                    "fewest_transfers": {
                        "journey": 18,
                        "wait": 0,
                        "transfers": 0,
                    },
                    "simple": {
                        "journey": 16,
                        "wait": 1,
                        "transfers": 1,
                    },
                    "balanced": {
                        "journey": 18,
                        "wait": 0,
                        "transfers": 0,
                    },
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    prefix = (
        str(ROOT / "envs")
        + str(Path("/"))
    )

    save_png(
        env,
        STEM,
        prefix,
    )


def main():
    args = parse_args()

    validate_geometry()

    if (
        OUT_PKL.exists()
        and not args.overwrite
    ):
        raise RuntimeError(
            "E5 exists. Use --overwrite "
            "to intentionally rebuild."
        )

    print(
        "Building frozen validated E5..."
    )

    print(
        "  movement steps:",
        STEPS,
    )

    print(
        "  route turns:",
        TURNS,
    )

    env = build_environment()

    env_lp_text = convert_to_clingo(
        env
    )

    scenario = scenario_text()

    save_outputs(
        env,
        env_lp_text,
        scenario,
    )

    print()
    print(
        "E5 BUILD: PASS"
    )

    print(
        "  No Clingo optimization was run during building."
    )

    print(
        "  Run profile optimization only in the final evaluation."
    )

    print(
        "  PNG:",
        OUT_PNG.relative_to(ROOT),
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
