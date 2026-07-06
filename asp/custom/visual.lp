% ============================================================
% visual.lp
% Preference optimization with waypoint/intermediate-stop support
% ============================================================



% -----------------------------
% Arrival time
% -----------------------------

arrival(ID,T) :-
    reached(ID,T),
    not reached(ID,T-1),
    T > 0.

arrival(ID,0) :-
    reached(ID,0).

% -----------------------------
% Waiting time
% -----------------------------

waiting_time(ID,N) :-
    train(ID),
    N = #count {
        T : action(train(ID), wait, T),
            not reached(ID,T)
    }.

% -----------------------------
% Turns / route complexity
% temporary proxy for transfers
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
% Waypoint visit time
% Requires waypoint.lp:
% waypoint(ID, WP, X, Y).
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
% Costs
% -----------------------------

cost(ID,arrival,C) :-
    arrival(ID,T),
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

#minimize { C,ID,Type : cost(ID,Type,C) }.

#show action/3.