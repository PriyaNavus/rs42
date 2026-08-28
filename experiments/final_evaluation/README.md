# RS42 Final Evaluation

This folder contains the final controlled evaluation of the RS42
preference-aware railway scheduling system.

## Frozen backend

The evaluation assumes the validated backend is frozen:
- scenario isolation
- semantic objective profiles
- passenger OD itinerary selection
- ASP -> Flatland execution validation
- reached trains removed from active ASP occupancy after reaching target

Do not modify those components during evaluation unless a regression fails.

## Environments

Four deterministic Flatland environments are used.

### E1 - Fast vs Slow Route
Two passenger services from the same origin to destination with a clear
journey-time difference.

Primary question:
Does Fastest choose the lower-time service?

### E2 - Transfer Network
A slower direct service competes with a faster journey through multiple
intermediate stations/trains.

Primary question:
Does Fastest accept transfers while Fewer Transfers prefers the slower
direct service?

### E3 - Waiting Network
A lower-total-time itinerary contains more connection waiting while an
alternative has lower waiting but a longer journey.

Primary question:
Does Less Waiting sacrifice journey time to reduce waiting?

### E4 - Simple vs Complex Route
A short route has greater turn/route complexity while a longer route is
simpler.

Primary question:
Does Simple Journey accept longer travel for fewer turns?

## Profiles

Every environment is evaluated with the same five profiles:
1. Fastest
2. Less Waiting
3. Fewer Transfers
4. Simple Journey
5. Balanced

This produces 4 x 5 = 20 primary optimization runs.

## Output policy

Never save final experiment outputs into temporary tool folders.

- results/runs/       one row/result per environment-profile run
- results/summaries/  consolidated CSV/JSON tables
- results/validation/ Flatland execution validation
- raw/                raw ASP/solver output
- plots/              report-ready figures
- logs/               execution logs
- configs/            immutable experiment metadata/configuration

Each environment should also keep canonical assets in:
- envs/pkl/
- envs/lp/
- envs/png/
- asp/scenarios/

Final environment names:
- e1_fast_slow
- e2_transfer_network
- e3_waiting_network
- e4_simple_complex

## Evaluation rule

Within an environment, the railway and passenger OD remain fixed.
Only the preference profile changes.

Across environments, the physical/timetable structure changes to expose
a different controlled trade-off.
