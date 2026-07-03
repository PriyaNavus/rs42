% ============================================================
% waypoints.lp
% Required intermediate waypoint constraints
% ============================================================

waypoint(0, wp1, 24, 14).
waypoint(0, wp2, 24, 18).

waypoint_order(0, wp1, wp2).

visited_waypoint(ID, WP) :-
    waypoint(ID, WP, X, Y),
    pos(ID, X, Y, _, T).

:- waypoint(ID, WP, _, _),
   not visited_waypoint(ID, WP).

#show visited_waypoint/2.