% RS42 Final Evaluation E2 - Transfer Network

% Direct service
flatland_waypoint(0,wp_direct_origin,2,1).
flatland_waypoint(0,wp_direct_destination,2,19).
station(origin,0,wp_direct_origin).
station(destination,0,wp_direct_destination).
must_visit(0,origin).
must_visit(0,destination).
station_order(0,origin,destination).

% Transfer leg 1: Origin -> B
flatland_waypoint(1,wp_t1_origin,5,1).
flatland_waypoint(1,wp_t1_b,5,5).
station(origin,1,wp_t1_origin).
station(station_b,1,wp_t1_b).
must_visit(1,origin).
must_visit(1,station_b).
station_order(1,origin,station_b).

% Transfer leg 2: B -> C
flatland_waypoint(2,wp_t2_b,8,1).
flatland_waypoint(2,wp_t2_c,8,5).
station(station_b,2,wp_t2_b).
station(station_c,2,wp_t2_c).
must_visit(2,station_b).
must_visit(2,station_c).
station_order(2,station_b,station_c).

% Transfer leg 3: C -> Destination
flatland_waypoint(3,wp_t3_c,11,1).
flatland_waypoint(3,wp_t3_destination,11,5).
station(station_c,3,wp_t3_c).
station(destination,3,wp_t3_destination).
must_visit(3,station_c).
must_visit(3,destination).
station_order(3,station_c,destination).

passenger(p1).
passenger_origin(p1,origin).
passenger_destination(p1,destination).

#show chosen_leg/7.
#show passenger_journey_time/2.
#show passenger_transfer_wait/2.
#show transfer_count/2.
