% ============================================================
% passenger_transfer.lp
% Transfer modelling based on actual station visits
% ============================================================

% Passenger
passenger(p1).

% Passenger itinerary order
uses_train(p1, 0, 1).
uses_train(p1, 1, 2).

% Candidate transfer station
transfer_station(s2).

% A train serves a station if it actually visits it
serves_station(Train, Station) :-
    visited_station(Train, Station).

% A transfer is valid only if:
% 1. passenger uses Train1 before Train2
% 2. Train1 and Train2 are different
% 3. both trains serve the same transfer station
valid_transfer(P, Station, Train1, Train2) :-
    passenger(P),
    transfer_station(Station),
    uses_train(P, Train1, Order1),
    uses_train(P, Train2, Order2),
    Train1 != Train2,
    Order1 < Order2,
    serves_station(Train1, Station),
    serves_station(Train2, Station).

transfer(P, Station) :-
    valid_transfer(P, Station, _, _).

transfer_count(P, N) :-
    passenger(P),
    N = #count { Station : transfer(P, Station) }.

#show valid_transfer/4.
#show transfer/2.
#show transfer_count/2.