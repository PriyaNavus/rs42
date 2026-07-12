# report notes - rs42 (not part of the code documentation)

material for the written report, moved out of the readme. working notes, not polished prose.

## related work and positioning

our approach builds on established techniques from the literature. main references:

- p. vansteenwegen and d. van oudheusden, 'decreasing the passenger waiting time for an intercity rail network', transportation research part b 41 (2007). recommended by our supervisor. minimizes a weighted waiting cost function on the belgian intercity network, closest published relative of our cost function idea
- j. goetsch and i. seidl, 'prioritization', university of potsdam student report. same asp machinery we reuse: '#minimize', weights, the times 1000 integer trick for ratios, and the lesson that weighted sums beat strict priorities
- g. brewka, j. delgrande, j. romero and t. schaub, 'asprin: customizing answer set preferences without a headache', aaai 2015. javier romero's work on preference handling in asp is the general framework our hand built weighted approach relates to, check his further papers on preferences for the report

## literature search strategy

our literature research focuses on publications from 2022 onwards where possible, in line with the course guidance. older foundational works are included where they are directly relevant to our approach. we search google scholar (including the scholar labs feature) by combining our topic, passenger waiting times and ride convenience, with the coordinating fields of the course: multi agent pathfinding (mapf), logic programming, linear programming and milp, boolean satisfiability (sat), and constraint programming. the railway-research repository, in particular the future work sections of previous student projects, serves as an additional starting point.

## open points for the report / future work

- transfer waiting time: following our supervisor's guidance, six minutes is treated as the optimal transfer waiting time, and deviation in either direction is penalized. the current cost layer minimizes waiting toward zero. follow up: penalize deviation = |wait - opt_wait| with '#const opt_wait' on top
- crowding as a criterion is not modelled yet
- the local actionlist.py fix (models[-1]) overlaps with an announced official toolkit update for optimized programs, reconcile when it lands
- the manual v3 station representation mirrors the announced v4 waypoint format 'waypoint(z, ord, (x,y), dir, arr, dep)' (order, location, direction, time window) to ease a later migration

## acknowledgements (for the report)

we thank r. kepler james murphy for the supervision and guidance throughout this project, in particular for helping us refine our concept, the literature recommendations and the toolkit support.
