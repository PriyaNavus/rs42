from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path.cwd()

PASSENGER = ROOT / "asp" / "custom" / "passenger_transfer.lp"
VISUAL = ROOT / "asp" / "custom" / "visual.lp"
OBJECTIVES = ROOT / "asp" / "custom" / "objectives.lp"

PROFILE_DIR = ROOT / "asp" / "profiles"
ACTIVE_PROFILE = PROFILE_DIR / "active_profile.lp"

ENV_LP = ROOT / "envs" / "lp" / "env_001--2_4.lp"
ENV_PKL = ROOT / "envs" / "pkl" / "env_001--2_4.pkl"
SCENARIO = ROOT / "asp" / "scenarios" / "env_001--2_4.lp"

CONNECTION = ROOT / "asp" / "custom" / "connection.lp"
ENCODING = ROOT / "asp" / "custom" / "encoding.lp"
WAYPOINT = ROOT / "asp" / "custom" / "waypoint.lp"

MARKER = "RS42_PASSENGER_OD_V1"


PASSENGER_TEXT = r"""% ============================================================
% passenger_transfer.lp
% RS42 passenger journey and transfer model
%
% Supports two modes:
%
% 1. Legacy fixed-itinerary passengers
%    passenger/1 + uses_train/3 + transfer_station/1
%    Kept for backwards compatibility with existing scenarios.
%
% 2. OD passengers
%    passenger/1 + passenger_origin/2 + passenger_destination/2
%    The solver chooses a feasible train itinerary.
% ============================================================

#const max_passenger_legs = 3.
#const min_transfer_time = 1.

% ------------------------------------------------------------
% Common station-service relation
% ------------------------------------------------------------

serves_station(Train, Station) :-
    visited_station(Train, Station).

% ============================================================
% LEGACY MODE
% ============================================================

od_passenger(P) :-
    passenger(P),
    passenger_origin(P,_),
    passenger_destination(P,_).

legacy_passenger(P) :-
    passenger(P),
    not od_passenger(P).

% Legacy transfer semantics are preserved exactly so existing
% scenarios remain regression-compatible.
valid_transfer(P, Station, Train1, Train2) :-
    legacy_passenger(P),
    transfer_station(Station),
    uses_train(P, Train1, Order1),
    uses_train(P, Train2, Order2),
    Train1 != Train2,
    Order1 < Order2,
    serves_station(Train1, Station),
    serves_station(Train2, Station).

legacy_transfer(P, Station) :-
    valid_transfer(P, Station, _, _).

transfer_count(P, N) :-
    legacy_passenger(P),
    N = #count {
        Station : legacy_transfer(P, Station)
    }.

% ============================================================
% OD MODE: SOLVER-SELECTED PASSENGER ITINERARY
% ============================================================

journey_leg(1..max_passenger_legs).

% A passenger may ride a train from FromStation to ToStation
% only when that train actually visits FromStation first and
% ToStation later in the generated railway schedule.
ride_option(Train, FromStation, ToStation, Depart, Arrive) :-
    first_station_visit(Train, FromStation, Depart),
    first_station_visit(Train, ToStation, Arrive),
    FromStation != ToStation,
    Depart < Arrive.

% Select the number of train legs in the passenger journey.
1 {
    journey_length(P,L) : journey_leg(L)
} 1 :-
    od_passenger(P).

% For every active leg choose exactly one feasible train ride.
1 {
    chosen_leg(P,I,Train,FromStation,ToStation,Depart,Arrive) :
        ride_option(Train,FromStation,ToStation,Depart,Arrive)
} 1 :-
    od_passenger(P),
    journey_length(P,L),
    journey_leg(I),
    I <= L.

% First selected ride must start at the passenger origin.
:- passenger_origin(P,Origin),
   chosen_leg(P,1,_,FromStation,_,_,_),
   FromStation != Origin.

% Last selected ride must terminate at the passenger destination.
:- passenger_destination(P,Destination),
   journey_length(P,L),
   chosen_leg(P,L,_,_,ToStation,_,_),
   ToStation != Destination.

% Consecutive legs must connect at the same station.
:- chosen_leg(P,I,_,_,TransferStation,_,_),
   chosen_leg(P,J,_,NextStation,_,_,_),
   J = I + 1,
   TransferStation != NextStation.

% A transfer must be temporally feasible.
:- chosen_leg(P,I,_,_,TransferStation,_,Arrive),
   chosen_leg(P,J,_,TransferStation,_,Depart,_),
   J = I + 1,
   Depart < Arrive + min_transfer_time.

% Consecutive legs on the same train are redundant: they can be
% represented as one longer ride on that train.
:- chosen_leg(P,I,Train,_,_,_,_),
   chosen_leg(P,J,Train,_,_,_,_),
   J = I + 1.

chosen_transfer(P,I,Station,FromTrain,ToTrain,Arrive,Depart) :-
    chosen_leg(P,I,FromTrain,_,Station,_,Arrive),
    chosen_leg(P,J,ToTrain,Station,_,Depart,_),
    J = I + 1.

transfer_count(P,N) :-
    od_passenger(P),
    N = #count {
        I,Station,FromTrain,ToTrain,Arrive,Depart :
            chosen_transfer(
                P,I,Station,FromTrain,ToTrain,Arrive,Depart
            )
    }.

% Passenger journey duration:
% final arrival minus first boarding/departure time.
passenger_journey_time(P,Duration) :-
    od_passenger(P),
    journey_length(P,L),
    chosen_leg(P,1,_,_,_,Depart,_),
    chosen_leg(P,L,_,_,_,_,Arrive),
    Duration = Arrive - Depart.

% Waiting caused specifically by changing trains.
transfer_wait(P,I,Wait) :-
    chosen_transfer(P,I,_,_,_,Arrive,Depart),
    Wait = Depart - Arrive.

passenger_transfer_wait(P,Total) :-
    od_passenger(P),
    Total = #sum {
        Wait,I : transfer_wait(P,I,Wait)
    }.

% Trains used by a selected passenger journey.
passenger_uses_train(P,Train) :-
    chosen_leg(P,_,Train,_,_,_,_).

#show valid_transfer/4.
#show chosen_leg/7.
#show chosen_transfer/7.
#show journey_length/2.
#show passenger_journey_time/2.
#show passenger_transfer_wait/2.
#show transfer_count/2.
"""


VISUAL_TEXT = r"""% ============================================================
% visual.lp
% RS42 raw metrics + optimization-facing metrics
%
% Raw train metrics remain available for scenarios without an
% origin/destination passenger model.
%
% When OD passengers exist, journey/wait/simple metrics are
% evaluated from the passenger-selected itinerary where possible.
% ============================================================

% ------------------------------------------------------------
% Absolute train arrival time
% ------------------------------------------------------------

arrival(ID,T) :-
    reached(ID,T),
    not reached(ID,T-1),
    T > 0.

arrival(ID,0) :-
    reached(ID,0).

% ------------------------------------------------------------
% Train journey duration
% ------------------------------------------------------------
% Current Flatland spawning places the train on its start cell at
% release_time + 2. Remove that fixed simulator overhead.

travel_time(ID,D) :-
    arrival(ID,A),
    start(ID,_,Release,_),
    D = A - Release - 2.

% ------------------------------------------------------------
% In-journey train waiting
% ------------------------------------------------------------

waiting_time(ID,N) :-
    train(ID),
    N = #count {
        T : action(train(ID), wait, T),
            pos(ID,_,_,_,T),
            not reached(ID,T)
    }.

% ------------------------------------------------------------
% Route complexity
% ------------------------------------------------------------

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

% ------------------------------------------------------------
% Intermediate waypoint timing
% ------------------------------------------------------------

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

% ============================================================
% OPTIMIZATION-FACING METRICS
% ============================================================

has_od_passenger :-
    od_passenger(_).

% Fastest:
% - with OD passengers: passenger journey duration
% - otherwise: train journey duration (legacy behaviour)
journey_metric(passenger(P),T) :-
    od_passenger(P),
    passenger_journey_time(P,T).

journey_metric(train(ID),T) :-
    travel_time(ID,T),
    not has_od_passenger.

% Least waiting:
% - with OD passengers: waiting between selected train legs
% - otherwise: train operational in-journey waiting
waiting_metric(passenger(P),T) :-
    od_passenger(P),
    passenger_transfer_wait(P,T).

waiting_metric(train(ID),T) :-
    waiting_time(ID,T),
    not has_od_passenger.

% Simple journey:
% for an OD passenger, count the route turns of the trains that the
% passenger actually uses. This remains a route-simplicity proxy.
passenger_turns(P,Total) :-
    od_passenger(P),
    Total = #sum {
        N,Train :
            passenger_uses_train(P,Train),
            turns(Train,N)
    }.

turn_metric(passenger(P),T) :-
    od_passenger(P),
    passenger_turns(P,T).

turn_metric(train(ID),T) :-
    turns(ID,T),
    not has_od_passenger.

% Waypoint timing remains an operational railway metric.
waypoint_metric(train(ID),T) :-
    waypoint_time(ID,T).

% ============================================================
% WEIGHTED COSTS
% Balanced / Custom only
% ============================================================

cost(Entity,journey,C) :-
    journey_metric(Entity,T),
    C = T * w_arrival.

cost(Entity,waiting,C) :-
    waiting_metric(Entity,T),
    C = T * w_wait.

cost(Entity,turns,C) :-
    turn_metric(Entity,T),
    C = T * w_turn.

cost(Entity,waypoint,C) :-
    waypoint_metric(Entity,T),
    C = T * w_waypoint.

cost(P,transfer,C) :-
    transfer_count(P,N),
    C = N * w_transfer.

#show action/3.
"""


OBJECTIVES_TEXT = r"""% ============================================================
% objectives.lp
% RS42 optimization policies
%
% Higher @ priorities are optimized first by clingo.
% ============================================================

known_objective_mode(weighted).
known_objective_mode(fastest).
known_objective_mode(least_waiting).
known_objective_mode(fewest_transfers).
known_objective_mode(simple).

:- not objective_mode(_).
:- objective_mode(M), not known_objective_mode(M).
:- objective_mode(M1), objective_mode(M2), M1 != M2.

% ------------------------------------------------------------
% FASTEST
% ------------------------------------------------------------

#minimize {
    T@5,Entity :
        journey_metric(Entity,T),
        objective_mode(fastest)
}.
#minimize {
    W@4,Entity :
        waiting_metric(Entity,W),
        objective_mode(fastest)
}.
#minimize {
    N@3,P :
        transfer_count(P,N),
        objective_mode(fastest)
}.
#minimize {
    N@2,Entity :
        turn_metric(Entity,N),
        objective_mode(fastest)
}.
#minimize {
    T@1,Entity :
        waypoint_metric(Entity,T),
        objective_mode(fastest)
}.

% ------------------------------------------------------------
% LEAST WAITING
% ------------------------------------------------------------

#minimize {
    W@5,Entity :
        waiting_metric(Entity,W),
        objective_mode(least_waiting)
}.
#minimize {
    T@4,Entity :
        journey_metric(Entity,T),
        objective_mode(least_waiting)
}.
#minimize {
    N@3,P :
        transfer_count(P,N),
        objective_mode(least_waiting)
}.
#minimize {
    N@2,Entity :
        turn_metric(Entity,N),
        objective_mode(least_waiting)
}.
#minimize {
    T@1,Entity :
        waypoint_metric(Entity,T),
        objective_mode(least_waiting)
}.

% ------------------------------------------------------------
% FEWEST TRANSFERS
% ------------------------------------------------------------

#minimize {
    N@5,P :
        transfer_count(P,N),
        objective_mode(fewest_transfers)
}.
#minimize {
    T@4,Entity :
        journey_metric(Entity,T),
        objective_mode(fewest_transfers)
}.
#minimize {
    W@3,Entity :
        waiting_metric(Entity,W),
        objective_mode(fewest_transfers)
}.
#minimize {
    N@2,Entity :
        turn_metric(Entity,N),
        objective_mode(fewest_transfers)
}.
#minimize {
    T@1,Entity :
        waypoint_metric(Entity,T),
        objective_mode(fewest_transfers)
}.

% ------------------------------------------------------------
% SIMPLE JOURNEY
% ------------------------------------------------------------

#minimize {
    N@5,Entity :
        turn_metric(Entity,N),
        objective_mode(simple)
}.
#minimize {
    T@4,Entity :
        journey_metric(Entity,T),
        objective_mode(simple)
}.
#minimize {
    W@3,Entity :
        waiting_metric(Entity,W),
        objective_mode(simple)
}.
#minimize {
    N@2,P :
        transfer_count(P,N),
        objective_mode(simple)
}.
#minimize {
    T@1,Entity :
        waypoint_metric(Entity,T),
        objective_mode(simple)
}.

% ------------------------------------------------------------
% WEIGHTED / BALANCED / CUSTOM
% ------------------------------------------------------------

#minimize {
    C@1,Entity,Type :
        cost(Entity,Type,C),
        objective_mode(weighted)
}.
"""


def backup(path):
    dest = path.with_suffix(path.suffix + ".passenger_od_v1.bak")
    if not dest.exists():
        shutil.copy2(path, dest)
    return dest


def restore(backups):
    for original, backup_path in backups.items():
        if backup_path.exists():
            shutil.copy2(backup_path, original)


def run_cmd(cmd, label, timeout=120):
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    combined = result.stdout + result.stderr
    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed with return code {result.returncode}.\n"
            + combined[-7000:]
        )
    return combined


def write_unit_case(path, mode):
    if mode not in {"fastest", "fewest_transfers"}:
        raise ValueError(mode)

    # Direct train 0: a -> d, duration 9, zero transfers.
    # Transfer route: train 1 a -> b, train 2 b -> d,
    # duration 6, one transfer.
    text = f"""% Synthetic OD passenger unit test
objective_mode({mode}).

#const w_arrival = 8.
#const w_wait = 8.
#const w_transfer = 8.
#const w_turn = 4.
#const w_waypoint = 6.

passenger(p).
passenger_origin(p,a).
passenger_destination(p,d).

first_station_visit(0,a,1).
first_station_visit(0,d,10).

first_station_visit(1,a,1).
first_station_visit(1,b,4).

first_station_visit(2,b,5).
first_station_visit(2,d,7).

turns(0,1).
turns(1,1).
turns(2,1).

waypoint_time(0,0).
waypoint_time(1,0).
waypoint_time(2,0).

#show chosen_leg/7.
#show passenger_journey_time/2.
#show passenger_transfer_wait/2.
#show transfer_count/2.
"""
    path.write_text(text, encoding="utf-8")


def run_unit_tests():
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        fastest_case = tmpdir / "fastest.lp"
        fewest_case = tmpdir / "fewest.lp"

        write_unit_case(fastest_case, "fastest")
        write_unit_case(fewest_case, "fewest_transfers")

        common = [
            str(PASSENGER),
            str(VISUAL),
            str(OBJECTIVES),
        ]

        fastest_output = run_cmd(
            [sys.executable, "-m", "clingo", str(fastest_case), *common],
            "Synthetic fastest-passenger test",
        )

        if "OPTIMUM FOUND" not in fastest_output:
            raise RuntimeError(
                "Fastest unit test did not report OPTIMUM FOUND.\n"
                + fastest_output[-5000:]
            )

        # Fastest should select the 2-leg route:
        # a->b (1..4), b->d (5..7), journey duration 6, 1 transfer.
        required_fastest = [
            "passenger_journey_time(p,6)",
            "transfer_count(p,1)",
        ]
        for atom in required_fastest:
            if atom not in fastest_output:
                raise RuntimeError(
                    f"Fastest unit test expected {atom}.\n"
                    + fastest_output[-5000:]
                )

        fewest_output = run_cmd(
            [sys.executable, "-m", "clingo", str(fewest_case), *common],
            "Synthetic fewest-transfers test",
        )

        if "OPTIMUM FOUND" not in fewest_output:
            raise RuntimeError(
                "Fewest-transfers unit test did not report OPTIMUM FOUND.\n"
                + fewest_output[-5000:]
            )

        # Fewest transfers should select direct train 0:
        # duration 9, zero transfers.
        required_fewest = [
            "passenger_journey_time(p,9)",
            "transfer_count(p,0)",
        ]
        for atom in required_fewest:
            if atom not in fewest_output:
                raise RuntimeError(
                    f"Fewest-transfers unit test expected {atom}.\n"
                    + fewest_output[-5000:]
                )

        return fastest_output, fewest_output


def run_existing_scenario_smoke():
    files = [
        ENV_LP,
        CONNECTION,
        ENCODING,
        WAYPOINT,
        PASSENGER,
        VISUAL,
        OBJECTIVES,
        ACTIVE_PROFILE,
        SCENARIO,
    ]

    output = run_cmd(
        [sys.executable, "-m", "clingo"]
        + [str(path) for path in files]
        + ["--time-limit=60"],
        "Existing env_001--2_4 ASP regression",
    )

    if "OPTIMUM FOUND" not in output:
        raise RuntimeError(
            "Existing scenario regression did not find an optimum.\n"
            + output[-5000:]
        )

    return output


def run_flatland_regression():
    output = run_cmd(
        [
            sys.executable,
            "solve.py",
            str(ENV_PKL),
            "--no-render",
        ],
        "Flatland regression",
        timeout=180,
    )

    if "RS42_VALIDATION: PASS" not in output:
        raise RuntimeError(
            "Flatland regression did not pass execution validation.\n"
            + output[-7000:]
        )

    return output


def main():
    required = [
        PASSENGER,
        VISUAL,
        OBJECTIVES,
        ACTIVE_PROFILE,
        ENV_LP,
        ENV_PKL,
        SCENARIO,
        CONNECTION,
        ENCODING,
        WAYPOINT,
    ]

    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(
            "Run this script from the RS42 repository root. Missing:\n"
            + "\n".join(missing)
        )

    backups = {
        PASSENGER: backup(PASSENGER),
        VISUAL: backup(VISUAL),
        OBJECTIVES: backup(OBJECTIVES),
    }

    try:
        PASSENGER.write_text(PASSENGER_TEXT, encoding="utf-8")
        VISUAL.write_text(VISUAL_TEXT, encoding="utf-8")
        OBJECTIVES.write_text(OBJECTIVES_TEXT, encoding="utf-8")

        print("Passenger OD backend written.")
        print("Running synthetic preference tests...")

        run_unit_tests()
        print("  PASS: Fastest chooses faster 1-transfer itinerary.")
        print("  PASS: Fewer Transfers chooses slower direct itinerary.")

        print("Running existing ASP regression...")
        run_existing_scenario_smoke()
        print("  PASS: existing env_001--2_4 remains optimizable.")

        print("Running Flatland execution regression...")
        run_flatland_regression()
        print("  PASS: ASP schedule still matches Flatland execution.")

    except Exception:
        print(
            "Passenger OD backend test failed. Restoring previous files...",
            file=sys.stderr,
        )
        restore(backups)
        raise

    print()
    print("RS42 passenger OD backend installed successfully.")
    print()
    print("New capability:")
    print("  passenger(P).")
    print("  passenger_origin(P, Station).")
    print("  passenger_destination(P, Station).")
    print("  -> solver selects 1..max_passenger_legs train rides")
    print("  -> transfer station/time must connect")
    print("  -> transfer count is derived from the selected journey")
    print()
    print("Verified trade-off:")
    print("  Fastest          -> faster 1-transfer journey")
    print("  Fewer Transfers  -> slower direct journey")
    print()
    print("Existing legacy uses_train/3 scenarios remain supported.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
