# RS42 — Passenger Convenience Planning in Flatland

This repository plans conflict-free train schedules in the [Flatland](https://flatland.aicrowd.com/intro.html) railway simulation using Answer Set Programming (ASP), and extends the planning with a passenger perspective: journeys are scored on convenience criteria (arrival time, waiting, transfers, turns, intermediate stops), each weighted by a user-selected preference profile. The solver then returns the most convenient schedule instead of an arbitrary valid one.

The repository builds on the [krr-up/flatland](https://github.com/krr-up/flatland) toolkit, which bridges Python and clingo: it reads Flatland environments, converts them to logical facts, and replays ASP output as an animated simulation.

## Repository structure

- `asp/custom/` — the RS42 encoding stack (see Encodings below)
- `asp/profiles/` — preference profiles as weight constants; `active_profile.lp` is written by the UI
- `asp/params.py` — controls which encodings the solver loads (`primary` list)
- `ui/` — Streamlit web interface
- `tools/` — helper scripts, e.g. waypoint extraction from Flatland environments
- `envs/` — pre-built environments; `envs/params.py` controls environment generation
- `modules/` — Python–clingo bridge (fact conversion, action list, simulation manager)
- `doc/` — original toolkit documentation
- `output/` — animations and per-step logs (`paths.csv`) from simulation runs
- `build.py` — builds environments from `envs/params.py`
- `solve.py` — solves an environment and renders the resulting schedule as a GIF

## Installation

A conda environment with Python 3.10 is recommended; newer Python versions conflict with Flatland 3 dependencies.

```
conda create -n flatland python=3.10
conda activate flatland
pip install "flatland-rl<4" imageio clingo "importlib_resources>=5,<6"
conda install -c conda-forge streamlit
```

Notes:
- The version pin `flatland-rl<4` matters: the environments in `envs/pkl/` were built with Flatland v3 and cannot be loaded by a v4 installation.
- On macOS, installing Streamlit via conda-forge avoids a pyarrow build error that plain pip can run into.
- `importlib_resources>=5,<6` resolves a `typing.io` import error on recent Python versions.

## Usage

### Web interface

From the repository root:

```
streamlit run ui/app.py
```

The UI lets the user pick a preference profile (fastest, least waiting, fewest transfers, balanced, comfort) or set custom weights with sliders. It writes the chosen weights to `asp/profiles/active_profile.lp`, which is loaded via `asp/params.py`, so the selection reaches the solver. Two modes are available:

- Quick check: runs clingo on the `.lp` environment and reports the optimization value, per-train metrics, and the schedule.
- Full animation: runs `solve.py` on the `.pkl` environment and displays the resulting GIF.

### Creating environments

Adjust `envs/params.py` (grid size, number of agents, speeds, malfunctions), then:

```
python build.py 3
```

Each environment is saved in three formats: `.lp` (clingo facts, for encoding development), `.pkl` (serialized environment, for simulation), and `.png` (visual reference). For this project, all trains run at full speed and malfunctions are disabled.

### Running the solver directly

For encoding development, clingo can be called on the `.lp` environment:

```
clingo envs/lp/env_001--2_4.lp asp/custom/connection.lp asp/custom/encoding.lp asp/custom/generated_waypoints.lp asp/custom/waypoint.lp asp/custom/passenger_transfer.lp asp/custom/visual.lp asp/profiles/active_profile.lp
```

For the full simulation, set the `primary` list in `asp/params.py` to the encodings above, then:

```
python solve.py envs/pkl/env_001--2_4.pkl
```

The required output format is `action(train(ID), Action, Time).` where `Action` is one of `move_forward`, `move_left`, `move_right`, `wait`. The animation and a per-step log (`paths.csv`) are saved to `output/`.

## Encodings

- `connection.lp` — builds the track graph from environment facts
- `encoding.lp` — route choice and action output
- `generated_waypoints.lp` — auto-extracted waypoints per train
- `waypoint.lp` — stations, required visits, visit order
- `passenger_transfer.lp` — passenger itineraries and transfer validation
- `visual.lp` — the cost layer: each convenience criterion is computed per train, multiplied by its profile weight, and minimized

Three conventions are essential for the plan to match the Flatland replay:

1. **Spawn timing.** A train with start time N is off the map until N+2. The encoding emits forced `wait` actions for `0..N`, the spawning `move_forward` at N+1, and places the train on its start cell at N+2.
2. **Steering labels.** Flatland interprets `move_left`/`move_right` relative to the direction the train currently faces. The encoding chooses the route internally (`steer/3`) and derives the action labels from consecutive movement directions afterwards; deriving them from edge letters directly emits turns one step early, which Flatland ignores at switches.
3. **Model selection.** With `#minimize`, the optimum is the last model clingo yields. `modules/actionlist.py` therefore executes `models[-1]`.

## Troubleshooting

- **Trains deviate from the plan or deadlock:** check `output/<run>/paths.csv`. Each row logs a train's position, state, and the command it received, which makes it possible to align plan and execution step by step. Deviations usually point to one of the three conventions above.
- **`ModuleNotFoundError` when running `solve.py`:** a Flatland dependency is missing or the installed Flatland major version does not match the `.pkl` environments (see Installation).
- **Unsatisfiable:** the environment has no valid schedule under the current constraints; try regenerating the environment or checking the deadlines in the `.lp` facts.
- **The simulation runs out of time steps:** typically caused by agents not being removed at their targets and blocking each other; check `remove_agents_at_target` in `envs/params.py`.

## Working example

```
conda activate flatland
streamlit run ui/app.py
```

Select the `balanced` profile, the environment `env_001--2_4`, mode "full animation", and press solve. The resulting GIF shows one train briefly taking a passing loop to let the other pass — the schedule the optimizer selected under the balanced weights.
