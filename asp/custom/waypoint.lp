% ============================================================
% waypoints.lp
% Station-based waypoint constraints
% ============================================================





% Scenario-specific facts are loaded from asp/scenarios/*.lp

required_waypoint(ID, WP) :-
    must_visit(ID, Station),
    station(Station, ID, WP).

waypoint(ID, WP, X, Y) :-
    required_waypoint(ID, WP),
    flatland_waypoint(ID, WP, X, Y).

visited_station(ID, Station) :-
    station(Station, ID, WP),
    waypoint(ID, WP, X, Y),
    pos(ID, X, Y, _, T).

visited_station_at(ID, Station, T) :-
    station(Station, ID, WP),
    waypoint(ID, WP, X, Y),
    pos(ID, X, Y, _, T).

first_station_visit(ID, Station, T) :-
    visited_station_at(ID, Station, T),
    not earlier_station_visit(ID, Station, T).

earlier_station_visit(ID, Station, T) :-
    visited_station_at(ID, Station, T),
    visited_station_at(ID, Station, T1),
    T1 < T.

:- must_visit(ID, Station),
   not visited_station(ID, Station).

:- station_order(ID, S1, S2),
   first_station_visit(ID, S1, T1),
   first_station_visit(ID, S2, T2),
   T1 >= T2.

#show visited_station/2.
#show first_station_visit/3.
