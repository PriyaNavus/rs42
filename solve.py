# standard packages
import warnings
import os 
import time
import pickle
import json
import csv  # RS42_STEP1_BACKEND_VALIDATION
from pathlib import Path
from argparse import ArgumentParser, Namespace

# custom modules
from asp import params
from modules.api import FlatlandPlan, FlatlandReplan
from modules.convert import convert_malfunctions_to_clingo, convert_formers_to_clingo, convert_futures_to_clingo

# clingo
import clingo
from clingo.application import Application, clingo_main

# rendering visualizations
from flatland.utils.rendertools import RenderTool
import imageio.v2 as imageio
from PIL import Image, ImageDraw, ImageFont


class MalfunctionManager():
    def __init__(self, num_agents):
        self.num_agents = num_agents
        self.malfunctions = []

    def get(self) -> list:
        """ get the list of malfunctions """
        return(self.malfunctions)

    def deduct(self) -> None:
        """ decrease the duration of each malfunction by one and delete expired malfunctions """
        malfunctions_to_remove = []
        for i, malf in enumerate(self.malfunctions):
            self.malfunctions[i] = (self.malfunctions[i][0], self.malfunctions[i][1] - 1)
            if self.malfunctions[i][1] == 0:
                malfunctions_to_remove.append(i)
        
        # delete expired malfunctions
        for i in sorted(malfunctions_to_remove, reverse=True):
            del self.malfunctions[i]

    def check(self, info) -> set:
        """ check current state of the env for new malfunctions """
        malfunctioning_info = info['malfunction']
        malfunctioning_trains = {train for train, duration in malfunctioning_info.items() if duration > 0}
        existing = {malf[0] for malf in self.malfunctions}
        new = malfunctioning_trains.difference(existing)

        # add new ones to malfunctions
        for train in new:
            self.malfunctions.append((train, malfunctioning_info[train]))

        return(new)


class SimulationManager():
    def __init__(self,env,primary,secondary=None):
        self.env = env
        self.primary = primary
        self.plan_symbols = None
        if secondary is None:
            self.secondary = primary 
        else:
            self.secondary = secondary

    def build_actions(self) -> list:
        """ create initial list of actions """
        # pass env, primary
        app = FlatlandPlan(self.env, None)
        clingo_main(app, self.primary)
        self.plan_symbols = app.model_symbols
        return(app.action_list)

    def provide_context(self, actions, timestep, malfunctions) -> str:
        """ provide additional facts when updating list """
        # actions that have already been executed
        # wait actions that are enforced because of malfunctions
        # future actions that were previously planned
        past = convert_formers_to_clingo(actions[:timestep])
        present = convert_malfunctions_to_clingo(malfunctions, timestep)
        future = convert_futures_to_clingo(actions[timestep:])
        return(past + present + future)

    def update_actions(self, context) -> list:
        """ update list of actions following malfunction """
        # pass env, secondary, context
        app = FlatlandPlan(self.env, context)
        clingo_main(app, self.primary)
        self.plan_symbols = app.model_symbols
        return(app.action_list)


class OutputLogManager():
    def __init__(self) -> None:
        self.logs = []

    def add(self,info) -> None:
        """ add info from a timestep to the log """
        self.logs.append(info)

    def save(self,filename) -> None:
        """ save output log to local drive """
        #with open(f"output/{filename}/paths.json", "w") as f:
        #    f.write(json.dumps(self.logs))
        with open(f"output/{filename}/paths.csv", "w") as f:
            f.write("agent;timestep;position;direction;status;given_command\n")
            for log in self.logs:
                f.write(log)

# RS42_STEP1_BACKEND_VALIDATION
def extract_planned_positions(symbols):
    """Return {(agent_id, timestep): (row, col)} from ASP pos/5 atoms."""
    planned = {}
    if not symbols:
        return planned

    for atom in symbols:
        try:
            if atom.name != "pos" or len(atom.arguments) != 5:
                continue
            agent_id = atom.arguments[0].number
            row = atom.arguments[1].number
            col = atom.arguments[2].number
            timestep = atom.arguments[4].number
        except (AttributeError, RuntimeError):
            continue

        planned[(agent_id, timestep)] = (row, col)

    return planned


def effective_flatland_position(agent, agent_done):
    """Return the Flatland position used for comparison with the ASP plan."""
    if agent.position is not None:
        return tuple(agent.position)

    # Flatland can remove a completed train from the map. ASP keeps a
    # completed train anchored at its target.
    if agent_done and agent.target is not None:
        return tuple(agent.target)

    return None


def add_validation_rows(rows, env, done, planned_positions, action_timestep):
    """
    action(..., T) advances Flatland from state T to state T+1.
    Compare the post-step Flatland state with ASP pos(..., T+1).
    """
    state_timestep = action_timestep + 1

    for agent_id, agent in enumerate(env.agents):
        planned = planned_positions.get((agent_id, state_timestep))
        agent_done = bool(done.get(agent_id, False))
        actual = effective_flatland_position(agent, agent_done)

        # Before spawning, the ASP encoding intentionally has no pos/5 atom.
        if planned is None:
            match = None
            status = "no_asp_position"
        else:
            match = planned == actual
            status = "match" if match else "diverged"

        rows.append({
            "agent": agent_id,
            "action_timestep": action_timestep,
            "state_timestep": state_timestep,
            "planned_position": planned,
            "actual_position": actual,
            "flatland_done": agent_done,
            "match": match,
            "status": status,
        })


def save_validation(output_dir, rows, done):
    output_dir = Path(output_dir)

    fields = [
        "agent",
        "action_timestep",
        "state_timestep",
        "planned_position",
        "actual_position",
        "flatland_done",
        "match",
        "status",
    ]

    with (output_dir / "validation.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    divergences = [row for row in rows if row["match"] is False]
    all_trains_done = bool(done.get("__all__", False))

    summary = {
        "success": all_trains_done and not divergences,
        "all_trains_done": all_trains_done,
        "divergence_count": len(divergences),
        "first_divergence": divergences[0] if divergences else None,
    }

    with (output_dir / "validation.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary

def check_params(par):
    """
    verify that all parameters exist before proceedingd
    """
    required_params = {
        "primary": list
        #"secondary": list
    }

    # check that all required parameters exist and have the correct type
    for param, expected_type in required_params.items():
        if not hasattr(par, param):
            raise ValueError(f"Required parameter '{param}' is missing from the params module")
            
        else:
            # check for correct types
            value = getattr(par, param)
        
            if not isinstance(value, expected_type):
                raise TypeError(f"Parameter '{param}' should be of type {expected_type.__name__}, but got {type(value).__name__}")

    return True


def get_args():
    """ capture command line inputs """
    parser = ArgumentParser()
    parser.add_argument('env', type=str, default='', nargs=1, help='the Flatland environment as a .pkl file')
    parser.add_argument('--no-render', action='store_true', help='if included, run the Flatland simulation but do not render a GIF')
    return(parser.parse_args())


def main():
    # dev test main
    if check_params(params):
        args: Namespace = get_args()
        env = pickle.load(open(args.env[0], "rb"))
        no_render = args.no_render

    # create manager objects
    mal = MalfunctionManager(env.get_num_agents())
    # RS42_STEP2A_SCENARIO_V3
    scenario_path = Path("asp/scenarios") / f"{Path(args.env[0]).stem}.lp"
    if not scenario_path.exists():
        raise FileNotFoundError(f"Missing RS42 scenario file: {scenario_path}")
    primary = list(params.primary) + [str(scenario_path)]
    sim = SimulationManager(env, primary, params.secondary)
    log = OutputLogManager()

    # envrionment rendering
    env_renderer = None
    if not no_render:
        env_renderer = RenderTool(env, gl="PILSVG")
        env_renderer.reset()
        images = []

    # create directory
    os.makedirs("tmp/frames", exist_ok=True)
    action_map = {1:'move_left',2:'move_forward',3:'move_right',4:'wait'}
    state_map = {0:'waiting', 1:'ready to depart', 2:'malfunction (off map)', 3:'moving', 4:'stopped', 5:'malfunction (on map)', 6:'done'}
    dir_map = {0:'n', 1:'e', 2:'s', 3:'w'}

    try:
        actions = sim.build_actions()
    except RuntimeError as exc:
        print(f"RS42_SOLVER: UNSAT/FAILED - {exc}")
        return 3
    planned_positions = extract_planned_positions(sim.plan_symbols)
    validation_rows = []
    last_done = {i: False for i in range(env.get_num_agents())}
    last_done["__all__"] = False

    timestep = 0
    while len(actions) > timestep:
        # add to the log
        for a in actions[timestep]:
            log.add(f'{a};{timestep};{env.agents[a].position};{dir_map[env.agents[a].direction]};{state_map[env.agents[a].state]};{action_map[actions[timestep][a]]}\n')

        _, _, done, info = env.step(actions[timestep])
        last_done = done
        add_validation_rows(
            validation_rows,
            env,
            done,
            planned_positions,
            timestep,
        )

        # end if simulation is finished
        if done['__all__'] and timestep < len(actions)-1:
            warnings.warn('Simulation has reached its end before actions list has been exhausted.')
            break

        # check for new malfunctions
        new_malfs = mal.check(info)

        if len(new_malfs) > 0:
            context = sim.provide_context(actions, timestep, mal.get())
            actions = sim.update_actions(context)
            planned_positions = extract_planned_positions(sim.plan_symbols)

        mal.deduct() #??? where in the loop should this go - before context?
        
        # render an image
        filename = 'tmp/frames/flatland_frame_{:04d}.png'.format(timestep)
        if env_renderer is not None:
            env_renderer.render_env(show=True, show_observations=False, show_predictions=False)
            env_renderer.gl.save_image(filename)
            env_renderer.reset()

            # add red numbers in the corner
            with Image.open(filename) as img:
                draw = ImageDraw.Draw(img)
                padding = 10
                font_size = int(min(img.width, img.height) * 0.10)
                try:
                    font = ImageFont.truetype("modules/LiberationMono-Regular.ttf", font_size)
                except IOError:
                    font = ImageFont.load_default()
                
                # prepare text
                text = f"{timestep}"
                size = font.getbbox(text)
                text_width = size[2]-size[0]
                text_position = (img.width - text_width - padding, padding)
                
                # draw text borders
                x, y = text_position
                border_color = "black"
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
                    draw.text((x + dx, y + dy), text, fill=border_color, font=font)
                
                # draw text
                draw.text(text_position, text, fill="red", font=font)
                img.save(filename)

            images.append(imageio.imread(filename))
        # images.append(imageio.imread(filename))

        timestep = timestep + 1

    # get time stamp for gif and output log
    stamp = time.time()
    os.makedirs(f"output/{stamp}", exist_ok=True)
    
    # combine images into gif
    if not no_render:
        imageio.mimsave(f"output/{stamp}/animation.gif", images, format='GIF', loop=0, duration=240)

    # save output log
    log.save(stamp)

    summary = save_validation(Path("output") / str(stamp), validation_rows, last_done)
    if summary["success"]:
        print("RS42_VALIDATION: PASS - ASP plan matched Flatland and all trains reached their targets.")
        return 0
    print("RS42_VALIDATION: FAIL")
    print(json.dumps(summary, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
