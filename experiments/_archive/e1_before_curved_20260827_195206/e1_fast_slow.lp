% ============================================================
% RS42 Final Evaluation E1 - Fast vs Slow Route
%
% The symbolic origin/destination each have two physical platforms.
%
% Train 0: short/fast O -> D service
% Train 1: long/slow O -> D service
%
% Passenger itinerary is selected by ASP.
% ============================================================

flatland_waypoint(
    0,
    wp_fast_origin,
    3,
    1
).
flatland_waypoint(
    0,
    wp_fast_destination,
    3,
    11
).
station(origin, 0, wp_fast_origin).
station(destination, 0, wp_fast_destination).
must_visit(0, origin).
must_visit(0, destination).
station_order(0, origin, destination).

flatland_waypoint(
    1,
    wp_slow_origin,
    8,
    1
).
flatland_waypoint(
    1,
    wp_slow_destination,
    8,
    19
).
station(origin, 1, wp_slow_origin).
station(destination, 1, wp_slow_destination).
must_visit(1, origin).
must_visit(1, destination).
station_order(1, origin, destination).

passenger(p1).
passenger_origin(p1, origin).
passenger_destination(p1, destination).
