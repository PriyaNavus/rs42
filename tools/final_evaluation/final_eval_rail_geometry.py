"""
Reusable deterministic curved-rail helpers for RS42 / Flatland 3.0.15.

Uses RailEnvTransitions.transition_list + rotate_transition rather than
RailEnvTransitionsEnum, which is not exported by the project's Flatland 3.0.15.
"""
from collections import defaultdict
from flatland.core.grid.rail_env_grid import RailEnvTransitions
from flatland.core.transition_map import GridTransitionMap

NORTH, EAST, SOUTH, WEST = 0, 1, 2, 3
DELTA_TO_DIRECTION = {
    (-1, 0): NORTH,
    (0, 1): EAST,
    (1, 0): SOUTH,
    (0, -1): WEST,
}

def direction_between(a, b):
    dr = b[0] - a[0]
    dc = b[1] - a[1]
    try:
        return DELTA_TO_DIRECTION[(dr, dc)]
    except KeyError:
        raise ValueError("Path cells must be Manhattan-adjacent: {} -> {}".format(a, b))

def manhattan_path(waypoints):
    if len(waypoints) < 2:
        raise ValueError("Need at least two waypoints.")
    path = [tuple(waypoints[0])]
    for raw_start, raw_end in zip(waypoints[:-1], waypoints[1:]):
        start = tuple(raw_start)
        end = tuple(raw_end)
        if start[0] != end[0] and start[1] != end[1]:
            raise ValueError("Each segment must be horizontal or vertical: {} -> {}".format(start, end))
        r, c = start
        target_r, target_c = end
        dr = 0 if r == target_r else (1 if target_r > r else -1)
        dc = 0 if c == target_c else (1 if target_c > c else -1)
        while (r, c) != (target_r, target_c):
            r += dr
            c += dc
            cell = (r, c)
            if path[-1] != cell:
                path.append(cell)
    if len(set(path)) != len(path):
        raise ValueError("A route may not self-intersect.")
    return path

def route_steps(path, origin, destination):
    i = path.index(tuple(origin))
    j = path.index(tuple(destination))
    if j <= i:
        raise ValueError("Destination must occur after origin.")
    return j - i

def route_turns(path, origin, destination):
    i = path.index(tuple(origin))
    j = path.index(tuple(destination))
    directions = [direction_between(path[k], path[k + 1]) for k in range(i, j)]
    return sum(1 for a, b in zip(directions[:-1], directions[1:]) if a != b)

def initial_direction(path, origin):
    i = path.index(tuple(origin))
    if i >= len(path) - 1:
        raise ValueError("Origin cannot be the final path cell.")
    return direction_between(path[i], path[i + 1])

def _transition_catalog(transitions):
    cells = transitions.transition_list
    vertical_straight = cells[1]
    horizontal_straight = transitions.rotate_transition(vertical_straight, 90)
    dead_end_from_south = cells[7]
    right_turn_from_south = cells[8]
    dead_end_from_west = transitions.rotate_transition(dead_end_from_south, 90)
    dead_end_from_north = transitions.rotate_transition(dead_end_from_south, 180)
    dead_end_from_east = transitions.rotate_transition(dead_end_from_south, 270)
    right_turn_from_west = transitions.rotate_transition(right_turn_from_south, 90)
    right_turn_from_north = transitions.rotate_transition(right_turn_from_south, 180)
    right_turn_from_east = transitions.rotate_transition(right_turn_from_south, 270)
    dead_end_by_connection = {
        NORTH: dead_end_from_north,
        EAST: dead_end_from_east,
        SOUTH: dead_end_from_south,
        WEST: dead_end_from_west,
    }
    pair_transition = {
        frozenset((NORTH, SOUTH)): vertical_straight,
        frozenset((EAST, WEST)): horizontal_straight,
        frozenset((SOUTH, EAST)): right_turn_from_south,
        frozenset((WEST, SOUTH)): right_turn_from_west,
        frozenset((NORTH, WEST)): right_turn_from_north,
        frozenset((EAST, NORTH)): right_turn_from_east,
    }
    return dead_end_by_connection, pair_transition

def build_disjoint_rail(width, height, paths):
    transitions = RailEnvTransitions()
    rail = GridTransitionMap(width=width, height=height, transitions=transitions, random_seed=42)
    rail.grid.fill(0)
    dead_end_by_connection, pair_transition = _transition_catalog(transitions)
    adjacency = defaultdict(set)
    owners = {}
    for route_name, path in paths.items():
        for cell in path:
            r, c = cell
            if not (0 <= r < height and 0 <= c < width):
                raise ValueError("{} contains out-of-bounds cell {}".format(route_name, cell))
            previous_owner = owners.get(cell)
            if previous_owner is not None and previous_owner != route_name:
                raise ValueError("Routes overlap physically: {} belongs to {} and {}".format(cell, previous_owner, route_name))
            owners[cell] = route_name
        for a, b in zip(path[:-1], path[1:]):
            direction_between(a, b)
            adjacency[a].add(b)
            adjacency[b].add(a)
    for cell, neighbours in adjacency.items():
        directions = {direction_between(cell, neighbour) for neighbour in neighbours}
        if len(directions) == 1:
            transition = dead_end_by_connection[next(iter(directions))]
        elif len(directions) == 2:
            key = frozenset(directions)
            if key not in pair_transition:
                raise ValueError("Unsupported rail cell {}: {}".format(cell, sorted(directions)))
            transition = pair_transition[key]
        else:
            raise ValueError("This helper supports non-branching routes only. {} has degree {}.".format(cell, len(directions)))
        if not transitions.is_valid(transition):
            raise RuntimeError("Invalid Flatland transition at {}: {}".format(cell, transition))
        rail.grid[cell[0], cell[1]] = transition
    return rail
