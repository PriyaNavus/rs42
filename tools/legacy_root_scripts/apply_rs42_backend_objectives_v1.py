from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path.cwd()

VISUAL = ROOT / "asp" / "custom" / "visual.lp"
OBJECTIVES = ROOT / "asp" / "custom" / "objectives.lp"
PARAMS = ROOT / "asp" / "params.py"
PROFILES = ROOT / "asp" / "profiles"

TARGETS = [
    VISUAL,
    PARAMS,
    PROFILES / "profile_fastest.lp",
    PROFILES / "profile_least_waiting.lp",
    PROFILES / "profile_fewest_transfers.lp",
    PROFILES / "profile_comfort.lp",
    PROFILES / "profile_balanced.lp",
    PROFILES / "active_profile.lp",
]

VISUAL_TEXT = r"""% ============================================================
% visual.lp
% RS42 outcome metrics.
%
% This file DEFINES metrics only.
% Optimization policy is separated into asp/custom/objectives.lp.
% ============================================================

% -----------------------------
% Absolute arrival time
% -----------------------------

arrival(ID,T) :-
    reached(ID,T),
    not reached(ID,T-1),
    T > 0.

arrival(ID,0) :-
    reached(ID,0).

% -----------------------------
% Journey / travel duration
% -----------------------------
% Flatland's current spawn convention places a train on its start
% cell at release_time + 2.  Subtract that fixed simulator overhead
% so this metric represents the on-map journey duration.

travel_time(ID,D) :-
    arrival(ID,A),
    start(ID,_,Release,_),
    D = A - Release - 2.

% -----------------------------
% In-journey waiting
% -----------------------------
% pos(...) excludes forced waits before the train exists on the map.

waiting_time(ID,N) :-
    train(ID),
    N = #count {
        T : action(train(ID), wait, T),
            pos(ID,_,_,_,T),
            not reached(ID,T)
    }.

% -----------------------------
% Route complexity: directional turns
% -----------------------------

left_turns(ID,L) :-
    train(ID),
    L = #count { T : action(train(ID), move_left, T) }.

right_turns(ID,R) :-
    train(ID),
    R = #count { T : action(train(ID), move_right, T) }.

turns(ID,N) :-
    left_turns(ID,L),
    right_turns(ID,R),
    N = L + R.

% -----------------------------
% Intermediate waypoint timing
% -----------------------------

visited_waypoint_at(ID,WP,T) :-
    waypoint(ID,WP,X,Y),
    pos(ID,X,Y,_,T).

visited_waypoint_before(ID,WP,T) :-
    visited_waypoint_at(ID,WP,T),
    visited_waypoint_at(ID,WP,T1),
    T1 < T.

first_waypoint_visit(ID,WP,T) :-
    visited_waypoint_at(ID,WP,T),
    not visited_waypoint_before(ID,WP,T).

waypoint_time(ID,Total) :-
    train(ID),
    Total = #sum {
        T,WP : first_waypoint_visit(ID,WP,T)
    }.

waypoint_time(ID,0) :-
    train(ID),
    not waypoint(ID,_,_,_).

% -----------------------------
% Weighted costs
% Used only by weighted (Balanced / Custom) optimization.
% -----------------------------

cost(ID,travel,C) :-
    travel_time(ID,T),
    C = T * w_arrival.

cost(ID,waiting,C) :-
    waiting_time(ID,T),
    C = T * w_wait.

cost(ID,waypoint,C) :-
    waypoint_time(ID,T),
    C = T * w_waypoint.

cost(ID,turns,C) :-
    turns(ID,T),
    C = T * w_turn.

cost(P,transfer,C) :-
    transfer_count(P,N),
    C = N * w_transfer.

#show action/3.
"""

OBJECTIVES_TEXT = r"""% ============================================================
% objectives.lp
% RS42 optimization policies.
%
% Exactly one objective_mode/1 fact must be supplied by
% asp/profiles/active_profile.lp.
%
% Higher @ priorities are optimized first by clingo.
% Named profiles are lexicographic:
%   - fastest:          travel time first
%   - least_waiting:    in-journey waiting first
%   - fewest_transfers: transfer count first
%   - simple:           route turns first
%
% weighted is used for Balanced and Custom profiles.
% ============================================================

known_objective_mode(weighted).
known_objective_mode(fastest).
known_objective_mode(least_waiting).
known_objective_mode(fewest_transfers).
known_objective_mode(simple).

% Require exactly one supported mode.
:- not objective_mode(_).
:- objective_mode(M), not known_objective_mode(M).
:- objective_mode(M1), objective_mode(M2), M1 != M2.

% ------------------------------------------------------------
% FASTEST
% Primary: journey duration.
% Tie-breakers: waiting, transfers, turns, intermediate timing.
% ------------------------------------------------------------

#minimize {
    T@5,ID : travel_time(ID,T), objective_mode(fastest)
}.
#minimize {
    W@4,ID : waiting_time(ID,W), objective_mode(fastest)
}.
#minimize {
    N@3,P : transfer_count(P,N), objective_mode(fastest)
}.
#minimize {
    N@2,ID : turns(ID,N), objective_mode(fastest)
}.
#minimize {
    T@1,ID : waypoint_time(ID,T), objective_mode(fastest)
}.

% ------------------------------------------------------------
% LEAST WAITING
% Primary: in-journey waiting.
% ------------------------------------------------------------

#minimize {
    W@5,ID : waiting_time(ID,W), objective_mode(least_waiting)
}.
#minimize {
    T@4,ID : travel_time(ID,T), objective_mode(least_waiting)
}.
#minimize {
    N@3,P : transfer_count(P,N), objective_mode(least_waiting)
}.
#minimize {
    N@2,ID : turns(ID,N), objective_mode(least_waiting)
}.
#minimize {
    T@1,ID : waypoint_time(ID,T), objective_mode(least_waiting)
}.

% ------------------------------------------------------------
% FEWEST TRANSFERS
% Primary: passenger transfer count.
% ------------------------------------------------------------

#minimize {
    N@5,P : transfer_count(P,N), objective_mode(fewest_transfers)
}.
#minimize {
    T@4,ID : travel_time(ID,T), objective_mode(fewest_transfers)
}.
#minimize {
    W@3,ID : waiting_time(ID,W), objective_mode(fewest_transfers)
}.
#minimize {
    N@2,ID : turns(ID,N), objective_mode(fewest_transfers)
}.
#minimize {
    T@1,ID : waypoint_time(ID,T), objective_mode(fewest_transfers)
}.

% ------------------------------------------------------------
% SIMPLE JOURNEY
% Primary: number of directional turns.
% ------------------------------------------------------------

#minimize {
    N@5,ID : turns(ID,N), objective_mode(simple)
}.
#minimize {
    T@4,ID : travel_time(ID,T), objective_mode(simple)
}.
#minimize {
    W@3,ID : waiting_time(ID,W), objective_mode(simple)
}.
#minimize {
    N@2,P : transfer_count(P,N), objective_mode(simple)
}.
#minimize {
    T@1,ID : waypoint_time(ID,T), objective_mode(simple)
}.

% ------------------------------------------------------------
% WEIGHTED
% Balanced / Custom preserve the original weighted-sum idea.
% ------------------------------------------------------------

#minimize {
    C@1,Entity,Type :
        cost(Entity,Type,C),
        objective_mode(weighted)
}.
"""

PROFILE_TEXTS = {
    "profile_fastest.lp": r"""% Primary optimization: minimum journey duration
objective_mode(fastest).

% Retained for reporting / future weighted variants.
#const w_arrival = 15.
#const w_wait = 4.
#const w_transfer = 2.
#const w_turn = 1.
#const w_waypoint = 5.
""",
    "profile_least_waiting.lp": r"""% Primary optimization: minimum in-journey waiting
objective_mode(least_waiting).

#const w_arrival = 6.
#const w_wait = 15.
#const w_transfer = 4.
#const w_turn = 1.
#const w_waypoint = 5.
""",
    "profile_fewest_transfers.lp": r"""% Primary optimization: minimum passenger transfers
objective_mode(fewest_transfers).

#const w_arrival = 5.
#const w_wait = 5.
#const w_transfer = 20.
#const w_turn = 1.
#const w_waypoint = 5.
""",
    # Keep the historical filename for compatibility; semantics are renamed.
    "profile_comfort.lp": r"""% Primary optimization: route simplicity (fewest turns)
% Historical filename retained for compatibility with the UI/repository.
objective_mode(simple).

#const w_arrival = 5.
#const w_wait = 5.
#const w_transfer = 5.
#const w_turn = 20.
#const w_waypoint = 5.
""",
    "profile_balanced.lp": r"""% Weighted multi-objective optimization
objective_mode(weighted).

#const w_arrival = 8.
#const w_wait = 8.
#const w_transfer = 8.
#const w_turn = 4.
#const w_waypoint = 6.
""",
    "active_profile.lp": r"""% Default active policy: Balanced weighted optimization
objective_mode(weighted).

#const w_arrival = 8.
#const w_wait = 8.
#const w_transfer = 8.
#const w_turn = 4.
#const w_waypoint = 6.
""",
}


def backup(path):
    backup_path = path.with_suffix(path.suffix + ".objective_v1.bak")
    if path.exists() and not backup_path.exists():
        shutil.copy2(path, backup_path)
    return backup_path


def restore(backups):
    for original, backup_path in backups.items():
        if backup_path.exists():
            shutil.copy2(backup_path, original)


def update_params(text):
    lines = text.splitlines()

    # Idempotency.
    if any("asp/custom/objectives.lp" in line for line in lines):
        return text if text.endswith("\n") else text + "\n"

    visual_indices = [
        i for i, line in enumerate(lines)
        if "asp/custom/visual.lp" in line
    ]
    if len(visual_indices) != 1:
        raise RuntimeError(
            "asp/params.py must contain exactly one visual.lp entry."
        )

    i = visual_indices[0]
    indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
    comma = "," if lines[i].rstrip().endswith(",") else ","

    # Ensure visual line has a comma before inserting another list item.
    if not lines[i].rstrip().endswith(","):
        lines[i] = lines[i].rstrip() + ","

    lines.insert(
        i + 1,
        f'{indent}"asp/custom/objectives.lp",'
    )
    return "\n".join(lines).rstrip() + "\n"


def clingo_smoke_test():
    """
    Ground + solve the known validated scenario using the current Python.
    Run this installer from the flatlandrs42 environment so python -m clingo
    is available.
    """
    scenario = ROOT / "asp" / "scenarios" / "env_001--2_4.lp"
    env_lp = ROOT / "envs" / "lp" / "env_001--2_4.lp"

    if not scenario.exists() or not env_lp.exists():
        raise RuntimeError(
            "Expected env_001--2_4 scenario/environment files are missing."
        )

    files = [
        env_lp,
        ROOT / "asp" / "custom" / "connection.lp",
        ROOT / "asp" / "custom" / "encoding.lp",
        ROOT / "asp" / "custom" / "waypoint.lp",
        ROOT / "asp" / "custom" / "passenger_transfer.lp",
        VISUAL,
        OBJECTIVES,
        PROFILES / "active_profile.lp",
        scenario,
    ]

    cmd = (
        [sys.executable, "-m", "clingo"]
        + [str(path) for path in files]
        + ["--time-limit=60"]
    )

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    combined = result.stdout + result.stderr

    if result.returncode != 0:
        raise RuntimeError(
            "Clingo smoke test returned non-zero.\n"
            + combined[-5000:]
        )

    if "UNSATISFIABLE" in combined:
        raise RuntimeError(
            "Clingo smoke test became UNSAT after the objective refactor.\n"
            + combined[-5000:]
        )

    if "OPTIMUM FOUND" not in combined:
        raise RuntimeError(
            "Clingo did not confirm an optimum during the smoke test.\n"
            + combined[-5000:]
        )

    return combined


def main():
    required = TARGETS + [
        ROOT / "asp" / "custom" / "connection.lp",
        ROOT / "asp" / "custom" / "encoding.lp",
        ROOT / "asp" / "custom" / "waypoint.lp",
        ROOT / "asp" / "custom" / "passenger_transfer.lp",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(
            "Run this script from the rs42 repository root. Missing:\n"
            + "\n".join(missing)
        )

    # Build all new content before touching disk.
    params_text = PARAMS.read_text(encoding="utf-8")
    new_params = update_params(params_text)
    compile(new_params, str(PARAMS), "exec")

    backups = {path: backup(path) for path in TARGETS}

    try:
        VISUAL.write_text(VISUAL_TEXT, encoding="utf-8")
        OBJECTIVES.write_text(OBJECTIVES_TEXT, encoding="utf-8")
        PARAMS.write_text(new_params, encoding="utf-8")

        for filename, text in PROFILE_TEXTS.items():
            (PROFILES / filename).write_text(text, encoding="utf-8")

        print("Files written. Running Clingo smoke test...")
        smoke_output = clingo_smoke_test()

    except Exception:
        print("Backend check failed. Restoring original files...", file=sys.stderr)
        restore(backups)
        if OBJECTIVES.exists():
            OBJECTIVES.unlink()
        raise

    print()
    print("RS42 backend objective refactor installed successfully.")
    print("Clingo smoke test: PASS / OPTIMUM FOUND")
    print()
    print("New semantics:")
    print("  Fastest          -> travel time is primary")
    print("  Less waiting     -> waiting is primary")
    print("  Fewer transfers  -> transfers are primary")
    print("  Simple journey   -> route turns are primary")
    print("  Balanced/Custom  -> weighted multi-objective")
    print()
    print("Next backend regression test:")
    print(r"  python solve.py envs\pkl\env_001--2_4.pkl --no-render")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
