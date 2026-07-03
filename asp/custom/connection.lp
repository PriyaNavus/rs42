
% Straight Tracks
connection(32800, (n,s)). connection(1025,  (w,e)).
% Curves
connection(4608,  (s,w)). connection(16386, (e,s)).
connection(72,    (n,e)). connection(2064,  (w,n)).
% Switches
connection(37408, (n,s)). connection(37408, (s,w)).
connection(17411, (w,e)). connection(17411, (e,s)).
connection(32872, (n,s)). connection(32872, (n,e)).
connection(3089,  (w,e)). connection(3089,  (w,n)).
connection(49186, (n,s)). connection(49186, (e,s)).
connection(1097,  (w,e)). connection(1097,  (n,e)).
connection(34864, (n,s)). connection(34864, (w,n)).
connection(5633,  (w,e)). connection(5633,  (s,w)).
% Crossings & Slips
connection(33825, (n,s)). connection(33825, (w,e)).
connection(38433, (n,s)). connection(38433, (w,e)). connection(38433, (s,w)).
connection(50211, (n,s)). connection(50211, (w,e)). connection(50211, (e,s)).
connection(33897, (n,s)). connection(33897, (w,e)). connection(33897, (n,e)).
connection(35889, (n,s)). connection(35889, (w,e)). connection(35889, (w,n)).
connection(38505, (n,s)). connection(38505, (w,e)). connection(38505, (n,e)). connection(38505, (s,w)).
connection(52275, (n,s)). connection(52275, (w,e)). connection(52275, (e,s)). connection(52275, (w,n)).
connection(20994, (e,s)). connection(20994, (s,w)).
connection(16458, (n,e)). connection(16458, (e,s)).
connection(2136,  (w,n)). connection(2136,  (n,e)).
connection(6672,  (s,w)). connection(6672,  (w,n)).

% Symmetric rule: tracks are traversable from both directions
connection(V, (D2, D1)) :- connection(V, (D1, D2)).

% Map text headings to integers to easily calculate turn directions
direction_map(n,0). direction_map(e,1). direction_map(s,2). direction_map(w,3).

% Map integer turns back to text headings for graph building
dir_int_to_let(0,n). dir_int_to_let(1,e). dir_int_to_let(2,s). dir_int_to_let(3,w).

% Relative grid offsets for matrix cell step detection
offset(n,-1,0). offset(s,1,0). offset(w,0,-1). offset(e,0,1).

% Opposite handshakes for entering boundary walls
opposite(n,s). opposite(s,n). opposite(e,w). opposite(w,e).

% Defines adjacent matrix cells based on spatial compass offsets
adjacent((X,Y), D, (X',Y')) :-
    cell((X,Y),_), cell((X',Y'),_),
    offset(D,DX,DY), X'=X+DX, Y'=Y+DY.

% Confirms a physical exit-to-entry match between two cells
connected((X,Y), D, (X',Y')) :-
    cell((X,Y), T), cell((X',Y'), T'),
    adjacent((X,Y), D, (X',Y')),
    connection(T,  (_,D)),
    opposite(D, Opp),
    connection(T', (Opp,_)).

% Builds subnodes out of cells based on active track layout exits
subnode(X,Y,D) :- cell((X,Y),T), connection(T,(_,D)).

% Builds static directed track edge lines between nodes using text headings
edge((X,Y,D), (X',Y',D')) :-
    subnode(X,Y,D), subnode(X',Y',D'),
    connected((X,Y), D, (X',Y')),
    cell((X',Y'),T'),
    opposite(D, Opp),
    connection(T',(Opp,D')).