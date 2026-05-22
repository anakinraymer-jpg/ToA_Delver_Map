from __future__ import annotations

from collections import deque
from typing import Optional


def find_next_step(grid, start: int, goal: int) -> Optional[int]:
    """
    BFS shortest-path on the hex graph.

    Returns the *first* node on the shortest path from *start* toward *goal*,
    or None if start == goal or no path exists.
    """
    if start == goal:
        return None

    visited: set[int] = {start}
    # Queue entries: (current_node, first_step_from_start)
    q: deque[tuple[int, int]] = deque()

    for nb in grid.neighbor_numbers(start):
        if nb == goal:
            return nb
        if nb not in visited:
            visited.add(nb)
            q.append((nb, nb))

    while q:
        node, first = q.popleft()
        for nb in grid.neighbor_numbers(node):
            if nb == goal:
                return first
            if nb not in visited:
                visited.add(nb)
                q.append((nb, first))

    return None  # no path found (disconnected grid — shouldn't happen normally)
