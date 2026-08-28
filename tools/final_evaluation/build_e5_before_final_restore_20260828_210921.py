"""
RS42 E5 — Final Solver-Safe Mixed Preference Network.

This is the final E5 geometry.

It is deliberately larger and more complex than the original validated E5,
but kept below the route/horizon size that caused the 300-second timeout.

Passenger alternatives:

A) Fast multi-transfer
   movement: 5 + 5 + 5
   journey: 17
   wait: 2
   transfers: 2
   route turns: high

B) Direct
   movement: 22
   journey: 22
   wait: 0
   transfers: 0
   route turns: medium

C) Compromise
   movement: 9 + 10
   journey: 20
   wait: 1
   transfers: 1
   route turns: low

Expected semantic behavior:
- Fastest -> A
- Less Waiting -> B
- Fewer Transfers -> B
- Simple Journey -> C
- Balanced is measured in the final evaluation.
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

from tools.final_evaluation.final_eval_builder_common import (
    chosen_legs,
    metric_show_text,
    passenger_metric,
    profile_path,
    require_backend,
    run_clingo,
)


STEM = "e5_mixed_preferences"

WIDTH = 22
HEIGHT = 22
HORIZON = 30


# ----------------------------------------------------------------------
# Physical routes
# ----------------------------------------------------------------------

# Direct: 22 evaluated movement steps, 7 turns.
DIRECT = manhattan_path([
    (2, 0),
    (2, 5),
    (5, 5),
    (5, 8),
    (3, 8),
    (3, 11),
    (6, 11),
    (6, 14),
    (4, 14),
])


# Fast route: three five-step zig-zag services.
# Each has four route turns.
FAST1 = manhattan_path([
    (9, 0),
    (9, 2),
    (8, 2),
    (8, 3),
    (9, 3),
    (9, 5),
])

FAST2 = manhattan_path([
    (9, 7),
    (9, 9),
    (10, 9),
    (10, 10),
    (9, 10),
    (9, 12),
])

FAST3 = manhattan_path([
    (9, 14),
    (9, 16),
    (8, 16),
    (8, 17),
    (9, 17),
    (9, 19),
])


# Compromise route: longer individual legs but only two turns per service.
COMP1 = manhattan_path([
    (16, 0),
    (16, 4),
    (19, 4),
    (19, 8),
])

COMP2 = manhattan_path([
    (20, 10),
    (20, 14),
    (16, 14),
    (16, 18),
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
    (9, 1),
    (9, 8),
    (9, 15),
    (16, 1),
    (20, 11),
]


TARGETS = [
    (5, 14),
    (9, 4),
    (9, 11),
    (9, 18),
    (19, 7),
    (16, 17),
]


# first_station_visit for a starting station occurs at release + 2.
#
# Fast:
#   2 -> 7
#   8 -> 13
#   14 -> 19
#
# Compromise:
#   2 -> 11
#   12 -> 22
RELEASES = [
    0,
    0,
    6,
    12,
    0,
    10,
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


OUT_PKL = ROOT / "envs" / "pkl" / f"{STEM}.pkl"
OUT_LP = ROOT / "envs" / "lp" / f"{STEM}.lp"
OUT_PNG = ROOT / "envs" / "png" / f"{STEM}.png"

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

    parser.add_argument(
        "--full-check",
        action="store_true",
        help=(
            "Also run Balanced during builder validation. "
            "The default build checks the four controlled semantic profiles."
        ),
    )

    return parser.parse_args()


def validate_geometry():
    expected_steps = [
        22,
        5,
        5,
        5,
        9,
        10,
    ]

    expected_turns = [
        7,
        4,
        4,
        4,
        2,
        2,
    ]

    if STEPS != expected_steps:
        raise RuntimeError(
            "Unexpected E5 movement lengths: {} "
            "(expected {})".format(
                STEPS,
                expected_steps,
            )
        )

    if TURNS != expected_turns:
        raise RuntimeError(
            "Unexpected E5 route turns: {} "
            "(expected {})".format(
                TURNS,
                expected_turns,
            )
        )

    # Explicitly enforce a buffer rail cell before every start
    # and after every target.
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
        start_index = path.index(start)
        target_index = path.index(target)

        if start_index <= 0:
            raise RuntimeError(
                "route{} start {} has no leading rail buffer."
                .format(
                    index,
                    start,
                )
            )

        if target_index >= len(path) - 1:
            raise RuntimeError(
                "route{} target {} has no trailing rail buffer."
                .format(
                    index,
                    target,
                )
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

    return f"""% RS42 E5 - Final Solver-Safe Mixed Preference Network

% ------------------------------------------------------------------
% Direct service - Train 0
% ------------------------------------------------------------------

flatland_waypoint(
    0,
    wp_d_o,
    {coords[0][0][0]},
    {coords[0][0][1]}
).

flatland_waypoint(
    0,
    wp_d_d,
    {coords[0][1][0]},
    {coords[0][1][1]}
).

station(origin,0,wp_d_o).
station(destination,0,wp_d_d).

must_visit(0,origin).
must_visit(0,destination).

station_order(
    0,
    origin,
    destination
).


% ------------------------------------------------------------------
% Fast multi-transfer journey - Trains 1 -> 2 -> 3
% ------------------------------------------------------------------

flatland_waypoint(
    1,
    wp_f1_o,
    {coords[1][0][0]},
    {coords[1][0][1]}
).

flatland_waypoint(
    1,
    wp_f1_b,
    {coords[1][1][0]},
    {coords[1][1][1]}
).

station(origin,1,wp_f1_o).
station(station_b,1,wp_f1_b).

must_visit(1,origin).
must_visit(1,station_b).

station_order(
    1,
    origin,
    station_b
).


flatland_waypoint(
    2,
    wp_f2_b,
    {coords[2][0][0]},
    {coords[2][0][1]}
).

flatland_waypoint(
    2,
    wp_f2_c,
    {coords[2][1][0]},
    {coords[2][1][1]}
).

station(station_b,2,wp_f2_b).
station(station_c,2,wp_f2_c).

must_visit(2,station_b).
must_visit(2,station_c).

station_order(
    2,
    station_b,
    station_c
).


flatland_waypoint(
    3,
    wp_f3_c,
    {coords[3][0][0]},
    {coords[3][0][1]}
).

flatland_waypoint(
    3,
    wp_f3_d,
    {coords[3][1][0]},
    {coords[3][1][1]}
).

station(station_c,3,wp_f3_c).
station(destination,3,wp_f3_d).

must_visit(3,station_c).
must_visit(3,destination).

station_order(
    3,
    station_c,
    destination
).


% ------------------------------------------------------------------
% Compromise journey - Trains 4 -> 5
% ------------------------------------------------------------------

flatland_waypoint(
    4,
    wp_c1_o,
    {coords[4][0][0]},
    {coords[4][0][1]}
).

flatland_waypoint(
    4,
    wp_c1_h,
    {coords[4][1][0]},
    {coords[4][1][1]}
).

station(origin,4,wp_c1_o).
station(station_h,4,wp_c1_h).

must_visit(4,origin).
must_visit(4,station_h).

station_order(
    4,
    origin,
    station_h
).


flatland_waypoint(
    5,
    wp_c2_h,
    {coords[5][0][0]},
    {coords[5][0][1]}
).

flatland_waypoint(
    5,
    wp_c2_d,
    {coords[5][1][0]},
    {coords[5][1][1]}
).

station(station_h,5,wp_c2_h).
station(destination,5,wp_c2_d).

must_visit(5,station_h).
must_visit(5,destination).

station_order(
    5,
    station_h,
    destination
).


passenger(p1).
passenger_origin(
    p1,
    origin
).

passenger_destination(
    p1,
    destination
).


% ------------------------------------------------------------------
% Fixed timetable.
%
% Direct:
%   2 -> 24
%   journey = 22
%   wait = 0
%   transfers = 0
%
% Fast:
%   2 -> 7
%   8 -> 13
%   14 -> 19
%   journey = 17
%   wait = 2
%   transfers = 2
%
% Compromise:
%   2 -> 11
%   12 -> 22
%   journey = 20
%   wait = 1
%   transfers = 1
% ------------------------------------------------------------------

:- first_station_visit(
    0,
    origin,
    T
),
T != 2.

:- first_station_visit(
    0,
    destination,
    T
),
T != 24.


:- first_station_visit(
    1,
    origin,
    T
),
T != 2.

:- first_station_visit(
    1,
    station_b,
    T
),
T != 7.


:- first_station_visit(
    2,
    station_b,
    T
),
T != 8.

:- first_station_visit(
    2,
    station_c,
    T
),
T != 13.


:- first_station_visit(
    3,
    station_c,
    T
),
T != 14.

:- first_station_visit(
    3,
    destination,
    T
),
T != 19.


:- first_station_visit(
    4,
    origin,
    T
),
T != 2.

:- first_station_visit(
    4,
    station_h,
    T
),
T != 11.


:- first_station_visit(
    5,
    station_h,
    T
),
T != 12.

:- first_station_visit(
    5,
    destination,
    T
),
T != 22.
"""


def evaluate(
    env_lp_text,
    scenario,
    full_check=False,
):
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        env_lp = (
            tmpdir
            / "environment.lp"
        )

        scenario_file = (
            tmpdir
            / "scenario.lp"
        )

        show_file = (
            tmpdir
            / "show.lp"
        )

        env_lp.write_text(
            env_lp_text,
            encoding="utf-8",
        )

        scenario_file.write_text(
            scenario,
            encoding="utf-8",
        )

        show_file.write_text(
            metric_show_text(),
            encoding="utf-8",
        )

        profiles = [
            "fastest",
            "least_waiting",
            "fewest_transfers",
            "simple",
        ]

        if full_check:
            profiles.append(
                "balanced"
            )

        results = {}

        for profile in profiles:
            print(
                "  checking {}..."
                .format(profile)
            )

            status, atoms, costs = run_clingo(
                ROOT,
                env_lp,
                scenario_file,
                profile_path(
                    ROOT,
                    profile,
                ),
                show_file,
                timeout=150,
            )

            results[profile] = {
                "status": status,
                "journey": passenger_metric(
                    atoms,
                    "passenger_journey_time",
                ),
                "wait": passenger_metric(
                    atoms,
                    "passenger_transfer_wait",
                ),
                "transfers": passenger_metric(
                    atoms,
                    "transfer_count",
                ),
                "legs": chosen_legs(
                    atoms
                ),
                "costs": costs,
            }

        return results


def validate_results(results):
    fastest = results[
        "fastest"
    ]

    least = results[
        "least_waiting"
    ]

    fewest = results[
        "fewest_transfers"
    ]

    simple = results[
        "simple"
    ]

    if not (
        fastest["journey"] == 17
        and fastest["wait"] == 2
        and fastest["transfers"] == 2
    ):
        raise RuntimeError(
            "E5 Fastest check failed: {}"
            .format(
                fastest
            )
        )

    if not (
        least["journey"] == 22
        and least["wait"] == 0
        and least["transfers"] == 0
    ):
        raise RuntimeError(
            "E5 Less Waiting check failed: {}"
            .format(
                least
            )
        )

    if not (
        fewest["journey"] == 22
        and fewest["transfers"] == 0
    ):
        raise RuntimeError(
            "E5 Fewer Transfers check failed: {}"
            .format(
                fewest
            )
        )

    if not (
        simple["journey"] == 20
        and simple["transfers"] == 1
    ):
        raise RuntimeError(
            "E5 Simple Journey check failed: {}"
            .format(
                simple
            )
        )


def save_outputs(
    env,
    env_lp_text,
    scenario,
    results,
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
                "purpose": (
                    "integrated mixed-preference "
                    "passenger network"
                ),
                "geometry_version": (
                    "solver_safe_final_v1"
                ),
                "movement_steps": STEPS,
                "route_turns": TURNS,
                "expected_passenger_options": {
                    "fast": {
                        "journey": 17,
                        "wait": 2,
                        "transfers": 2,
                    },
                    "direct": {
                        "journey": 22,
                        "wait": 0,
                        "transfers": 0,
                    },
                    "compromise": {
                        "journey": 20,
                        "wait": 1,
                        "transfers": 1,
                    },
                },
                "builder_checks": results,
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

    require_backend(
        ROOT
    )

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
        "Building final solver-safe E5..."
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

    results = evaluate(
        env_lp_text,
        scenario,
        full_check=args.full_check,
    )

    validate_results(
        results
    )

    save_outputs(
        env,
        env_lp_text,
        scenario,
        results,
    )

    print()
    print(
        "E5 FINAL BUILD: PASS"
    )

    for profile, result in results.items():
        print(
            "  {}: journey={}, "
            "wait={}, transfers={}"
            .format(
                profile,
                result["journey"],
                result["wait"],
                result["transfers"],
            )
        )

    print()
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
