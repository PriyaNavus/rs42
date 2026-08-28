% ============================================================
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
