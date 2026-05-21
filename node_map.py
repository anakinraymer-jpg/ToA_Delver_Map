from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class MapNode:
    number: int
    x: float        # scene-pixel position
    y: float
    name: str = ""


class NodeMap:
    """
    A collection of manually placed movement nodes.
    Two nodes are adjacent when their pixel distance <= adj_distance.
    Neighbour lookups are cached and invalidated on any mutation.
    """

    def __init__(self, adj_distance: float = 200.0):
        self._nodes: dict[int, MapNode] = {}
        self._next_number: int = 1
        self.adj_distance = adj_distance
        self._cache: dict[int, list[int]] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_node(self, x: float, y: float, name: str = "") -> MapNode:
        node = MapNode(number=self._next_number, x=x, y=y, name=name)
        self._nodes[self._next_number] = node
        self._next_number += 1
        self._invalidate()
        return node

    def remove_node(self, number: int):
        self._nodes.pop(number, None)
        self._invalidate()

    def move_node(self, number: int, x: float, y: float):
        node = self._nodes.get(number)
        if node:
            node.x = x
            node.y = y
            self._invalidate()

    def set_adj_distance(self, dist: float):
        self.adj_distance = dist
        self._invalidate()

    def clear(self):
        self._nodes.clear()
        self._next_number = 1
        self._invalidate()

    def _invalidate(self):
        self._cache.clear()

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_node(self, number: int) -> Optional[MapNode]:
        return self._nodes.get(number)

    def nearest_to(self, x: float, y: float, max_dist: float = 30.0) -> Optional[MapNode]:
        best, best_d = None, max_dist
        for node in self._nodes.values():
            d = math.hypot(node.x - x, node.y - y)
            if d < best_d:
                best_d = d
                best = node
        return best

    def neighbors(self, number: int) -> list[int]:
        if number not in self._cache:
            node = self._nodes.get(number)
            if not node:
                self._cache[number] = []
            else:
                self._cache[number] = [
                    n for n, other in self._nodes.items()
                    if n != number
                    and math.hypot(node.x - other.x, node.y - other.y) <= self.adj_distance
                ]
        return self._cache[number]

    def are_adjacent(self, n1: int, n2: int) -> bool:
        return n2 in self.neighbors(n1)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def all_nodes(self) -> list[MapNode]:
        return sorted(self._nodes.values(), key=lambda n: n.number)

    @property
    def count(self) -> int:
        return len(self._nodes)

    @property
    def max_number(self) -> int:
        return max(self._nodes.keys()) if self._nodes else 0

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "adj_distance": self.adj_distance,
            "next_number": self._next_number,
            "nodes": [
                {"number": n.number, "x": n.x, "y": n.y, "name": n.name}
                for n in self.all_nodes
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> NodeMap:
        nm = cls(adj_distance=data.get("adj_distance", 200.0))
        nm._next_number = data.get("next_number", 1)
        for nd in data.get("nodes", []):
            node = MapNode(
                number=nd["number"],
                x=nd["x"],
                y=nd["y"],
                name=nd.get("name", ""),
            )
            nm._nodes[node.number] = node
        return nm
