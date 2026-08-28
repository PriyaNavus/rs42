% RS42 Experiment 1: controlled OD preference trade-off
objective_mode(fastest).

#const w_arrival = 8.
#const w_wait = 8.
#const w_transfer = 8.
#const w_turn = 4.
#const w_waypoint = 6.

passenger(p).
passenger_origin(p,a).
passenger_destination(p,d).

% Direct service: a -> d, duration 9, zero transfers.
first_station_visit(0,a,1).
first_station_visit(0,d,10).

% Faster transfer service:
% train 1 a -> b, then train 2 b -> d.
first_station_visit(1,a,1).
first_station_visit(1,b,4).

first_station_visit(2,b,5).
first_station_visit(2,d,7).

turns(0,1).
turns(1,1).
turns(2,1).

waypoint_time(0,0).
waypoint_time(1,0).
waypoint_time(2,0).

#show chosen_leg/7.
#show passenger_journey_time/2.
#show passenger_transfer_wait/2.
#show transfer_count/2.
