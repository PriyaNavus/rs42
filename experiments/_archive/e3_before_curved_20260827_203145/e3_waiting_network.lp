% RS42 Final Evaluation E3 - Waiting Network
%
% Route A: Origin -> B -> Destination
%          shorter movement, deliberately long transfer wait.
%
% Route B: Origin -> C -> Destination
%          longer movement, nearly immediate transfer.
%
% Both alternatives use exactly one transfer.

% ---------- Route A leg 1 ----------
flatland_waypoint(0,wp_a1_origin,2,1).
flatland_waypoint(0,wp_a1_b,2,4).
station(origin,0,wp_a1_origin).
station(station_b,0,wp_a1_b).
must_visit(0,origin).
must_visit(0,station_b).
station_order(0,origin,station_b).

% ---------- Route A leg 2 ----------
flatland_waypoint(1,wp_a2_b,5,1).
flatland_waypoint(1,wp_a2_destination,5,4).
station(station_b,1,wp_a2_b).
station(destination,1,wp_a2_destination).
must_visit(1,station_b).
must_visit(1,destination).
station_order(1,station_b,destination).

% ---------- Route B leg 1 ----------
flatland_waypoint(2,wp_b1_origin,8,1).
flatland_waypoint(2,wp_b1_c,8,7).
station(origin,2,wp_b1_origin).
station(station_c,2,wp_b1_c).
must_visit(2,origin).
must_visit(2,station_c).
station_order(2,origin,station_c).

% ---------- Route B leg 2 ----------
flatland_waypoint(3,wp_b2_c,11,1).
flatland_waypoint(3,wp_b2_destination,11,7).
station(station_c,3,wp_b2_c).
station(destination,3,wp_b2_destination).
must_visit(3,station_c).
must_visit(3,destination).
station_order(3,station_c,destination).

passenger(p1).
passenger_origin(p1,origin).
passenger_destination(p1,destination).

% ------------------------------------------------------------
% Fixed service timetable for E3.
%
% Route A (fast but high wait):
%   Train 0: Origin t=2 -> B t=5
%   Train 1: B t=10 -> Destination t=13
%   passenger wait at B = 5
%   total passenger journey = 11
%
% Route B (slower but low wait):
%   Train 2: Origin t=2 -> C t=8
%   Train 3: C t=9 -> Destination t=15
%   passenger wait at C = 1
%   total passenger journey = 13
%
% These constraints prevent ASP from delaying Train 0 merely to reduce
% passenger waiting. E3 is intended to compare two fixed timetables.
% ------------------------------------------------------------

:- first_station_visit(0,origin,T), T != 2.
:- first_station_visit(0,station_b,T), T != 5.

:- first_station_visit(1,station_b,T), T != 10.
:- first_station_visit(1,destination,T), T != 13.

:- first_station_visit(2,origin,T), T != 2.
:- first_station_visit(2,station_c,T), T != 8.

:- first_station_visit(3,station_c,T), T != 9.
:- first_station_visit(3,destination,T), T != 15.

#show chosen_leg/7.
#show passenger_journey_time/2.
#show passenger_transfer_wait/2.
#show transfer_count/2.
