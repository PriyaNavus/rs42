% RS42 E2 - Curved Transfer Network

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
flatland_waypoint(2,wp_t2_c,10,12).
station(station_b,2,wp_t2_b).
station(station_c,2,wp_t2_c).
must_visit(2,station_b).
must_visit(2,station_c).
station_order(2,station_b,station_c).

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

% Final E2 timetable using the actual route lengths.
% Direct:   2 -> 26 = journey 24
% Transfer: 2 -> 9, 10 -> 17, 18 -> 25 = journey 23, wait 2
:- first_station_visit(0,origin,T), T != 2.
:- first_station_visit(0,destination,T), T != 26.

:- first_station_visit(1,origin,T), T != 2.
:- first_station_visit(1,station_b,T), T != 9.
:- first_station_visit(2,station_b,T), T != 10.
:- first_station_visit(2,station_c,T), T != 17.
:- first_station_visit(3,station_c,T), T != 18.
:- first_station_visit(3,destination,T), T != 25.
