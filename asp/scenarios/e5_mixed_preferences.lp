% RS42 E5 - Frozen Validated Mixed Preference Network

% Direct Train 0
flatland_waypoint(0,wp_d_o,2,1).
flatland_waypoint(0,wp_d_d,2,15).
station(origin,0,wp_d_o).
station(destination,0,wp_d_d).
must_visit(0,origin).
must_visit(0,destination).
station_order(0,origin,destination).

% Fast route: Train 1 -> Train 2 -> Train 3
flatland_waypoint(1,wp_f1_o,7,1).
flatland_waypoint(1,wp_f1_b,6,4).
station(origin,1,wp_f1_o).
station(station_b,1,wp_f1_b).
must_visit(1,origin).
must_visit(1,station_b).
station_order(1,origin,station_b).

flatland_waypoint(2,wp_f2_b,9,5).
flatland_waypoint(2,wp_f2_c,10,8).
station(station_b,2,wp_f2_b).
station(station_c,2,wp_f2_c).
must_visit(2,station_b).
must_visit(2,station_c).
station_order(2,station_b,station_c).

flatland_waypoint(3,wp_f3_c,12,9).
flatland_waypoint(3,wp_f3_d,11,12).
station(station_c,3,wp_f3_c).
station(destination,3,wp_f3_d).
must_visit(3,station_c).
must_visit(3,destination).
station_order(3,station_c,destination).

% Compromise route: Train 4 -> Train 5
flatland_waypoint(4,wp_c1_o,18,1).
flatland_waypoint(4,wp_c1_h,16,6).
station(origin,4,wp_c1_o).
station(station_h,4,wp_c1_h).
must_visit(4,origin).
must_visit(4,station_h).
station_order(4,origin,station_h).

flatland_waypoint(5,wp_c2_h,22,7).
flatland_waypoint(5,wp_c2_d,20,13).
station(station_h,5,wp_c2_h).
station(destination,5,wp_c2_d).
must_visit(5,station_h).
must_visit(5,destination).
station_order(5,station_h,destination).

passenger(p1).
passenger_origin(p1,origin).
passenger_destination(p1,destination).

% Fixed service timetable.
%
% Direct:
%   2 -> 20
%   journey 18
%   wait 0
%   transfers 0
%
% Fast:
%   2 -> 6
%   7 -> 11
%   12 -> 16
%   journey 14
%   wait 2
%   transfers 2
%
% Compromise:
%   2 -> 9
%   10 -> 18
%   journey 16
%   wait 1
%   transfers 1

:- first_station_visit(0,origin,T), T != 2.
:- first_station_visit(0,destination,T), T != 20.

:- first_station_visit(1,origin,T), T != 2.
:- first_station_visit(1,station_b,T), T != 6.

:- first_station_visit(2,station_b,T), T != 7.
:- first_station_visit(2,station_c,T), T != 11.

:- first_station_visit(3,station_c,T), T != 12.
:- first_station_visit(3,destination,T), T != 16.

:- first_station_visit(4,origin,T), T != 2.
:- first_station_visit(4,station_h,T), T != 9.

:- first_station_visit(5,station_h,T), T != 10.
:- first_station_visit(5,destination,T), T != 18.
