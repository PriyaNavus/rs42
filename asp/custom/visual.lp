% ============================================================
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
