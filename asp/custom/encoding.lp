% =============================================================
% Team RS42 - action encoding
% Pairs with connection.lp (graph building, direction helpers).
% Produces repo-compatible output: action(train(ID), Action, Time).
% Action is one of: move_forward, move_left, move_right, wait
% =============================================================

% Allowed actions (atoms with underscores so solve.py can read them)
action_type(move_forward; move_left; move_right; wait).

% Planning horizon.
% Use the environment's global() horizon when present (newer envs),
% otherwise fall back to the latest train deadline (older envs).
has_global :- global(_).
max_time(MT) :- global(MT).
max_time(MT) :- MT = #max{ T : end(_,_,T) }, not has_global.

% How each steering action changes the heading (integers 0=n,1=e,2=s,3=w)
action_dir(InDir, move_forward, InDir)        :- direction_map(_, InDir).
action_dir(InDir, move_left,    (InDir+3)\4)  :- direction_map(_, InDir).
action_dir(InDir, move_right,   (InDir+1)\4)  :- direction_map(_, InDir).

% Train state at its spawn time
pos(ID, X, Y, DirNum, T_start) :-
    start(ID, (X, Y), T_start, DirLetter),
    direction_map(DirLetter, DirNum).

% Exactly one action per train per time step (until the train has arrived)
{ action(train(ID), Act, T) : action_type(Act) } = 1 :-
    pos(ID, X, Y, Dir, T), not reached(ID, T), max_time(MT), T < MT.

% Moving: the action must match a real edge in the track graph
pos(ID, X', Y', OutDirNum, T+1) :-
    pos(ID, X, Y, InDirNum, T), action(train(ID), Act, T), Act != wait,
    action_dir(InDirNum, Act, OutDirNum),
    dir_int_to_let(InDirNum, InLetter),
    dir_int_to_let(OutDirNum, OutLetter),
    edge((X, Y, InLetter), (X', Y', OutLetter)),
    max_time(MT), T < MT.

% Waiting: stay in place, keep heading
pos(ID, X, Y, Dir, T+1) :-
    pos(ID, X, Y, Dir, T), action(train(ID), wait, T), max_time(MT), T < MT.

% After reaching the goal, the train stays anchored at its target cell
pos(ID, X, Y, Dir, T+1) :-
    pos(ID, X, Y, Dir, T), reached(ID, T), max_time(MT), T < MT.

% A train has reached its goal once it sits on its target cell
reached(ID, T) :- pos(ID, X, Y, _, T), end(ID, (X, Y), _).

% Hard constraint: every train must reach its goal
:- train(ID), not reached(ID, _).

% No two trains in the same cell at the same time
:- pos(ID1, X, Y, _, T), pos(ID2, X, Y, _, T), ID1 < ID2.

% No head-on swap across a track
:- pos(ID1, X1, Y1, _, T), pos(ID2, X2, Y2, _, T),
   pos(ID1, X2, Y2, _, T+1), pos(ID2, X1, Y1, _, T+1), ID1 < ID2.

#show action/3.
