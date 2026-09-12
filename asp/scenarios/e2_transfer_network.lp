% RS42 E2 - Passenger-aware transfer network
%
% Demonstrates minimum transfer time = 6.
%
% Direct option:
%   Train 0: origin 2 -> destination 26
%   journey time = 24, transfers = 0
%
% Transfer option:
%   Train 1: origin 2 -> station_b 9
%   Train 2: station_b 15 -> destination 22
%   transfer time = 15 - 9 = 6
%   journey time = 22 - 2 = 20, transfers = 1
%
% Expected preference separation:
%   Fastest          -> Train 1 -> Train 2
%   Fewer Transfers  -> Train 0

flatland_waypoint(0,wp_direct_origin,2,1).
flatland_waypoint(0,wp_direct_destination,5,16).
station(origin,0,wp_direct_origin).
station(destination,0,wp_direct_destination).
must_visit(0,origin).
must_visit(0,destination).
station_order(0,origin,destination).

flatland_waypoint(1,wp_t1_origin,9,1).
flatland_waypoint(1,wp_t1_b,10,5).
station(origin,1,wp_t1_origin).
station(station_b,1,wp_t1_b).
must_visit(1,origin).
must_visit(1,station_b).
station_order(1,origin,station_b).

flatland_waypoint(2,wp_t2_b,9,8).
flatland_waypoint(2,wp_t2_destination,10,12).
station(station_b,2,wp_t2_b).
station(destination,2,wp_t2_destination).
must_visit(2,station_b).
must_visit(2,destination).
station_order(2,station_b,destination).

flatland_waypoint(3,wp_t3_c,9,15).
flatland_waypoint(3,wp_t3_destination,10,19).
station(station_c,3,wp_t3_c).
station(destination,3,wp_t3_destination).
must_visit(3,station_c).
must_visit(3,destination).
station_order(3,station_c,destination).

passenger(p1).
passenger_origin(p1,origin).
passenger_destination(p1,destination).

:- first_station_visit(0,origin,T), T != 2.
:- first_station_visit(0,destination,T), T != 26.

:- first_station_visit(1,origin,T), T != 2.
:- first_station_visit(1,station_b,T), T != 9.

:- first_station_visit(2,station_b,T), T != 15.
:- first_station_visit(2,destination,T), T != 22.

:- first_station_visit(3,station_c,T), T != 18.
:- first_station_visit(3,destination,T), T != 25.
