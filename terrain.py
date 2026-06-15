from __future__ import annotations

from typing import Optional

# -----------------------------------------------------------------------
# Terrain catalogue
# -----------------------------------------------------------------------

TERRAINS: list[str] = [
    "Jungle",
    "Beach",
    "Mountains",
    "Rivers",
    "Swamp",
    "Wasteland",
    "Grassland",
    "Ocean",
    "Structure",
    "Cave",
]

# Terrain types that suppress the Druid wild bonus on the character sheet
INDOOR_TERRAINS: frozenset[str] = frozenset({"Structure", "Cave"})

# Hex fill colour for each terrain
TERRAIN_COLORS: dict[str, str] = {
    "Jungle":    "#1a5e1a",   # deep forest green
    "Beach":     "#c8a832",   # sandy gold
    "Mountains": "#706868",   # slate grey
    "Rivers":    "#2a7dd4",   # medium blue
    "Swamp":     "#3e5220",   # murky olive
    "Wasteland": "#9c6b3a",   # dusty brown
    "Grassland": "#3db53d",   # bright meadow green
    "Ocean":     "#1a3f8c",   # deep navy
    "Structure": "#b0886a",   # warm sandstone
    "Cave":      "#4a3a52",   # dark purple-grey
}

# Alpha (0–255) applied to the fill — higher = more opaque
TERRAIN_ALPHA: dict[str, int] = {
    "Jungle":    145,
    "Beach":     120,
    "Mountains": 145,
    "Rivers":    155,
    "Swamp":     150,
    "Wasteland": 135,
    "Grassland": 115,
    "Ocean":     165,
    "Structure": 160,
    "Cave":      170,
}

# 3-letter abbreviation shown as a subtle watermark inside each painted hex
TERRAIN_ABBR: dict[str, str] = {
    "Jungle":    "JNG",
    "Beach":     "BCH",
    "Mountains": "MTN",
    "Rivers":    "RVR",
    "Swamp":     "SWP",
    "Wasteland": "WLD",
    "Grassland": "GRS",
    "Ocean":     "OCN",
    "Structure": "STR",
    "Cave":      "CAV",
}


# -----------------------------------------------------------------------
# Storage
# -----------------------------------------------------------------------

class TerrainMap:
    """Maps hex node numbers to terrain type names."""

    def __init__(self):
        self._data: dict[int, str] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def set(self, node: int, terrain: str) -> None:
        if terrain in TERRAINS:
            self._data[node] = terrain

    def clear(self, node: int) -> None:
        self._data.pop(node, None)

    def clear_all(self) -> None:
        self._data.clear()

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, node: int) -> Optional[str]:
        return self._data.get(node)

    @property
    def count(self) -> int:
        return len(self._data)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {str(k): v for k, v in self._data.items()}

    @classmethod
    def from_dict(cls, data: dict) -> TerrainMap:
        tm = cls()
        for k, v in data.items():
            if v in TERRAINS:
                try:
                    tm._data[int(k)] = v
                except ValueError:
                    pass
        return tm
