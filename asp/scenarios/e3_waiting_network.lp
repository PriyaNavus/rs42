% RS42 E3 - Transfer Timing Preference
%
% Route A: slightly slower but ideal transfer
%   Train 0: origin 2 -> station_b 10
%   Train 1: station_b 16 -> destination 24
%   passenger journey = 22
%   transfer wait = 6
%   deviation from ideal 6 = 0
%
% Route B: faster but tight transfer
%   Train 2: origin 2 -> station_c 12
%   Train 3: station_c 13 -> destination 23
%   passenger journey = 21
%   transfer wait = 1
%   deviation from ideal 6 = 5
%
% Expected profile separation:
%   Fastest -> Route B
%   Less Waiting (ideal transfer: 6 steps) -> Route A

flatland_waypoint(0,wp_a1_origin,2,1).
flatland_waypoint(0,wp_a1_b,3,6).
station(origin,0,wp_a1_origin).
station(station_b,0,wp_a1_b).
must_visit(0,origin).
must_visit(0,station_b).
station_order(0,origin,station_b).

flatland_waypoint(1,wp_a2_b,2,10).
flatland_waypoint(1,wp_a2_destination,3,15).
station(station_b,1,wp_a2_b).
station(destination,1,wp_a2_destination).
must_visit(1,station_b).
must_visit(1,destination).
station_order(1,station_b,destination).

flatland_waypoint(2,wp_b1_origin,8,1).
flatland_waypoint(2,wp_b1_c,9,8).
station(origin,2,wp_b1_origin).
station(station_c,2,wp_b1_c).
must_visit(2,origin).
must_visit(2,station_c).
station_order(2,origin,station_c).

flatland_waypoint(3,wp_b2_c,8,12).
flatland_waypoint(3,wp_b2_destination,9,19).
station(station_c,3,wp_b2_c).
station(destination,3,wp_b2_destination).
must_visit(3,station_c).
must_visit(3,destination).
station_order(3,station_c,destination).

passenger(p1).
passenger_origin(p1,origin).
passenger_destination(p1,destination).

% Fixed service timetable.
:- first_station_visit(0,origin,T), T != 2.
:- first_station_visit(0,station_b,T), T != 10.
:- first_station_visit(1,station_b,T), T != 16.
:- first_station_visit(1,destination,T), T != 24.

:- first_station_visit(2,origin,T), T != 2.
:- first_station_visit(2,station_c,T), T != 12.
:- first_station_visit(3,station_c,T), T != 13.
:- first_station_visit(3,destination,T), T != 23.
