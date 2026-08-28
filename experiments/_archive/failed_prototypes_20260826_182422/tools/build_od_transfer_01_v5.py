"""
Build a real RS42 OD-transfer benchmark v4 using synchronized 3-train Flatland
environments for a verified Fastest-vs-Fewer-Transfers trade-off.

Run from the rs42 repository root:

    conda activate flatlandrs42
    python tools\build_od_transfer_01_v5.py

Optional:
    python tools\build_od_transfer_01_v5.py --max-seeds 40 --overwrite
"""

from __future__ import annotations

import argparse
import copy
import inspect
import itertools
import json
import os
import pickle
import random
import re
import shutil
import subprocess
import sys
import tempfile
from collections import deque
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.convert import convert_to_clingo
from modules.save import save_png

from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_generators import sparse_rail_generator
from flatland.envs.line_generators import sparse_line_generator
from flatland.envs.observations import GlobalObsForRailEnv
from flatland.envs.malfunction_generators import (
    MalfunctionParameters,
    ParamMalfunctionGen,
)

OUT_STEM = "od_transfer_01"
MIN_TRANSFER_TIME = 1
MIN_HORIZON = 30
HORIZON_SLACK = 12

OUT_PKL = ROOT / "envs" / "pkl" / f"{OUT_STEM}.pkl"
OUT_LP = ROOT / "envs" / "lp" / f"{OUT_STEM}.lp"
OUT_PNG = ROOT / "envs" / "png" / f"{OUT_STEM}.png"
OUT_SCENARIO = ROOT / "asp" / "scenarios" / f"{OUT_STEM}.lp"
OUT_META = ROOT / "asp" / "scenarios" / f"{OUT_STEM}.json"

ACTIVE_PROFILE = ROOT / "asp" / "profiles" / "active_profile.lp"

CONNECTION = ROOT / "asp" / "custom" / "connection.lp"
ENCODING = ROOT / "asp" / "custom" / "encoding.lp"
WAYPOINT = ROOT / "asp" / "custom" / "waypoint.lp"
PASSENGER = ROOT / "asp" / "custom" / "passenger_transfer.lp"
VISUAL = ROOT / "asp" / "custom" / "visual.lp"
OBJECTIVES = ROOT / "asp" / "custom" / "objectives.lp"

DIR_DELTA = {
    0: (-1, 0),  # north
    1: (0, 1),   # east
    2: (1, 0),   # south
    3: (0, -1),  # west
}

PROFILE_CONSTANTS = {
    "fastest": {
        "w_arrival": 15,
        "w_wait": 4,
        "w_transfer": 2,
        "w_turn": 1,
        "w_waypoint": 5,
    },
    "fewest_transfers": {
        "w_arrival": 5,
        "w_wait": 5,
        "w_transfer": 20,
        "w_turn": 1,
        "w_waypoint": 5,
    },
}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--max-seeds", type=int, default=40)
    p.add_argument("--candidates-per-seed", type=int, default=12)
    p.add_argument("--search-time-limit", type=int, default=10)
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args()


def require_files(paths):
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Required RS42 files are missing:\n" + "\n".join(missing)
        )


def outputs():
    return [OUT_PKL, OUT_LP, OUT_PNG, OUT_SCENARIO, OUT_META]


def ensure_output_policy(overwrite):
    existing = [p for p in outputs() if p.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "od_transfer_01 already exists. Use --overwrite to rebuild it:\n"
            + "\n".join(str(p) for p in existing)
        )


def cleanup_outputs():
    for p in outputs():
        if p.exists():
            p.unlink()


def profile_text(mode):
    lines = [f"objective_mode({mode}).", ""]
    for name, value in PROFILE_CONSTANTS[mode].items():
        lines.append(f"#const {name} = {value}.")
    return "\n".join(lines) + "\n"


def make_env(seed):
    random.seed(seed)
    np.random.seed(seed)

    rail_kwargs = dict(
        max_num_cities=3,
        grid_mode=False,
        max_rails_between_cities=2,
        max_rail_pairs_in_city=2,
    )

    # Some Flatland versions accept seed in the rail generator; some do not.
    try:
        sig = inspect.signature(sparse_rail_generator)
        if "seed" in sig.parameters:
            rail_kwargs["seed"] = seed
    except Exception:
        pass

    rail_generator = sparse_rail_generator(**rail_kwargs)
    line_generator = sparse_line_generator({1: 1})

    malfunction = MalfunctionParameters(
        malfunction_rate=0.0,
        min_duration=0,
        max_duration=0,
    )

    env_kwargs = dict(
        width=25,
        height=25,
        rail_generator=rail_generator,
        line_generator=line_generator,
        number_of_agents=3,
        obs_builder_object=GlobalObsForRailEnv(),
        malfunction_generator=ParamMalfunctionGen(malfunction),
        remove_agents_at_target=True,
    )

    try:
        env_sig = inspect.signature(RailEnv)
        if "random_seed" in env_sig.parameters:
            env_kwargs["random_seed"] = seed
    except Exception:
        pass

    env = RailEnv(**env_kwargs)

    try:
        reset_sig = inspect.signature(env.reset)
        if "random_seed" in reset_sig.parameters:
            env.reset(random_seed=seed)
        else:
            env.reset()
    except Exception:
        env.reset()

    return env


def shortest_path(env, agent):
    """
    BFS over Flatland states (row, col, direction).
    Returns one shortest coordinate path from initial position to target.
    """
    start_pos = tuple(agent.initial_position)
    start_dir = int(agent.initial_direction)
    target = tuple(agent.target)

    start = (start_pos[0], start_pos[1], start_dir)
    q = deque([start])
    parent = {start: None}

    goal = None

    while q:
        row, col, direction = q.popleft()

        if (row, col) == target:
            goal = (row, col, direction)
            break

        transitions = env.rail.get_transitions(row, col, direction)

        for next_dir in range(4):
            if not transitions[next_dir]:
                continue

            dr, dc = DIR_DELTA[next_dir]
            nr, nc = row + dr, col + dc

            if nr < 0 or nc < 0 or nr >= env.height or nc >= env.width:
                continue

            nxt = (nr, nc, next_dir)
            if nxt in parent:
                continue

            parent[nxt] = (row, col, direction)
            q.append(nxt)

    if goal is None:
        return None

    states = []
    cur = goal
    while cur is not None:
        states.append(cur)
        cur = parent[cur]
    states.reverse()

    return [(r, c) for r, c, _ in states]


def indexed_path(path):
    """
    Use first occurrence only. Shortest paths normally do not loop, but this
    keeps candidate ordering deterministic.
    """
    result = {}
    for i, cell in enumerate(path):
        if cell not in result:
            result[cell] = i
    return result


def build_geometric_candidates(paths):
    """
    Find direct-vs-transfer station triples.

    Candidate timing lower bound:
        transfer = first_leg + MIN_TRANSFER_TIME + second_leg

    Store path indices so v4 can synchronize train release times.
    """
    candidates = []

    for direct_train, first_train, second_train in itertools.permutations(range(3), 3):
        pd = indexed_path(paths[direct_train])
        p1 = indexed_path(paths[first_train])
        p2 = indexed_path(paths[second_train])

        origins = set(pd) & set(p1)
        hubs = set(p1) & set(p2)
        destinations = set(pd) & set(p2)

        for origin in origins:
            for hub in hubs:
                if p1[origin] >= p1[hub]:
                    continue

                for destination in destinations:
                    if pd[origin] >= pd[destination]:
                        continue
                    if p2[hub] >= p2[destination]:
                        continue
                    if len({origin, hub, destination}) != 3:
                        continue

                    direct_steps = pd[destination] - pd[origin]
                    first_steps = p1[hub] - p1[origin]
                    second_steps = p2[destination] - p2[hub]

                    transfer_lower_bound = (
                        first_steps + MIN_TRANSFER_TIME + second_steps
                    )
                    margin = direct_steps - transfer_lower_bound

                    if margin < 1:
                        continue

                    candidates.append(
                        {
                            "direct_train": direct_train,
                            "first_train": first_train,
                            "second_train": second_train,
                            "origin": origin,
                            "hub": hub,
                            "destination": destination,
                            "direct_steps": direct_steps,
                            "first_steps": first_steps,
                            "second_steps": second_steps,
                            "transfer_lower_bound": transfer_lower_bound,
                            "geometric_margin": margin,
                            "direct_origin_index": pd[origin],
                            "direct_destination_index": pd[destination],
                            "first_origin_index": p1[origin],
                            "first_hub_index": p1[hub],
                            "second_hub_index": p2[hub],
                            "second_destination_index": p2[destination],
                        }
                    )

    candidates.sort(
        key=lambda x: (x["geometric_margin"], x["direct_steps"]),
        reverse=True,
    )

    seen = set()
    unique = []
    for c in candidates:
        key = (
            c["direct_train"],
            c["first_train"],
            c["second_train"],
            c["origin"],
            c["hub"],
            c["destination"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)

    return unique


def _set_agent_time(agent, field, value):
    try:
        setattr(agent, field, int(value))
    except Exception as exc:
        raise RuntimeError(
            f"Could not set EnvAgent.{field}={value}: {exc}"
        )


def tune_candidate_timetable(base_env, candidate, paths):
    """Synchronize the transfer and derive a tight candidate horizon."""
    env = copy.deepcopy(base_env)

    direct_id = candidate["direct_train"]
    first_id = candidate["first_train"]
    second_id = candidate["second_train"]

    first_hub_i = candidate["first_hub_index"]
    second_hub_i = candidate["second_hub_index"]

    first_release = max(
        0,
        second_hub_i - first_hub_i - MIN_TRANSFER_TIME,
    )
    second_release = (
        first_release
        + first_hub_i
        - second_hub_i
        + MIN_TRANSFER_TIME
    )
    direct_release = first_release + 2

    releases = {
        direct_id: direct_release,
        first_id: first_release,
        second_id: second_release,
    }

    for agent_id, release in releases.items():
        _set_agent_time(
            env.agents[agent_id],
            "earliest_departure",
            release,
        )

    nominal_target_times = []
    for agent_id, path in enumerate(paths):
        release = releases.get(
            agent_id,
            int(env.agents[agent_id].earliest_departure),
        )
        nominal_target_times.append(
            release + 2 + max(0, len(path) - 1)
        )

    horizon = max(
        MIN_HORIZON,
        max(nominal_target_times) + HORIZON_SLACK,
    )
    env._max_episode_steps = int(horizon)

    for agent in env.agents:
        try:
            _set_agent_time(agent, "latest_arrival", horizon)
        except RuntimeError:
            pass

    first_hub_time = first_release + 2 + first_hub_i
    second_hub_time = second_release + 2 + second_hub_i
    if second_hub_time - first_hub_time != MIN_TRANSFER_TIME:
        raise AssertionError("Transfer synchronization failed.")

    timing = {
        "direct_release": direct_release,
        "first_release": first_release,
        "second_release": second_release,
        "expected_first_hub_time": first_hub_time,
        "expected_second_hub_time": second_hub_time,
        "expected_transfer_wait": MIN_TRANSFER_TIME,
        "planning_horizon": int(horizon),
        "nominal_latest_target_time": int(max(nominal_target_times)),
    }
    return env, timing


def scenario_text(c):
    d = c["direct_train"]
    a = c["first_train"]
    b = c["second_train"]

    orow, ocol = c["origin"]
    hrow, hcol = c["hub"]
    drow, dcol = c["destination"]

    return f"""% ============================================================
% RS42 controlled passenger OD benchmark: {OUT_STEM}
%
% Direct service:
%   train {d}: origin -> destination
%
% Faster transfer candidate:
%   train {a}: origin -> hub
%   train {b}: hub -> destination
%
% Passenger itinerary is selected by ASP.
% ============================================================

flatland_waypoint({d}, wp_direct_origin, {orow}, {ocol}).
flatland_waypoint({d}, wp_direct_destination, {drow}, {dcol}).
station(origin, {d}, wp_direct_origin).
station(destination, {d}, wp_direct_destination).
must_visit({d}, origin).
must_visit({d}, destination).
station_order({d}, origin, destination).

flatland_waypoint({a}, wp_first_origin, {orow}, {ocol}).
flatland_waypoint({a}, wp_first_hub, {hrow}, {hcol}).
station(origin, {a}, wp_first_origin).
station(hub, {a}, wp_first_hub).
must_visit({a}, origin).
must_visit({a}, hub).
station_order({a}, origin, hub).

flatland_waypoint({b}, wp_second_hub, {hrow}, {hcol}).
flatland_waypoint({b}, wp_second_destination, {drow}, {dcol}).
station(hub, {b}, wp_second_hub).
station(destination, {b}, wp_second_destination).
must_visit({b}, hub).
must_visit({b}, destination).
station_order({b}, hub, destination).

passenger(p1).
passenger_origin(p1, origin).
passenger_destination(p1, destination).
"""


def clingo_files(env_lp, scenario, profile):
    return [
        str(env_lp),
        str(CONNECTION),
        str(ENCODING),
        str(WAYPOINT),
        str(PASSENGER),
        str(VISUAL),
        str(OBJECTIVES),
        str(profile),
        str(scenario),
    ]


def _parse_clingo_json(result):
    if not result.stdout.strip():
        return {
            "ok": False,
            "status": "NO_OUTPUT",
            "atoms": set(),
        }

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "status": "BAD_JSON",
            "atoms": set(),
        }

    status = str(data.get("Result", "UNKNOWN")).upper()
    calls = data.get("Call", [])
    witnesses = calls[-1].get("Witnesses", []) if calls else []
    atoms = set(witnesses[-1].get("Value", [])) if witnesses else set()

    return {
        "ok": bool(witnesses),
        "status": status,
        "atoms": atoms,
    }


def run_clingo_json(
    env_lp,
    scenario,
    mode,
    tmpdir,
    time_limit,
    optimize=True,
):
    profile = tmpdir / f"profile_{mode}.lp"
    profile.write_text(profile_text(mode), encoding="utf-8")

    optimization_args = (
        ["--opt-mode=opt"]
        if optimize
        else ["--opt-mode=ignore", "--models=1"]
    )

    result = subprocess.run(
        [sys.executable, "-m", "clingo"]
        + clingo_files(env_lp, scenario, profile)
        + [
            "--outf=2",
            f"--time-limit={int(time_limit)}",
        ]
        + optimization_args,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    return _parse_clingo_json(result)


def sat_check(env_lp, scenario, tmpdir, time_limit):
    result = run_clingo_json(
        env_lp,
        scenario,
        "fastest",
        tmpdir,
        time_limit,
        optimize=False,
    )

    if result["ok"]:
        return True, f"SAT ({result['status']})"

    if "UNSAT" in result["status"]:
        return False, "UNSAT"

    return False, f"NO MODEL ({result['status']})"


def atom_value(atoms, predicate):
    pattern = re.compile(
        rf"^{re.escape(predicate)}\(p1,(-?\d+)\)$"
    )
    for atom in atoms:
        m = pattern.match(atom)
        if m:
            return int(m.group(1))
    return None


def verify_candidate(env_lp, scenario, tmpdir, time_limit):
    fastest = run_clingo_json(
        env_lp,
        scenario,
        "fastest",
        tmpdir,
        time_limit,
        optimize=True,
    )

    if fastest["status"] != "OPTIMUM FOUND":
        suffix = "model found" if fastest["ok"] else "no model"
        return (
            None,
            f"fastest optimization {fastest['status']} ({suffix})",
        )

    ft = atom_value(fastest["atoms"], "transfer_count")
    fj = atom_value(
        fastest["atoms"],
        "passenger_journey_time",
    )
    if ft != 1 or fj is None:
        return (
            None,
            f"fastest optimum: transfers={ft}, journey={fj}",
        )

    fewest = run_clingo_json(
        env_lp,
        scenario,
        "fewest_transfers",
        tmpdir,
        time_limit,
        optimize=True,
    )

    if fewest["status"] != "OPTIMUM FOUND":
        suffix = "model found" if fewest["ok"] else "no model"
        return (
            None,
            f"fewest optimization {fewest['status']} ({suffix})",
        )

    zt = atom_value(fewest["atoms"], "transfer_count")
    zj = atom_value(
        fewest["atoms"],
        "passenger_journey_time",
    )
    if zt != 0 or zj is None:
        return (
            None,
            f"fewest optimum: transfers={zt}, journey={zj}",
        )

    if fj >= zj:
        return (
            None,
            f"no speed tradeoff: fastest={fj}, direct={zj}",
        )

    return {
        "fastest_transfer_count": ft,
        "fastest_journey_time": fj,
        "fewest_transfer_count": zt,
        "fewest_journey_time": zj,
    }, "VERIFIED"


def save_environment(env):
    OUT_PKL.parent.mkdir(parents=True, exist_ok=True)
    OUT_LP.parent.mkdir(parents=True, exist_ok=True)
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    OUT_SCENARIO.parent.mkdir(parents=True, exist_ok=True)

    with OUT_PKL.open("wb") as f:
        pickle.dump(env, f)

    OUT_LP.write_text(
        convert_to_clingo(env),
        encoding="utf-8",
    )

    try:
        prefix = str(ROOT / "envs") + os.sep
        save_png(env, OUT_STEM, prefix)
    except Exception as exc:
        print(f"WARNING: PNG rendering skipped: {exc}")


def write_active_profile(mode):
    ACTIVE_PROFILE.write_text(
        profile_text(mode),
        encoding="utf-8",
    )


def run_flatland(mode, expected_transfers):
    write_active_profile(mode)

    result = subprocess.run(
        [
            sys.executable,
            "solve.py",
            str(OUT_PKL),
            "--no-render",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=240,
    )

    text = result.stdout + result.stderr

    if result.returncode != 0:
        raise RuntimeError(
            f"{mode}: solve.py failed.\n{text[-9000:]}"
        )

    if "RS42_VALIDATION: PASS" not in text:
        raise RuntimeError(
            f"{mode}: Flatland validation failed.\n{text[-9000:]}"
        )

    expected = f"transfer_count(p1,{expected_transfers})"
    if expected not in text:
        raise RuntimeError(
            f"{mode}: expected {expected} in solver output.\n{text[-9000:]}"
        )

    journey_times = [
        int(x)
        for x in re.findall(
            r"passenger_journey_time\(p1,(-?\d+)\)",
            text,
        )
    ]

    return {
        "mode": mode,
        "transfer_count": expected_transfers,
        "journey_time": journey_times[-1] if journey_times else None,
        "validation": "PASS",
    }


def main():
    args = parse_args()

    require_files(
        [
            ACTIVE_PROFILE,
            CONNECTION,
            ENCODING,
            WAYPOINT,
            PASSENGER,
            VISUAL,
            OBJECTIVES,
        ]
    )
    ensure_output_policy(args.overwrite)

    original_profile = ACTIVE_PROFILE.read_text(encoding="utf-8")
    found = None
    found_env = None
    found_scenario = None

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            temp_env_lp = tmpdir / "candidate_env.lp"
            temp_scenario = tmpdir / "candidate_scenario.lp"
            empty_scenario = tmpdir / "empty_scenario.lp"
            empty_scenario.write_text(
                "% baseline without station/passenger constraints\n",
                encoding="utf-8",
            )

            for seed in range(1, args.max_seeds + 1):
                print(f"\n=== Seed {seed}/{args.max_seeds} ===")

                try:
                    env = make_env(seed)
                except Exception as exc:
                    print(f"Environment generation skipped: {exc}")
                    continue

                paths = []
                valid = True
                for agent_id, agent in enumerate(env.agents):
                    p = shortest_path(env, agent)
                    if not p:
                        print(f"Agent {agent_id}: no path found.")
                        valid = False
                        break
                    paths.append(p)

                if not valid or len(paths) != 3:
                    continue

                candidates = build_geometric_candidates(paths)
                print(
                    f"Found {len(candidates)} geometric OD candidates."
                )

                if not candidates:
                    continue

                for idx, candidate in enumerate(
                    candidates[: args.candidates_per_seed],
                    start=1,
                ):
                    candidate_env, timing = tune_candidate_timetable(
                        env,
                        candidate,
                        paths,
                    )

                    temp_env_lp.write_text(
                        convert_to_clingo(candidate_env),
                        encoding="utf-8",
                    )

                    scenario = scenario_text(candidate)
                    temp_scenario.write_text(
                        scenario,
                        encoding="utf-8",
                    )

                    baseline_ok, baseline_reason = sat_check(
                        temp_env_lp,
                        empty_scenario,
                        tmpdir,
                        min(8, args.search_time_limit),
                    )
                    if not baseline_ok:
                        print(
                            f"  Candidate {idx}: "
                            f"direct={candidate['direct_train']} "
                            f"first={candidate['first_train']} "
                            f"second={candidate['second_train']} "
                            f"origin={candidate['origin']} "
                            f"hub={candidate['hub']} "
                            f"destination={candidate['destination']} "
                            f"horizon={timing['planning_horizon']} "
                            f"-> base train schedule {baseline_reason}"
                        )
                        continue

                    scenario_ok, scenario_reason = sat_check(
                        temp_env_lp,
                        temp_scenario,
                        tmpdir,
                        min(8, args.search_time_limit),
                    )
                    if not scenario_ok:
                        print(
                            f"  Candidate {idx}: "
                            f"direct={candidate['direct_train']} "
                            f"first={candidate['first_train']} "
                            f"second={candidate['second_train']} "
                            f"origin={candidate['origin']} "
                            f"hub={candidate['hub']} "
                            f"destination={candidate['destination']} "
                            f"horizon={timing['planning_horizon']} "
                            f"-> station/OD constraints {scenario_reason}"
                        )
                        continue

                    verified, reason = verify_candidate(
                        temp_env_lp,
                        temp_scenario,
                        tmpdir,
                        args.search_time_limit,
                    )

                    print(
                        f"  Candidate {idx}: "
                        f"direct={candidate['direct_train']} "
                        f"first={candidate['first_train']} "
                        f"second={candidate['second_train']} "
                        f"origin={candidate['origin']} "
                        f"hub={candidate['hub']} "
                        f"destination={candidate['destination']} "
                        f"margin={candidate['geometric_margin']} "
                        f"horizon={timing['planning_horizon']} "
                        f"releases="
                        f"({timing['direct_release']},"
                        f"{timing['first_release']},"
                        f"{timing['second_release']}) "
                        f"-> {reason}"
                    )

                    if verified is None:
                        continue

                    found = {
                        "seed": seed,
                        **candidate,
                        **timing,
                        **verified,
                    }
                    found_env = candidate_env
                    found_scenario = scenario
                    break

                if found is not None:
                    break

        if found is None:
            raise RuntimeError(
                "No verified timed trade-off found within the search budget. "
                "The output separates base schedulability, station/OD "
                "satisfiability, and optimization failures. "
                "No benchmark files were written."
            )

        print("\nVerified candidate found:")
        printable = dict(found)
        for key in ("origin", "hub", "destination"):
            printable[key] = list(printable[key])
        print(json.dumps(printable, indent=2))

        if args.overwrite:
            cleanup_outputs()

        save_environment(found_env)
        OUT_SCENARIO.write_text(
            found_scenario,
            encoding="utf-8",
        )

        meta = dict(printable)
        meta.update(
            {
                "benchmark": OUT_STEM,
                "purpose": (
                    "Controlled OD benchmark: faster one-transfer "
                    "journey versus slower direct journey"
                ),
            }
        )

        print("\nRunning full Flatland validation: Fastest...")
        fastest_result = run_flatland(
            "fastest",
            expected_transfers=1,
        )
        print("  PASS")

        print("Running full Flatland validation: Fewer Transfers...")
        fewest_result = run_flatland(
            "fewest_transfers",
            expected_transfers=0,
        )
        print("  PASS")

        if (
            fastest_result["journey_time"] is not None
            and fewest_result["journey_time"] is not None
            and fastest_result["journey_time"]
            >= fewest_result["journey_time"]
        ):
            raise RuntimeError(
                "Full Flatland validation passed, but final journey-time "
                "ordering no longer demonstrates the intended trade-off."
            )

        meta["flatland_validation"] = {
            "fastest": fastest_result,
            "fewest_transfers": fewest_result,
        }

        OUT_META.write_text(
            json.dumps(meta, indent=2) + "\n",
            encoding="utf-8",
        )

    except Exception:
        cleanup_outputs()
        raise

    finally:
        ACTIVE_PROFILE.write_text(
            original_profile,
            encoding="utf-8",
        )

    print("\nSUCCESS: od_transfer_01 created and verified.")
    print(f"  {OUT_PKL.relative_to(ROOT)}")
    print(f"  {OUT_LP.relative_to(ROOT)}")
    if OUT_PNG.exists():
        print(f"  {OUT_PNG.relative_to(ROOT)}")
    print(f"  {OUT_SCENARIO.relative_to(ROOT)}")
    print(f"  {OUT_META.relative_to(ROOT)}")

    print("\nVerified preference split:")
    print(
        "  Fastest          -> "
        f"{meta['flatland_validation']['fastest']['journey_time']} "
        "journey time, 1 transfer"
    )
    print(
        "  Fewer Transfers  -> "
        f"{meta['flatland_validation']['fewest_transfers']['journey_time']} "
        "journey time, 0 transfers"
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
