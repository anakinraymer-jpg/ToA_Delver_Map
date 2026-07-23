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

    Warp mode
    ---------
    Call set_warp_corners(tl, tr, bl, br) with four pixel positions to enable
    bilinear warping.  Every parametric hex position is normalised into [0,1]²
    relative to the parametric bounding box, then bilinearly interpolated to
    the user-defined quad.  Because individual hex-polygon corners are warped
    the same way, the tessellation stays gap-free.

    Call reset_warp() or reconfigure() to return to the parametric grid.
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
        self._warp_corners: Optional[tuple] = None   # (tl, tr, bl, br) or None
        self._warp_bbox: Optional[tuple] = None      # (min_x, max_x, min_y, max_y)
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
        # Reset warp state whenever the parametric grid changes
        self._warp_corners = None
        self._warp_bbox = None
        self._compute_warp_bbox()

    def reconfigure(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self._rebuild()

    # ------------------------------------------------------------------
    # Warp support
    # ------------------------------------------------------------------

    def _compute_warp_bbox(self):
        """Cache the axis-aligned bounding box of all parametric hex centres."""
        if not self._cells:
            self._warp_bbox = (0.0, 1.0, 0.0, 1.0)
            return
        xs, ys = [], []
        for cell in self._cells.values():
            x, y = self._parametric_hex_to_pixel(cell.q, cell.r)
            xs.append(x)
            ys.append(y)
        self._warp_bbox = (min(xs), max(xs), min(ys), max(ys))

    def _apply_warp(self, cx: float, cy: float) -> tuple[float, float]:
        """Bilinearly map a parametric pixel position into the warp quad."""
        if self._warp_corners is None or self._warp_bbox is None:
            return cx, cy
        min_x, max_x, min_y, max_y = self._warp_bbox
        tl, tr, bl, br = self._warp_corners
        dx = max_x - min_x or 1.0
        dy = max_y - min_y or 1.0
        u = (cx - min_x) / dx
        v = (cy - min_y) / dy
        wx = (1 - u) * (1 - v) * tl[0] + u * (1 - v) * tr[0] \
           + (1 - u) *       v  * bl[0] + u *       v  * br[0]
        wy = (1 - u) * (1 - v) * tl[1] + u * (1 - v) * tr[1] \
           + (1 - u) *       v  * bl[1] + u *       v  * br[1]
        return wx, wy

    def get_warp_corners(self) -> tuple:
        """
        Returns the 4 active warp corners (tl, tr, bl, br).
        If no warp is set, returns the corners of the parametric bbox.
        """
        if self._warp_corners is not None:
            return self._warp_corners
        if self._warp_bbox is None:
            self._compute_warp_bbox()
        min_x, max_x, min_y, max_y = self._warp_bbox
        return (
            (min_x, min_y),
            (max_x, min_y),
            (min_x, max_y),
            (max_x, max_y),
        )

    def set_warp_corners(
        self,
        tl: tuple[float, float],
        tr: tuple[float, float],
        bl: tuple[float, float],
        br: tuple[float, float],
    ):
        """Enable bilinear warp with these four corner control points."""
        if self._warp_bbox is None:
            self._compute_warp_bbox()
        self._warp_corners = (tl, tr, bl, br)

    def reset_warp(self):
        """Disable warp and revert to the parametric grid."""
        self._warp_corners = None

    @property
    def is_warped(self) -> bool:
        return self._warp_corners is not None

    # ------------------------------------------------------------------
    # Coordinate conversion
    # ------------------------------------------------------------------

    def _parametric_hex_to_pixel(self, q: int, r: int) -> tuple[float, float]:
        """Pure parametric calculation — unaffected by warp."""
        ox, oy = self.origin
        s = self.size
        if self.orientation == "flat":
            x = s * 1.5 * q + ox
            y = s * (math.sqrt(3) * r + math.sqrt(3) / 2 * q) + oy
        else:
            x = s * (math.sqrt(3) * q + math.sqrt(3) / 2 * r) + ox
            y = s * 1.5 * r + oy
        return x, y

    def hex_to_pixel(self, q: int, r: int) -> tuple[float, float]:
        """Returns the warped pixel position of a hex centre."""
        return self._apply_warp(*self._parametric_hex_to_pixel(q, r))

    def pixel_to_nearest(self, px: float, py: float) -> Optional[tuple[int, int]]:
        if self._warp_corners is None:
            return self._pixel_to_nearest_parametric(px, py)
        return self._pixel_to_nearest_bruteforce(px, py)

    def _pixel_to_nearest_parametric(
        self, px: float, py: float
    ) -> Optional[tuple[int, int]]:
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

    def _pixel_to_nearest_bruteforce(
        self, px: float, py: float
    ) -> Optional[tuple[int, int]]:
        """O(n) nearest-cell search used when warp is active."""
        best_coord = None
        best_d2 = math.inf
        for (q, r), cell in self._cells.items():
            cx, cy = self.hex_to_pixel(q, r)
            d2 = (px - cx) ** 2 + (py - cy) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best_coord = (q, r)
        return best_coord

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
        """
        Returns the 6 pixel corners of a hex polygon.
        When warp is active, each corner is warped independently from its
        parametric position, which keeps the tessellation gap-free.
        """
        cx_p, cy_p = self._parametric_hex_to_pixel(q, r)
        angle_offset = 0 if self.orientation == "flat" else 30
        return [
            self._apply_warp(
                cx_p + self.size * math.cos(math.radians(60 * i + angle_offset)),
                cy_p + self.size * math.sin(math.radians(60 * i + angle_offset)),
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

    def hex_distance(self, n1: int, n2: int) -> int:
        """Cube-coordinate distance (minimum hex steps) between two nodes."""
        c1 = self._num_to_coord.get(n1)
        c2 = self._num_to_coord.get(n2)
        if c1 is None or c2 is None:
            return -1
        dq = c2[0] - c1[0]
        dr = c2[1] - c1[1]
        return (abs(dq) + abs(dr) + abs(dq + dr)) // 2

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
