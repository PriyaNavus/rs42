% ============================================================
% passenger_transfer.lp
% RS42 passenger journey and transfer model
%
% Supports two modes:
%
% 1. Legacy fixed-itinerary passengers
%    passenger/1 + uses_train/3 + transfer_station/1
%    Kept for backwards compatibility with existing scenarios.
%
% 2. OD passengers
%    passenger/1 + passenger_origin/2 + passenger_destination/2
%    The solver chooses a feasible train itinerary.
% ============================================================

#const max_passenger_legs = 3.
#const ideal_transfer_time = 6.

% ------------------------------------------------------------
% Common station-service relation
% ------------------------------------------------------------

serves_station(Train, Station) :-
    visited_station(Train, Station).

% ============================================================
% LEGACY MODE
% ============================================================

od_passenger(P) :-
    passenger(P),
    passenger_origin(P,_),
    passenger_destination(P,_).

legacy_passenger(P) :-
    passenger(P),
    not od_passenger(P).

% Legacy transfer semantics are preserved exactly so existing
% scenarios remain regression-compatible.
valid_transfer(P, Station, Train1, Train2) :-
    legacy_passenger(P),
    transfer_station(Station),
    uses_train(P, Train1, Order1),
    uses_train(P, Train2, Order2),
    Train1 != Train2,
    Order1 < Order2,
    serves_station(Train1, Station),
    serves_station(Train2, Station).

legacy_transfer(P, Station) :-
    valid_transfer(P, Station, _, _).

transfer_count(P, N) :-
    legacy_passenger(P),
    N = #count {
        Station : legacy_transfer(P, Station)
    }.

% ============================================================
% OD MODE: SOLVER-SELECTED PASSENGER ITINERARY
% ============================================================

journey_leg(1..max_passenger_legs).

% A passenger may ride a train from FromStation to ToStation
% only when that train actually visits FromStation first and
% ToStation later in the generated railway schedule.
ride_option(Train, FromStation, ToStation, Depart, Arrive) :-
    first_station_visit(Train, FromStation, Depart),
    first_station_visit(Train, ToStation, Arrive),
    FromStation != ToStation,
    Depart < Arrive.

% Select the number of train legs in the passenger journey.
1 {
    journey_length(P,L) : journey_leg(L)
} 1 :-
    od_passenger(P).

% For every active leg choose exactly one feasible train ride.
1 {
    chosen_leg(P,I,Train,FromStation,ToStation,Depart,Arrive) :
        ride_option(Train,FromStation,ToStation,Depart,Arrive)
} 1 :-
    od_passenger(P),
    journey_length(P,L),
    journey_leg(I),
    I <= L.

% First selected ride must start at the passenger origin.
:- passenger_origin(P,Origin),
   chosen_leg(P,1,_,FromStation,_,_,_),
   FromStation != Origin.

% Last selected ride must terminate at the passenger destination.
:- passenger_destination(P,Destination),
   journey_length(P,L),
   chosen_leg(P,L,_,_,ToStation,_,_),
   ToStation != Destination.

% Consecutive legs must connect at the same station.
:- chosen_leg(P,I,_,_,TransferStation,_,_),
   chosen_leg(P,J,_,NextStation,_,_,_),
   J = I + 1,
   TransferStation != NextStation.

% A transfer must provide at least min_transfer_time time units between arrival and the next departure.
:- chosen_leg(P,I,_,_,TransferStation,_,Arrive),
   chosen_leg(P,J,_,TransferStation,_,Depart,_),
   J = I + 1,
   Depart < Arrive.

% Consecutive legs on the same train are redundant: they can be
% represented as one longer ride on that train.
:- chosen_leg(P,I,Train,_,_,_,_),
   chosen_leg(P,J,Train,_,_,_,_),
   J = I + 1.

chosen_transfer(P,I,Station,FromTrain,ToTrain,Arrive,Depart) :-
    chosen_leg(P,I,FromTrain,_,Station,_,Arrive),
    chosen_leg(P,J,ToTrain,Station,_,Depart,_),
    J = I + 1.

transfer_count(P,N) :-
    od_passenger(P),
    N = #count {
        I,Station,FromTrain,ToTrain,Arrive,Depart :
            chosen_transfer(
                P,I,Station,FromTrain,ToTrain,Arrive,Depart
            )
    }.

% Passenger journey duration:
% final arrival minus first boarding/departure time.
passenger_journey_time(P,Duration) :-
    od_passenger(P),
    journey_length(P,L),
    chosen_leg(P,1,_,_,_,Depart,_),
    chosen_leg(P,L,_,_,_,_,Arrive),
    Duration = Arrive - Depart.

% Waiting caused specifically by changing trains.
transfer_wait(P,I,Wait) :-
    chosen_transfer(P,I,_,_,_,Arrive,Depart),
    Wait = Depart - Arrive.

% Soft passenger preference: a transfer is most comfortable at
% ideal_transfer_time (= 6) time units. Shorter and longer connections
% remain feasible but are penalized by their absolute deviation from 6.
transfer_deviation(P,I,Deviation) :-
    transfer_wait(P,I,Wait),
    Wait < ideal_transfer_time,
    Deviation = ideal_transfer_time - Wait.

transfer_deviation(P,I,Deviation) :-
    transfer_wait(P,I,Wait),
    Wait >= ideal_transfer_time,
    Deviation = Wait - ideal_transfer_time.

passenger_transfer_deviation(P,Total) :-
    od_passenger(P),
    Total = #sum {
        Deviation,I : transfer_deviation(P,I,Deviation)
    }.

passenger_transfer_wait(P,Total) :-
    od_passenger(P),
    Total = #sum {
        Wait,I : transfer_wait(P,I,Wait)
    }.

% Trains used by a selected passenger journey.
passenger_uses_train(P,Train) :-
    chosen_leg(P,_,Train,_,_,_,_).

#show valid_transfer/4.
#show chosen_leg/7.
#show chosen_transfer/7.
#show journey_length/2.
#show passenger_journey_time/2.
#show passenger_transfer_wait/2.
#show passenger_transfer_deviation/2.
#show transfer_count/2.
