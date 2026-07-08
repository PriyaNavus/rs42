# group rs42 - passenger convenience planner

team: priya and orkan. course: railway scheduling with flatland and asp, supervised by r. kepler james murphy.

this file documents our own work. the original toolkit readme from the krr-up/flatland repo is kept unchanged next to it, see README.md for build and solve basics.

## requirements

for the ui and the quick check (clingo mode), this is enough:

    pip install clingo
    conda install -c conda-forge streamlit

(on mac, installing streamlit via conda-forge avoids a pyarrow build error that plain pip can run into.)

for the full animation mode (solve.py), additionally:

    pip install "flatland-rl<4" imageio

the version pin matters: our pkl environments were built with flatland v3, and a v4 install cannot unpickle them (module layout changed, you get 'no module named flatland.core.grid.rail_env_grid'). if flatland-rl refuses to install on a recent python, create a separate conda environment with an older python just for this repo, for example 'conda create -n flatland python=3.10', activate it, and install everything there.

first start of streamlit: it asks for an email address once. just press enter to skip. to never see the prompt, create the file '~/.streamlit/config.toml' with these two lines:

    [browser]
    gatherUsageStats = false

## what this project does

instead of only finding collision free schedules, we plan from the passenger's point of view. for a passenger travelling between cities, we compute the most convenient ride and make 'convenient' measurable: early arrival, little waiting, few transfers, few turns (comfort for motion sick passengers), and reaching intermediate stops early. each criterion is turned into a number, weighted, and minimized with clingo's '#minimize'. the most convenient ride is the schedule with the lowest total weighted cost.

## architecture

python -> flatland environment -> waypoint extraction (tools/extract_flatland_waypoints.py) -> generated_waypoints.lp -> station mapping and ordering (waypoint.lp) -> passenger transfer validation (passenger_transfer.lp) -> preference weights (asp/profiles) -> asp optimization (visual.lp) -> flatland simulation (solve.py).

the encoding stack in asp/custom:

- connection.lp: builds the track graph from the environment facts
- encoding.lp: chooses one action per train per timestep, outputs 'action(train(id), action, time)' with move_forward, move_left, move_right, wait
- generated_waypoints.lp: auto extracted waypoints per train
- waypoint.lp: stations, must visit constraints, visit order
- passenger_transfer.lp: passenger itineraries and transfer counting
- visual.lp: the cost layer. arrival, waiting, turns, waypoint times and transfers, each multiplied by its weight, one '#minimize' over all costs

## preference profiles and the ui

profiles live in asp/profiles as five '#const' lines each: w_arrival, w_wait, w_transfer, w_turn, w_waypoint. bigger weight means the criterion matters more. current profiles: fastest, least_waiting, fewest_transfers, balanced, comfort (high w_turn, for motion sick passengers).

the ui is a streamlit app in ui/app.py. the user picks a profile or sets custom weights with sliders, chooses an environment, and solves. the mechanism: the ui writes the chosen weights into asp/profiles/active_profile.lp, and that file is listed in the primary list of asp/params.py. that is how the user's choice actually reaches the solver.

important: this replaces the older run_preference.py approach. run_preference.py passed the profile file as an extra command line argument to solve.py, but solve.py ignores extra arguments and only reads asp/params.py. the active_profile mechanism closes that gap.

the ui has two solve modes:

- quick check: runs plain clingo on the lp environment, shows the optimization value, the metrics (arrival, waiting, turns, transfers, costs) and the schedule. works today.
- full animation: runs solve.py on the pkl environment and displays the resulting gif in the browser.

## how to run

requirements: python with clingo and streamlit installed ('pip install clingo streamlit'), plus the flatland setup from the original readme for the animation mode.

from the repo root:

    streamlit run ui/app.py

for a manual check without the ui:

    clingo envs/lp/env_001--2_4.lp asp/custom/connection.lp asp/custom/encoding.lp asp/custom/generated_waypoints.lp asp/custom/waypoint.lp asp/custom/passenger_transfer.lp asp/custom/visual.lp asp/profiles/active_profile.lp

verified working: this exact call finds the optimum on env_001--2_4 including a valid transfer of passenger p1 at station s2.

## conventions and settings

- all trains run at full speed (one cell per timestep), fractional speeds are disabled in envs/params.py
- no malfunctions, we define our own solvable environments
- replay convention 1, spawning: a train with start time n is off the map until n+2. the encoding forces wait actions for 0..n, the spawning move_forward at n+1, and puts the train on its start cell at n+2 (same as the krr-up reference). planning as if the train was on the map at n desyncs plan and simulation
- replay convention 2, steering labels: flatland reads move_left and move_right relative to the direction the train is facing in its current cell. the encoding chooses the route internally (steer/3) and derives the labels from consecutive movement directions. deriving labels from the edge letters directly emits turns one step early, flatland then ignores them at switches and trains deadlock (we hit exactly this, verified via output paths.csv)
- solve.py executes the model list built in modules/actionlist.py. with '#minimize' the optimum is the last yielded model, so actionlist.py uses models[-1]. the original used models[0], the first and worst model. this local fix overlaps with an announced official toolkit update for optimized programs, reconcile when it lands
- stops are built manually in v3. the v4 waypoint format 'waypoint(z, ord, (x,y), dir, arr, dep)' has been announced for the course toolkit and is subject to change, our station representation mirrors its fields (order, location, direction, time window) to ease a later migration
- adjustable values sit on top of files as '#const' so they are easy to tune

## open points and future work

- transfer waiting time: following our supervisor's guidance, six minutes is treated as the optimal transfer waiting time, and deviation in either direction is penalized. the current cost layer minimizes waiting toward zero. a follow up is to penalize the deviation from the optimum instead, for example deviation = |wait - opt_wait| with '#const opt_wait' on top
- crowding as a criterion is not modelled yet
- animation with optimized programs works via our local actionlist.py fix (models[-1]). when the official toolkit update for optimized programs is released, compare and reconcile

## related work and how we position ourselves

our approach builds on established techniques from the literature. main references:

- p. vansteenwegen and d. van oudheusden, 'decreasing the passenger waiting time for an intercity rail network', transportation research part b 41 (2007). recommended by our supervisor. minimizes a weighted waiting cost function on the belgian intercity network, closest published relative of our cost function idea
- j. goetsch and i. seidl, 'prioritization', university of potsdam student report. same asp machinery we reuse: '#minimize', weights, the times 1000 integer trick for ratios, and the lesson that weighted sums beat strict priorities
- g. brewka, j. delgrande, j. romero and t. schaub, 'asprin: customizing answer set preferences without a headache', aaai 2015. javier romero's work on preference handling in asp is the general framework our hand built weighted approach relates to, check his further papers on preferences for the report
- our literature research focuses on publications from 2022 onwards where possible, in line with the course guidance. older foundational works are included where they are directly relevant to our approach. we search google scholar (including the scholar labs feature) by combining our topic, passenger waiting times and ride convenience, with the coordinating fields of the course: multi agent pathfinding (mapf), logic programming, linear programming and milp, boolean satisfiability (sat), and constraint programming. the railway-research repository, in particular the future work sections of previous student projects, serves as an additional starting point

## acknowledgements

we thank r. kepler james murphy for the supervision and guidance throughout this project, in particular for helping us refine our concept, the literature recommendations and the toolkit support.
