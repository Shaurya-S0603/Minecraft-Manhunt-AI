from __future__ import annotations

from heapq import heappop, heappush
from typing import List, Optional, Sequence, Set, Tuple, Union

Coord = Tuple[int, int]


def manhattan(a: Coord, b: Coord) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _normalize_grid(grid: Sequence[Sequence[Union[int, bool, str]]]) -> List[List[bool]]:
    normalized: List[List[bool]] = []
    for row in grid:
        normalized_row: List[bool] = []
        for cell in row:
            if isinstance(cell, str):
                value = cell.strip().lower()
                normalized_row.append(value not in {"0", "false", "blocked", "wall", "obstacle", "water", "lava"})
            else:
                normalized_row.append(bool(cell))
        normalized.append(normalized_row)
    return normalized


class AStarPlanner:
    def __init__(self, grid: Optional[Sequence[Sequence[Union[int, bool, str]]]] = None):
        self.grid = _normalize_grid(grid) if grid is not None else []

    def find_path(
        self,
        start: Coord,
        goal: Coord,
        *,
        blocked: Optional[Set[Coord]] = None,
        allow_diagonal: bool = False,
        max_steps: int = 5000,
    ) -> List[Coord]:
        if not self.grid:
            raise ValueError("Grid is empty; provide a traversable map before planning.")
        return astar(self.grid, start, goal, blocked=blocked, allow_diagonal=allow_diagonal, max_steps=max_steps)


def astar(
    grid: Sequence[Sequence[Union[int, bool, str]]],
    start: Coord,
    goal: Coord,
    *,
    blocked: Optional[Set[Coord]] = None,
    allow_diagonal: bool = False,
    max_steps: int = 5000,
) -> List[Coord]:
    normalized = _normalize_grid(grid)
    rows = len(normalized)
    cols = len(normalized[0]) if rows else 0
    blocked = blocked or set()
    start = (int(start[0]), int(start[1]))
    goal = (int(goal[0]), int(goal[1]))

    if not (0 <= start[0] < rows and 0 <= start[1] < cols):
        raise ValueError("Start is outside the grid scope")
    if not (0 <= goal[0] < rows and 0 <= goal[1] < cols):
        raise ValueError("Goal is outside the grid scope")
    if start in blocked or not normalized[start[0]][start[1]]:
        raise ValueError("Start is blocked")
    if goal in blocked or not normalized[goal[0]][goal[1]]:
        raise ValueError("Goal is blocked")
    if start == goal:
        return [start]

    open_heap: List[Tuple[int, int, Coord]] = [(manhattan(start, goal), 0, start)]
    came_from: dict[Coord, Optional[Coord]] = {start: None}
    g_score: dict[Coord, int] = {start: 0}

    steps = 0
    while open_heap and steps < max_steps:
        _, _, current = heappop(open_heap)
        if current == goal:
            path: List[Coord] = []
            cursor: Optional[Coord] = current
            while cursor is not None:
                path.append(cursor)
                cursor = came_from[cursor]
            return list(reversed(path))

        directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        if allow_diagonal:
            directions += [(1, 1), (1, -1), (-1, 1), (-1, -1)]

        for dx, dy in directions:
            neighbor = (current[0] + dx, current[1] + dy)
            if not (0 <= neighbor[0] < rows and 0 <= neighbor[1] < cols):
                continue
            if neighbor in blocked or not normalized[neighbor[0]][neighbor[1]]:
                continue
            tentative = g_score[current] + (1 if dx == 0 or dy == 0 else 2)
            if tentative < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                heappush(open_heap, (tentative + manhattan(neighbor, goal), tentative, neighbor))
        steps += 1

    raise ValueError("No path found")


a_star = astar
find_path = astar
