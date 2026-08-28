
from flatland.envs.timetable_utils import Line

class EvaluationLineGenerator:
    def __init__(self, positions, directions, targets, speeds):
        self.positions = list(positions)
        self.directions = list(directions)
        self.targets = list(targets)
        self.speeds = list(speeds)

    def __call__(self, rail, num_agents, hints=None, num_resets=0, np_random=None):
        if num_agents != len(self.positions):
            raise ValueError(
                "Expected {} agents, got {}.".format(
                    len(self.positions), num_agents
                )
            )
        return Line(
            agent_positions=self.positions,
            agent_directions=self.directions,
            agent_targets=self.targets,
            agent_speeds=self.speeds,
        )
