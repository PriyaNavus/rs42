import pickle
import sys
from flatland.envs.rail_env_shortest_paths import get_shortest_paths

env_path = sys.argv[1]
out_path = sys.argv[2]

with open(env_path, "rb") as f:
    env = pickle.load(f)

paths = get_shortest_paths(env.distance_map, max_depth=100)

with open(out_path, "w") as f:
    f.write("% Auto-generated Flatland waypoints\n")

    for agent_id, path in paths.items():
        if path is None:
            continue

        for i, waypoint in enumerate(path):
            if waypoint.position is None:
                continue

            x, y = waypoint.position
            f.write(f"flatland_waypoint({agent_id}, wp{i}, {x}, {y}).\n")