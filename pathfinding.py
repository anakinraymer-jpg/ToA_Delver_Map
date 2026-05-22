from __future__ import annotations

from collections import deque
from typing import Optional


def find_next_step(
    grid,
    start: int,
    goal: int,
    *,
    blocked: Optional[set[int]] = None,
) -> Optional[int]:
    """
    BFS shortest-path on the hex graph.

    Returns the *first* node on the shortest path from *start* toward *goal*,
    or None if start == goal or no path exists (including when the goal or all
    intermediate routes are in the *blocked* set).

    Parameters
    ----------
    blocked : set of node numbers that cannot be entered (e.g. water tiles for
              a non-seafaring entity).  The start node is never blocked.
              If *goal* itself is blocked the function returns None immediately.
    """
    if start == goal:
        return None

    _blocked: set[int] = blocked if blocked is not None else set()

    # If the destination is impassable there is no valid path.
    if goal in _blocked:
        return None

    visited: set[int] = {start}
    # Queue entries: (current_node, first_step_from_start)
    q: deque[tuple[int, int]] = deque()

    for nb in grid.neighbor_numbers(start):
        if nb in _blocked:
            continue
        if nb == goal:
            return nb
        if nb not in visited:
            visited.add(nb)
            q.append((nb, nb))

    while q:
        node, first = q.popleft()
        for nb in grid.neighbor_numbers(node):
            if nb in _blocked:
                continue
            if nb == goal:
                return first
            if nb not in visited:
                visited.add(nb)
                q.append((nb, first))

    return None  # no path found
