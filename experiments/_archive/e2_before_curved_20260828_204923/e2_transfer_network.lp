% RS42 E2 - Curved Transfer Network

flatland_waypoint(0,wp_direct_origin,2,1).
flatland_waypoint(0,wp_direct_destination,2,13).
station(origin,0,wp_direct_origin).
station(destination,0,wp_direct_destination).
must_visit(0,origin).
must_visit(0,destination).
station_order(0,origin,destination).

flatland_waypoint(1,wp_t1_origin,9,1).
flatland_waypoint(1,wp_t1_b,7,3).
station(origin,1,wp_t1_origin).
station(station_b,1,wp_t1_b).
must_visit(1,origin).
must_visit(1,station_b).
station_order(1,origin,station_b).

flatland_waypoint(2,wp_t2_b,8,5).
flatland_waypoint(2,wp_t2_c,8,7).
station(station_b,2,wp_t2_b).
station(station_c,2,wp_t2_c).
must_visit(2,station_b).
must_visit(2,station_c).
station_order(2,station_b,station_c).

flatland_waypoint(3,wp_t3_c,9,9).
flatland_waypoint(3,wp_t3_destination,7,11).
station(station_c,3,wp_t3_c).
station(destination,3,wp_t3_destination).
must_visit(3,station_c).
must_visit(3,destination).
station_order(3,station_c,destination).

passenger(p1).
passenger_origin(p1,origin).
passenger_destination(p1,destination).
