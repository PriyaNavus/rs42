% =============================================================
% team rs42 - action encoding
% pairs with connection.lp (graph building, direction helpers).
% output: action(train(ID), Action, Time) with
% move_forward, move_left, move_right, wait
%
% two conventions matter so the flatland replay matches the plan
% (both verified against a failing replay, see readme):
% 1. spawn: a train with start time N is off the map until N+2.
%    it must send wait 0..N, the spawning move_forward at N+1,
%    and stands on its start cell at N+2 (krr-up reference does
%    the same).
% 2. steering labels: flatland reads left/right relative to the
%    direction the train is facing in its current cell. we choose
%    the route internally (steer/3) and derive the labels from
%    consecutive movement directions afterwards. deriving them
%    from the edge letters directly emits turns one step early,
%    flatland then ignores them at switches and trains deadlock.
% =============================================================

% allowed route decisions per timestep
action_type(move_forward; move_left; move_right; wait).

% planning horizon: environment global() if present, else latest deadline
has_global :- global(_).
max_time(MT) :- global(MT).
max_time(MT) :- MT = #max{ T : end(_,_,T) }, not has_global.

% how each decision changes the outgoing direction (0=n,1=e,2=s,3=w)
action_dir(InDir, move_forward, InDir)        :- direction_map(_, InDir).
action_dir(InDir, move_left,    (InDir+3)\4)  :- direction_map(_, InDir).
action_dir(InDir, move_right,   (InDir+1)\4)  :- direction_map(_, InDir).

% ---- spawn convention (1) ----
% forced flatland actions before the train exists on the map
action(train(ID), wait, 0..N) :- start(ID, _, N, _).
action(train(ID), move_forward, N+1) :- start(ID, _, N, _).

% the train stands on its start cell at N+2
pos(ID, X, Y, DirNum, N+2) :-
    start(ID, (X, Y), N, DirLetter),
    direction_map(DirLetter, DirNum).

% ---- route choice (internal) ----
% exactly one decision per train per on-map timestep until arrival
{ steer(ID, Act, T) : action_type(Act) } = 1 :-
    pos(ID, X, Y, Dir, T), not reached(ID, T), max_time(MT), T < MT.

% moving: the decision must match a real edge in the track graph
pos(ID, X', Y', OutDirNum, T+1) :-
    pos(ID, X, Y, InDirNum, T), steer(ID, Act, T), Act != wait,
    action_dir(InDirNum, Act, OutDirNum),
    dir_int_to_let(InDirNum, InLetter),
    dir_int_to_let(OutDirNum, OutLetter),
    edge((X, Y, InLetter), (X', Y', OutLetter)),
    max_time(MT), T < MT.

% waiting: stay in place, keep the planned outgoing direction
pos(ID, X, Y, Dir, T+1) :-
    pos(ID, X, Y, Dir, T), steer(ID, wait, T), max_time(MT), T < MT.

% after reaching the goal, the train stays anchored at its target cell
pos(ID, X, Y, Dir, T+1) :-
    pos(ID, X, Y, Dir, T), reached(ID, T), max_time(MT), T < MT.

% ---- flatland labels (2) ----
% direction of the move a train actually performs at time T
movedir(ID, D, T) :- pos(ID, _, _, D, T), steer(ID, Act, T), Act != wait.

% facing: where the train looks while sitting in a cell.
% at spawn it faces its start direction, after a move it faces
% where it moved, waiting keeps the facing.
facing(ID, D, N+2) :- start(ID, _, N, L), direction_map(L, D).
facing(ID, D, T+1) :- movedir(ID, D, T).
facing(ID, D, T+1) :- facing(ID, D, T), steer(ID, wait, T).

% label = rotation between facing and the direction moved
action(train(ID), move_forward, T) :- movedir(ID, D, T),  facing(ID, D, T).
action(train(ID), move_right,   T) :- movedir(ID, D2, T), facing(ID, D1, T), D2 = (D1+1)\4.
action(train(ID), move_left,    T) :- movedir(ID, D2, T), facing(ID, D1, T), D2 = (D1+3)\4.
% dead ends reverse with a plain forward in flatland
action(train(ID), move_forward, T) :- movedir(ID, D2, T), facing(ID, D1, T), D2 = (D1+2)\4.
action(train(ID), wait, T) :- steer(ID, wait, T).

% ---- goal and safety ----
% a train has reached its goal once it sits on its target cell
reached(ID, T) :- pos(ID, X, Y, _, T), end(ID, (X, Y), _).

% hard constraint: every train must reach its goal
:- train(ID), not reached(ID, _).

% no two trains in the same cell at the same time
:- pos(ID1, X, Y, _, T), pos(ID2, X, Y, _, T), ID1 < ID2.

% no head-on swap across a track
:- pos(ID1, X1, Y1, _, T), pos(ID2, X2, Y2, _, T),
   pos(ID1, X2, Y2, _, T+1), pos(ID2, X1, Y1, _, T+1), ID1 < ID2.

#show action/3.
