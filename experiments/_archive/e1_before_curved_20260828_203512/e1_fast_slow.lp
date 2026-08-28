% RS42 E1 - Curved Fast vs Slow

flatland_waypoint(0,wp_fast_origin,2,1).
flatland_waypoint(0,wp_fast_destination,3,8).
station(origin,0,wp_fast_origin).
station(destination,0,wp_fast_destination).
must_visit(0,origin).
must_visit(0,destination).
station_order(0,origin,destination).

flatland_waypoint(1,wp_slow_origin,10,1).
flatland_waypoint(1,wp_slow_destination,12,13).
station(origin,1,wp_slow_origin).
station(destination,1,wp_slow_destination).
must_visit(1,origin).
must_visit(1,destination).
station_order(1,origin,destination).

passenger(p1).
passenger_origin(p1,origin).
passenger_destination(p1,destination).
