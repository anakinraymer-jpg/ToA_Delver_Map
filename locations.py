from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

# Recognised location structure types (empty string = untyped / plain location)
LOCATION_TYPES: list[str] = ["Structure", "Outdoor Structure", "Cave"]


@dataclass
class Location:
    name: str
    node: int
    color: str = "#f39c12"          # amber default
    description: str = ""
    location_type: str = ""         # one of LOCATION_TYPES or "" for untyped
    curse_level: str = ""           # "Lesser Curse", "Greater Curse", or ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


class LocationManager:
    def __init__(self):
        self._locs: dict[str, Location] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, loc: Location) -> None:
        self._locs[loc.id] = loc

    def remove(self, lid: str) -> None:
        self._locs.pop(lid, None)

    def update(self, lid: str, **kwargs) -> None:
        loc = self._locs.get(lid)
        if loc:
            for k, v in kwargs.items():
                setattr(loc, k, v)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, lid: str) -> Optional[Location]:
        return self._locs.get(lid)

    def at_node(self, node: int) -> list[Location]:
        return [l for l in self._locs.values() if l.node == node]

    @property
    def all(self) -> list[Location]:
        return sorted(self._locs.values(), key=lambda l: (l.node, l.name))

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_list(self) -> list[dict]:
        return [
            {
                "id": l.id,
                "name": l.name,
                "node": l.node,
                "color": l.color,
                "description": l.description,
                "location_type": l.location_type,
                "curse_level": l.curse_level,
            }
            for l in self.all
        ]

    @classmethod
    def from_list(cls, data: list[dict]) -> LocationManager:
        lm = cls()
        for d in data:
            lm.add(Location(
                name=d["name"],
                node=d["node"],
                color=d.get("color", "#f39c12"),
                description=d.get("description", ""),
                location_type=d.get("location_type", ""),
                curse_level=d.get("curse_level", ""),
                id=d["id"],
            ))
        return lm
