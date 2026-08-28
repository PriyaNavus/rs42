
"""
Promote Flatland benchmark Test_02 / Level_8 into RS42 E5.

The physical rail topology comes directly from:
    benchmarks/environments/Test_02/Level_8.pkl

Only six services are retained for the E5 passenger experiment.

The script:
- loads the Flatland persistence file correctly;
- reconstructs actual shortest paths on the benchmark rail;
- selects Direct / Fast / Compromise services automatically;
- adds intermediate mandatory route waypoints to control ASP search;
- creates the canonical E5 PKL / LP / PNG / scenario;
- DOES NOT run Clingo during building.

Run from RS42 root:

    conda activate flatlandrs42
    python promote_test02_level8_to_e5.py
"""

from __future__ import annotations

import itertools
import json
import pickle
import shutil
import sys
from collections import deque
from datetime import datetime
from pathlib import Path


ROOT = Path.cwd().resolve()

if not (ROOT / "solve.py").exists():
    raise SystemExit(
        "ERROR: Run this script from the RS42 repository root."
    )


SOURCE = (
    ROOT
    / "benchmarks"
    / "environments"
    / "Test_02"
    / "Level_8.pkl"
)

STEM = "e5_mixed_preferences"

OUT_PKL = ROOT / "envs" / "pkl" / f"{STEM}.pkl"
OUT_LP = ROOT / "envs" / "lp" / f"{STEM}.lp"
OUT_PNG = ROOT / "envs" / "png" / f"{STEM}.png"
OUT_SCENARIO = ROOT / "asp" / "scenarios" / f"{STEM}.lp"

OUT_META = (
    ROOT
    / "experiments"
    / "final_evaluation"
    / "configs"
    / f"{STEM}.json"
)

ARCHIVE_ROOT = (
    ROOT
    / "experiments"
    / "_archive"
)


try:
    from flatland.envs.persistence import RailEnvPersister
    from flatland.envs.rail_generators import rail_from_grid_transition_map
    from flatland.envs.rail_env import RailEnv
    from flatland.envs.observations import GlobalObsForRailEnv
    from flatland.envs.malfunction_generators import (
        MalfunctionParameters,
        ParamMalfunctionGen,
    )

    from modules.convert import convert_to_clingo
    from modules.save import save_png

    from tools.final_evaluation.evaluation_generators import (
        EvaluationLineGenerator,
    )

except Exception as exc:
    raise SystemExit(
        "ERROR: Required RS42/Flatland import failed: {}".format(exc)
    )


DIR_DELTA = {
    0: (-1, 0),  # north
    1: (0, 1),   # east
    2: (1, 0),   # south
    3: (0, -1),  # west
}


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

    return value


def state_shortest_path(rail, start, direction, target):
    """
    Direction-aware BFS over Flatland rail transitions.

    Returns states:
        [(row, col, direction), ...]
    including start and target.
    """

    start = tuple(start)
    target = tuple(target)
    initial = (
        int(start[0]),
        int(start[1]),
        int(direction),
    )

    queue = deque([initial])
    parent = {initial: None}

    goal = None

    while queue:
        row, col, heading = queue.popleft()

        if (row, col) == target:
            goal = (row, col, heading)
            break

        transitions = rail.get_transitions(
            row,
            col,
            heading,
        )

        for next_direction, allowed in enumerate(transitions):
            if not allowed:
                continue

            dr, dc = DIR_DELTA[next_direction]
            nr = row + dr
            nc = col + dc

            state = (
                nr,
                nc,
                int(next_direction),
            )

            if state in parent:
                continue

            parent[state] = (
                row,
                col,
                heading,
            )

            queue.append(state)

    if goal is None:
        return None

    path = []
    current = goal

    while current is not None:
        path.append(current)
        current = parent[current]

    path.reverse()

    return path


def path_turns(states):
    if not states or len(states) < 2:
        return 0

    directions = [
        state[2]
        for state in states
    ]

    turns = 0

    for previous, current in zip(
        directions,
        directions[1:],
    ):
        if previous != current:
            turns += 1

    return turns


def route_record(source_id, agent, states):
    return {
        "source_train": int(source_id),
        "start": tuple(
            int(x)
            for x in agent.initial_position
        ),
        "target": tuple(
            int(x)
            for x in agent.target
        ),
        "direction": int(
            agent.initial_direction
        ),
        "length": int(
            len(states) - 1
        ),
        "turns": int(
            path_turns(states)
        ),
        "states": states,
    }


def select_roles(routes):
    """
    Choose six distinct benchmark trains.

    The timetable will enforce:
        Fast < Compromise < Direct

    Physical route complexity is used to prefer:
        Compromise = low turns
        Direct     = higher turns
        Fast       = high combined turns
    """

    usable = [
        route
        for route in routes
        if 7 <= route["length"] <= 55
    ]

    if len(usable) < 6:
        usable = list(routes)

    # ----------------------------------------------------------
    # Compromise pair:
    # prefer two routes with low combined turns and manageable
    # combined distance.
    # ----------------------------------------------------------

    pair_candidates = []

    for pair in itertools.combinations(
        usable,
        2,
    ):
        total_length = sum(
            route["length"]
            for route in pair
        )

        total_turns = sum(
            route["turns"]
            for route in pair
        )

        pair_candidates.append(
            (
                total_turns,
                total_length,
                pair,
            )
        )

    pair_candidates.sort(
        key=lambda item: (
            item[0],
            item[1],
        )
    )

    compromise = pair_candidates[0][2]

    used = {
        route["source_train"]
        for route in compromise
    }

    remaining = [
        route
        for route in usable
        if route["source_train"] not in used
    ]

    compromise_turns = sum(
        route["turns"]
        for route in compromise
    )

    # ----------------------------------------------------------
    # Direct:
    # prefer a single visibly turn-rich route.
    # ----------------------------------------------------------

    direct_candidates = sorted(
        remaining,
        key=lambda route: (
            route["turns"],
            route["length"],
        ),
        reverse=True,
    )

    direct = direct_candidates[0]

    used.add(
        direct["source_train"]
    )

    remaining = [
        route
        for route in remaining
        if route["source_train"]
        != direct["source_train"]
    ]

    # ----------------------------------------------------------
    # Fast triple:
    # among remaining routes, prefer the shortest combined
    # movement while retaining meaningful turn complexity.
    # ----------------------------------------------------------

    triple_candidates = []

    for triple in itertools.combinations(
        remaining,
        3,
    ):
        total_length = sum(
            route["length"]
            for route in triple
        )

        total_turns = sum(
            route["turns"]
            for route in triple
        )

        # Prefer a fast route that is not simpler than compromise.
        complexity_penalty = (
            0
            if total_turns > compromise_turns
            else 1000
        )

        triple_candidates.append(
            (
                complexity_penalty
                + total_length,
                -total_turns,
                triple,
            )
        )

    triple_candidates.sort(
        key=lambda item: (
            item[0],
            item[1],
        )
    )

    fast = triple_candidates[0][2]

    return {
        "direct": [direct],
        "fast": list(fast),
        "compromise": list(compromise),
    }


def waypoint_indices(states):
    """
    Choose two internal route-shaping points.

    They deliberately stay away from start/target.
    """

    moves = len(states) - 1

    if moves < 6:
        return []

    first = max(
        2,
        moves // 3,
    )

    second = min(
        moves - 2,
        (2 * moves) // 3,
    )

    indices = sorted(
        set(
            [
                first,
                second,
            ]
        )
    )

    return [
        index
        for index in indices
        if 0 < index < moves
    ]


def make_timetable(roles):
    """
    Use actual physical travel lengths, then add only enough
    timetable slack to guarantee:

        Fast < Compromise < Direct

    This avoids impossible arrival constraints.
    """

    fast_lengths = [
        route["length"]
        for route in roles["fast"]
    ]

    compromise_lengths = [
        route["length"]
        for route in roles["compromise"]
    ]

    direct_length = roles[
        "direct"
    ][0]["length"]

    fast_journey = (
        sum(fast_lengths)
        + 2
    )

    compromise_minimum = (
        sum(compromise_lengths)
        + 1
    )

    compromise_journey = max(
        compromise_minimum,
        fast_journey + 3,
    )

    direct_journey = max(
        direct_length,
        compromise_journey + 4,
    )

    # Origin visit begins at t=2.
    fast_visits = []

    current = 2

    for index, length in enumerate(
        fast_lengths
    ):
        start_visit = current
        end_visit = (
            start_visit
            + length
        )

        fast_visits.append(
            (
                start_visit,
                end_visit,
            )
        )

        if index < len(
            fast_lengths
        ) - 1:
            current = (
                end_visit
                + 1
            )

    comp_first_length = (
        compromise_lengths[0]
    )

    comp_second_length = (
        compromise_lengths[1]
    )

    comp_first = (
        2,
        2 + comp_first_length,
    )

    comp_second_start = (
        comp_first[1]
        + 1
    )

    comp_second_earliest_end = (
        comp_second_start
        + comp_second_length
    )

    comp_target = (
        2
        + compromise_journey
    )

    # If the desired compromise journey requires extra timetable
    # slack, put it into the second service.
    comp_second = (
        comp_second_start,
        max(
            comp_second_earliest_end,
            comp_target,
        ),
    )

    direct = (
        2,
        2 + direct_journey,
    )

    return {
        "fast": fast_visits,
        "compromise": [
            comp_first,
            comp_second,
        ],
        "direct": direct,
        "journeys": {
            "fast": fast_visits[-1][1] - 2,
            "compromise": comp_second[1] - 2,
            "direct": direct[1] - 2,
        },
    }


def route_station_block(
    new_train,
    route,
    start_station,
    end_station,
    start_visit,
    end_visit,
):
    """
    Generate the train's passenger endpoints plus two intermediate
    mandatory waypoints from the real benchmark shortest path.
    """

    states = route["states"]

    items = [
        (
            start_station,
            states[0],
            start_visit,
        )
    ]

    for mid_number, index in enumerate(
        waypoint_indices(states),
        start=1,
    ):
        row, col, _ = states[index]

        station_name = (
            "r{}_mid{}"
            .format(
                new_train,
                mid_number,
            )
        )

        visit = (
            start_visit
            + index
        )

        items.append(
            (
                station_name,
                states[index],
                visit,
            )
        )

    items.append(
        (
            end_station,
            states[-1],
            end_visit,
        )
    )

    lines = [
        "% Train {} <- benchmark Train {}".format(
            new_train,
            route["source_train"],
        )
    ]

    for station_name, state, _ in items:
        row, col, _direction = state

        waypoint_name = (
            "wp_{}_{}"
            .format(
                new_train,
                station_name,
            )
        )

        lines.append(
            "flatland_waypoint({},{},{},{})."
            .format(
                new_train,
                waypoint_name,
                row,
                col,
            )
        )

        lines.append(
            "station({},{},{})."
            .format(
                station_name,
                new_train,
                waypoint_name,
            )
        )

        lines.append(
            "must_visit({},{})"
            ".".format(
                new_train,
                station_name,
            )
        )

    for (
        previous,
        current,
    ) in zip(
        items,
        items[1:],
    ):
        lines.append(
            "station_order({},{},{})."
            .format(
                new_train,
                previous[0],
                current[0],
            )
        )

    # Fix route-shaping waypoint times as well.
    # This keeps the ASP search close to the benchmark shortest path.
    for station_name, _state, visit in items:
        lines.extend(
            [
                ":- first_station_visit("
                "{},{},T), T != {}."
                .format(
                    new_train,
                    station_name,
                    visit,
                )
            ]
        )

    return "\n".join(lines)


def make_scenario(
    selected,
    timetable,
):
    lines = [
        "% RS42 E5 - Test_02 Level_8 promoted environment",
        "% Full benchmark rail topology, six selected services.",
        "",
    ]

    # New train indices:
    # 0 direct
    # 1,2,3 fast
    # 4,5 compromise

    direct = selected["direct"][0]

    lines.append(
        route_station_block(
            0,
            direct,
            "origin",
            "destination",
            timetable["direct"][0],
            timetable["direct"][1],
        )
    )

    lines.append("")

    fast_station_pairs = [
        (
            "origin",
            "station_b",
        ),
        (
            "station_b",
            "station_c",
        ),
        (
            "station_c",
            "destination",
        ),
    ]

    for offset, (
        route,
        station_pair,
        visits,
    ) in enumerate(
        zip(
            selected["fast"],
            fast_station_pairs,
            timetable["fast"],
        ),
        start=1,
    ):
        lines.append(
            route_station_block(
                offset,
                route,
                station_pair[0],
                station_pair[1],
                visits[0],
                visits[1],
            )
        )

        lines.append("")

    compromise_station_pairs = [
        (
            "origin",
            "station_h",
        ),
        (
            "station_h",
            "destination",
        ),
    ]

    for offset, (
        route,
        station_pair,
        visits,
    ) in enumerate(
        zip(
            selected["compromise"],
            compromise_station_pairs,
            timetable["compromise"],
        ),
        start=4,
    ):
        lines.append(
            route_station_block(
                offset,
                route,
                station_pair[0],
                station_pair[1],
                visits[0],
                visits[1],
            )
        )

        lines.append("")

    lines.extend(
        [
            "passenger(p1).",
            "passenger_origin(p1,origin).",
            "passenger_destination(p1,destination).",
            "",
        ]
    )

    return (
        "\n".join(lines)
        + "\n"
    )


def archive_existing_e5():
    existing = [
        OUT_PKL,
        OUT_LP,
        OUT_PNG,
        OUT_SCENARIO,
        OUT_META,
    ]

    existing = [
        path
        for path in existing
        if path.exists()
    ]

    if not existing:
        return None

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    archive = (
        ARCHIVE_ROOT
        / "e5_before_test02_level8_{}".format(
            stamp
        )
    )

    archive.mkdir(
        parents=True,
        exist_ok=True,
    )

    for path in existing:
        shutil.copy2(
            str(path),
            str(
                archive
                / path.name
            ),
        )

    return archive


def main():
    if not SOURCE.exists():
        raise RuntimeError(
            "Missing source benchmark: {}".format(
                SOURCE
            )
        )

    print()
    print("=" * 72)
    print("RS42 E5 <- TEST_02 LEVEL_8")
    print("=" * 72)
    print()

    source_env, _source_dict = (
        RailEnvPersister.load_new(
            str(SOURCE)
        )
    )

    routes = []

    print(
        "Computing actual benchmark train routes..."
    )

    for source_id, agent in enumerate(
        source_env.agents
    ):
        states = state_shortest_path(
            source_env.rail,
            agent.initial_position,
            agent.initial_direction,
            agent.target,
        )

        if states is None:
            continue

        route = route_record(
            source_id,
            agent,
            states,
        )

        routes.append(route)

        print(
            "  Train {:>2}: length={:<3} turns={:<2} {} -> {}"
            .format(
                source_id,
                route["length"],
                route["turns"],
                route["start"],
                route["target"],
            )
        )

    if len(routes) < 6:
        raise RuntimeError(
            "Fewer than six usable benchmark routes were found."
        )

    selected = select_roles(
        routes
    )

    timetable = make_timetable(
        selected
    )

    ordered = (
        selected["direct"]
        + selected["fast"]
        + selected["compromise"]
    )

    print()
    print("SELECTED SERVICES")
    print("-----------------")

    role_names = [
        "Direct",
        "Fast leg 1",
        "Fast leg 2",
        "Fast leg 3",
        "Compromise leg 1",
        "Compromise leg 2",
    ]

    for new_id, (
        role,
        route,
    ) in enumerate(
        zip(
            role_names,
            ordered,
        )
    ):
        print(
            "  New Train {} | {:<18} | source={} length={} turns={}"
            .format(
                new_id,
                role,
                route["source_train"],
                route["length"],
                route["turns"],
            )
        )

    print()
    print("PASSENGER JOURNEY TARGETS")
    print("-------------------------")
    print(
        "  Fast:       {}".format(
            timetable["journeys"]["fast"]
        )
    )
    print(
        "  Compromise: {}".format(
            timetable["journeys"]["compromise"]
        )
    )
    print(
        "  Direct:     {}".format(
            timetable["journeys"]["direct"]
        )
    )

    # ----------------------------------------------------------
    # Build a new six-agent environment on the ORIGINAL full rail.
    # ----------------------------------------------------------

    positions = [
        route["start"]
        for route in ordered
    ]

    directions = [
        route["direction"]
        for route in ordered
    ]

    targets = [
        route["target"]
        for route in ordered
    ]

    release_visits = [
        timetable["direct"][0],
        timetable["fast"][0][0],
        timetable["fast"][1][0],
        timetable["fast"][2][0],
        timetable["compromise"][0][0],
        timetable["compromise"][1][0],
    ]

    releases = [
        max(
            0,
            int(visit) - 2,
        )
        for visit in release_visits
    ]

    latest_visits = [
        timetable["direct"][1],
        timetable["fast"][0][1],
        timetable["fast"][1][1],
        timetable["fast"][2][1],
        timetable["compromise"][0][1],
        timetable["compromise"][1][1],
    ]

    env = RailEnv(
        width=source_env.width,
        height=source_env.height,
        rail_generator=rail_from_grid_transition_map(
            source_env.rail
        ),
        line_generator=EvaluationLineGenerator(
            positions=positions,
            directions=directions,
            targets=targets,
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

    max_visit = max(
        latest_visits
    )

    env._max_episode_steps = (
        max_visit
        + 6
    )

    for index, agent in enumerate(
        env.agents
    ):
        agent.earliest_departure = (
            releases[index]
        )

        try:
            agent.latest_arrival = (
                latest_visits[index]
            )
        except Exception:
            pass

    scenario = make_scenario(
        selected,
        timetable,
    )

    env_lp_text = convert_to_clingo(
        env
    )

    archive = archive_existing_e5()

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

    metadata = {
        "environment": STEM,
        "source_benchmark": str(
            SOURCE.relative_to(ROOT)
        ),
        "source_grid": [
            int(source_env.height),
            int(source_env.width),
        ],
        "selected_services": {
            role: {
                "new_train": new_id,
                "source_train": route["source_train"],
                "start": plain(
                    route["start"]
                ),
                "target": plain(
                    route["target"]
                ),
                "direction": route["direction"],
                "shortest_path_length": route["length"],
                "route_turns": route["turns"],
            }
            for new_id, (
                role,
                route,
            ) in enumerate(
                zip(
                    role_names,
                    ordered,
                )
            )
        },
        "passenger_journey_targets": (
            timetable["journeys"]
        ),
        "max_episode_steps": (
            env._max_episode_steps
        ),
        "notes": [
            "Full Test_02 Level_8 rail topology retained.",
            "Only six services are active in E5.",
            "Intermediate shortest-path waypoints constrain ASP route search.",
            "Builder performs no Clingo optimization.",
        ],
    }

    OUT_META.write_text(
        json.dumps(
            metadata,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # RS42's save_png helper expects the envs root and creates envs/png.
    prefix = (
        str(ROOT / "envs")
        + str(Path("/"))
    )

    save_png(
        env,
        STEM,
        prefix,
    )

    print()
    print("=" * 72)
    print("E5 TEST_02 PROMOTION: PASS")
    print("=" * 72)

    if archive:
        print(
            "Previous E5 archived:",
            archive.relative_to(ROOT),
        )

    print(
        "PKL:",
        OUT_PKL.relative_to(ROOT),
    )
    print(
        "LP:",
        OUT_LP.relative_to(ROOT),
    )
    print(
        "PNG:",
        OUT_PNG.relative_to(ROOT),
    )
    print(
        "Scenario:",
        OUT_SCENARIO.relative_to(ROOT),
    )
    print(
        "Metadata:",
        OUT_META.relative_to(ROOT),
    )

    print()
    print(
        "No Clingo optimization was run."
    )

    print()
    print(
        "Next: inspect envs/png/e5_mixed_preferences.png "
        "and launch the UI."
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
