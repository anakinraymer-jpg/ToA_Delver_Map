import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class HexCell:
    q: int
    r: int
    number: int


class HexGrid:
    """
    Axial-coordinate hex grid overlaid on a pixel canvas.
    orientation: 'flat' (flat-top) or 'pointy' (pointy-top)
    size:        hex radius in pixels (center to corner)
    origin:      pixel (x, y) of hex (q=0, r=0)
    """

    def __init__(
        self,
        size: float = 40.0,
        origin: tuple[float, float] = (0.0, 0.0),
        orientation: str = "flat",
        cols: int = 20,
        rows: int = 15,
    ):
        self.size = size
        self.origin = origin
        self.orientation = orientation
        self.cols = cols
        self.rows = rows
        self._cells: dict[tuple[int, int], HexCell] = {}
        self._num_to_coord: dict[int, tuple[int, int]] = {}
        self._rebuild()

    # ------------------------------------------------------------------
    # Grid construction
    # ------------------------------------------------------------------

    def _rebuild(self):
        self._cells.clear()
        self._num_to_coord.clear()
        n = 1
        if self.orientation == "flat":
            for col in range(self.cols):
                r_offset = -(col // 2)
                for row in range(self.rows):
                    q, r = col, row + r_offset
                    self._cells[(q, r)] = HexCell(q, r, n)
                    self._num_to_coord[n] = (q, r)
                    n += 1
        else:  # pointy
            for row in range(self.rows):
                q_offset = -(row // 2)
                for col in range(self.cols):
                    q, r = col + q_offset, row
                    self._cells[(q, r)] = HexCell(q, r, n)
                    self._num_to_coord[n] = (q, r)
                    n += 1

    def reconfigure(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self._rebuild()

    # ------------------------------------------------------------------
    # Coordinate conversion
    # ------------------------------------------------------------------

    def hex_to_pixel(self, q: int, r: int) -> tuple[float, float]:
        ox, oy = self.origin
        s = self.size
        if self.orientation == "flat":
            x = s * 1.5 * q + ox
            y = s * (math.sqrt(3) * r + math.sqrt(3) / 2 * q) + oy
        else:
            x = s * (math.sqrt(3) * q + math.sqrt(3) / 2 * r) + ox
            y = s * 1.5 * r + oy
        return x, y

    def pixel_to_nearest(self, px: float, py: float) -> Optional[tuple[int, int]]:
        ox, oy = self.origin
        px -= ox
        py -= oy
        s = self.size
        if self.orientation == "flat":
            q = (2 / 3 * px) / s
            r = (-1 / 3 * px + math.sqrt(3) / 3 * py) / s
        else:
            q = (math.sqrt(3) / 3 * px - 1 / 3 * py) / s
            r = (2 / 3 * py) / s
        coord = self._cube_round(q, r)
        return coord if coord in self._cells else None

    @staticmethod
    def _cube_round(fq: float, fr: float) -> tuple[int, int]:
        fs = -fq - fr
        q, r, s = round(fq), round(fr), round(fs)
        dq, dr, ds = abs(q - fq), abs(r - fr), abs(s - fs)
        if dq > dr and dq > ds:
            q = -r - s
        elif dr > ds:
            r = -q - s
        return q, r

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def corners(self, q: int, r: int) -> list[tuple[float, float]]:
        cx, cy = self.hex_to_pixel(q, r)
        angle_offset = 0 if self.orientation == "flat" else 30
        return [
            (
                cx + self.size * math.cos(math.radians(60 * i + angle_offset)),
                cy + self.size * math.sin(math.radians(60 * i + angle_offset)),
            )
            for i in range(6)
        ]

    def neighbors(self, q: int, r: int) -> list[tuple[int, int]]:
        dirs = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)]
        return [(q + dq, r + dr) for dq, dr in dirs if (q + dq, r + dr) in self._cells]

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def are_adjacent(self, n1: int, n2: int) -> bool:
        c1 = self._num_to_coord.get(n1)
        c2 = self._num_to_coord.get(n2)
        if not c1 or not c2:
            return False
        return c2 in self.neighbors(*c1)

    def cell(self, q: int, r: int) -> Optional[HexCell]:
        return self._cells.get((q, r))

    def cell_by_number(self, n: int) -> Optional[HexCell]:
        coord = self._num_to_coord.get(n)
        return self._cells.get(coord) if coord else None

    def pixel_of(self, n: int) -> Optional[tuple[float, float]]:
        coord = self._num_to_coord.get(n)
        return self.hex_to_pixel(*coord) if coord else None

    def neighbor_numbers(self, n: int) -> list[int]:
        coord = self._num_to_coord.get(n)
        if not coord:
            return []
        return [self._cells[c].number for c in self.neighbors(*coord)]

    @property
    def all_cells(self) -> list[HexCell]:
        return sorted(self._cells.values(), key=lambda c: c.number)

    @property
    def max_number(self) -> int:
        return len(self._cells)
