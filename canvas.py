from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from entities import Entity, EntityManager
from hex_grid import HexGrid
from locations import LocationManager
from terrain import TERRAIN_ABBR, TERRAIN_ALPHA, TERRAIN_COLORS, TerrainMap

# Terrain types that require the Seafaring flag to enter
WATER_TERRAINS: frozenset[str] = frozenset({"Ocean", "Rivers"})


class HexMapCanvas(QGraphicsView):
    entity_selected = pyqtSignal(object)        # Entity | None
    move_requested = pyqtSignal(object, int)    # entity, target_node
    origin_clicked = pyqtSignal(float, float)   # x, y scene coords
    right_clicked_entity = pyqtSignal(object)   # Entity (for edit dialog)

    def __init__(self, grid: HexGrid, em: EntityManager, lm: LocationManager, tm: TerrainMap):
        super().__init__()
        self.grid = grid
        self.em = em
        self.lm = lm
        self.tm = tm
        self.teleport_enabled = False
        self._selected_entity: Optional[Entity] = None
        self._valid_targets: set[int] = set()
        self._bg_pixmap: Optional[QPixmap] = None
        self._pan_start = None
        self.grid_opacity: int = 180  # 0–255
        self._origin_click_mode: bool = False
        self._highlighted_location_node: int = -1  # hex to tint purple

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(self.renderHints().__class__.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))

        # Corner-drag state  (indices: 0=TL 1=TR 2=BL 3=BR)
        self._dragging_corner: int = -1
        self._corner_drag_start_scene: tuple[float, float] | None = None
        self._corner_drag_origin: tuple[float, float] | None = None

        # Day-turn tracking
        self._moved_ids: set[str] = set()   # entity IDs that have fully acted today

        # Fog of war
        self.fog_enabled: bool = False
        self._fog_revealed: set[int] = set()   # node numbers that have been uncovered

        # Terrain paint state
        self._terrain_paint_mode: bool = False
        self._terrain_paint_type: str = "Jungle"
        self._terrain_dragging: bool = False       # left/right drag in progress
        self._terrain_drag_erase: bool = False     # True = erasing, False = painting
        self._terrain_last_node: Optional[int] = None   # avoid repainting same hex

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_image(self, path: str):
        self._bg_pixmap = QPixmap(path)
        self.refresh()
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def set_highlighted_location(self, node: int):
        """Highlight a hex cell to indicate the selected location (-1 = none)."""
        self._highlighted_location_node = node
        self.refresh()

    def refresh(self):
        self._scene.clear()
        self._draw_background()
        self._draw_terrain()
        self._draw_grid()
        self._draw_locations()
        self._draw_bot_targets()
        self._draw_entities()
        self._draw_fog()            # covers unrevealed hexes above everything else
        self._draw_corner_handles()

    def mark_moved(self, entity_id: str):
        """Mark an entity as having fully acted this day."""
        self._moved_ids.add(entity_id)

    def clear_moved(self):
        """Reset all turn-tracking for a new day."""
        self._moved_ids.clear()

    def set_selected(self, entity: Optional[Entity]):
        self._selected_entity = entity
        if entity is None:
            self._valid_targets = set()
        elif entity.id in self._moved_ids:
            self._valid_targets = set()     # turn already spent
        elif self.teleport_enabled:
            self._valid_targets = {c.number for c in self.grid.all_cells} - {entity.node}
        else:
            self._valid_targets = set(self.grid.neighbor_numbers(entity.node))

        # Remove water tiles for non-seafaring entities
        if entity is not None and not getattr(entity, "seafaring", False):
            self._valid_targets = {
                n for n in self._valid_targets
                if self.tm.get(n) not in WATER_TERRAINS
            }

        self.refresh()
        self.entity_selected.emit(entity)

    def set_teleport(self, enabled: bool):
        self.teleport_enabled = enabled
        if self._selected_entity:
            self.set_selected(self._selected_entity)

    def set_grid_opacity(self, value: int):
        self.grid_opacity = max(0, min(255, value))
        self.refresh()

    def reveal_hex(self, node: int):
        """Lift fog on a single hex.  Call after a non-bot entity moves there."""
        self._fog_revealed.add(node)

    def set_fog_enabled(self, enabled: bool):
        self.fog_enabled = enabled
        self.refresh()

    def set_origin_click_mode(self, enabled: bool):
        self._origin_click_mode = enabled
        if not self._terrain_paint_mode:
            self.setCursor(
                Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor
            )

    def set_terrain_paint(self, enabled: bool, terrain: str = "Jungle"):
        self._terrain_paint_mode = enabled
        self._terrain_paint_type = terrain
        self.setCursor(
            Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor
        )

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw_background(self):
        if self._bg_pixmap:
            self._scene.addPixmap(self._bg_pixmap).setZValue(0)

    def _draw_grid(self):
        op = self.grid_opacity
        pen_normal   = QPen(QColor(80,  80,  80,  op), 1)
        pen_target   = QPen(QColor(80,  200, 80,  min(255, op + 60)), 2)
        pen_sel_node = QPen(QColor(255, 200, 0,   min(255, op + 60)), 3)
        pen_loc_node = QPen(QColor(180, 100, 255, min(255, op + 60)), 2)
        brush_clear    = QBrush(Qt.BrushStyle.NoBrush)
        brush_target   = QBrush(QColor(80,  200, 80,  min(255, op // 3)))
        brush_sel_node = QBrush(QColor(255, 200, 0,   min(255, op // 3)))
        brush_loc_node = QBrush(QColor(180, 100, 255, min(255, op // 4)))

        text_alpha = max(0, min(255, int(op * 1.2)))

        font = QFont()
        font.setPointSize(max(6, int(self.grid.size * 0.28)))

        selected_node = self._selected_entity.node if self._selected_entity else None

        for cell in self.grid.all_cells:
            corners = self.grid.corners(cell.q, cell.r)
            poly = QPolygonF([QPointF(x, y) for x, y in corners])
            cx, cy = self.grid.hex_to_pixel(cell.q, cell.r)

            is_sel = cell.number == selected_node
            is_target = cell.number in self._valid_targets
            is_loc = cell.number == self._highlighted_location_node

            if is_sel:
                pen, brush = pen_sel_node, brush_sel_node
            elif is_target:
                pen, brush = pen_target, brush_target
            elif is_loc:
                pen, brush = pen_loc_node, brush_loc_node
            else:
                pen, brush = pen_normal, brush_clear

            self._scene.addPolygon(poly, pen, brush).setZValue(1)

            num_item = self._scene.addText(str(cell.number), font)
            num_item.setDefaultTextColor(QColor(210, 210, 210, text_alpha))
            br = num_item.boundingRect()
            num_item.setPos(cx - br.width() / 2, cy - br.height() / 2)
            num_item.setZValue(2)

    def _draw_entities(self):
        font = QFont()
        font.setPointSize(max(7, int(self.grid.size * 0.28)))
        font.setBold(True)

        for entity in self.em.toplevel:   # skip group members
            pos = self.grid.pixel_of(entity.node)
            if pos is None:
                continue
            cx, cy = pos
            r = self.grid.size * 0.38
            is_sel   = self._selected_entity and entity.id == self._selected_entity.id
            is_moved = entity.id in self._moved_ids

            # Fill colour — dim when turn is spent
            fill_color = QColor(entity.color)
            if is_moved:
                fill_color.setAlpha(110)

            # Border colour / style
            if is_sel:
                pen_color, pen_w = QColor("yellow"), 3
            elif is_moved:
                pen_color, pen_w = QColor(90, 90, 90), 1
            elif entity.is_bot:
                pen_color, pen_w = QColor(160, 160, 160), 2
            else:
                pen_color, pen_w = QColor("white"), 2

            pen = QPen(pen_color, pen_w)
            if entity.is_bot and not is_moved:
                pen.setStyle(Qt.PenStyle.DashLine)

            circle = self._scene.addEllipse(
                QRectF(cx - r, cy - r, 2 * r, 2 * r),
                pen,
                QBrush(fill_color),
            )
            circle.setZValue(5)

            lbl = self._scene.addText(entity.label, font)
            txt_color = QColor(160, 160, 160) if is_moved else QColor("white")
            lbl.setDefaultTextColor(txt_color)
            br = lbl.boundingRect()
            lbl.setPos(cx - br.width() / 2, cy - br.height() / 2)
            lbl.setZValue(6)

            # Small "✓" overlay for moved entities
            if is_moved:
                chk_font = QFont()
                chk_font.setPointSize(max(5, int(self.grid.size * 0.18)))
                chk = self._scene.addText("✓", chk_font)
                chk.setDefaultTextColor(QColor(120, 220, 120, 200))
                cbr = chk.boundingRect()
                chk.setPos(cx + r * 0.4 - cbr.width() / 2,
                            cy - r - cbr.height() * 0.6)
                chk.setZValue(7)

    # ------------------------------------------------------------------
    # Terrain fills  (z=0.5 fill, z=0.8 abbreviation label)
    # ------------------------------------------------------------------

    def _draw_terrain(self):
        abbr_font = QFont()
        abbr_font.setPointSize(max(5, int(self.grid.size * 0.16)))
        abbr_font.setBold(True)

        for cell in self.grid.all_cells:
            t = self.tm.get(cell.number)
            if t is None:
                continue

            # Filled polygon
            corners = self.grid.corners(cell.q, cell.r)
            poly = QPolygonF([QPointF(x, y) for x, y in corners])
            fill = QColor(TERRAIN_COLORS[t])
            fill.setAlpha(TERRAIN_ALPHA[t])
            self._scene.addPolygon(
                poly, QPen(Qt.PenStyle.NoPen), QBrush(fill)
            ).setZValue(0.5)

            # Subtle abbreviation at the top of the hex
            cx, cy = self.grid.hex_to_pixel(cell.q, cell.r)
            lbl = self._scene.addText(TERRAIN_ABBR[t], abbr_font)
            lbl_color = QColor(255, 255, 255, 130)
            lbl.setDefaultTextColor(lbl_color)
            br = lbl.boundingRect()
            lbl.setPos(cx - br.width() / 2,
                       cy - self.grid.size * 0.48)
            lbl.setZValue(0.8)

    # ------------------------------------------------------------------
    # Location markers  (z=3 diamonds, z=4 name labels)
    # ------------------------------------------------------------------

    def _draw_locations(self):
        name_font = QFont()
        name_font.setPointSize(max(5, int(self.grid.size * 0.14)))
        name_font.setBold(True)

        for loc in self.lm.all:
            pos = self.grid.pixel_of(loc.node)
            if pos is None:
                continue
            cx, cy = pos
            h = max(6.0, self.grid.size * 0.18)   # diamond half-size

            # Filled diamond (map-pin style)
            diamond = QPolygonF([
                QPointF(cx,     cy - h),   # top
                QPointF(cx + h, cy),       # right
                QPointF(cx,     cy + h),   # bottom
                QPointF(cx - h, cy),       # left
            ])
            pen   = QPen(QColor("white"), 1.2)
            brush = QBrush(QColor(loc.color))
            self._scene.addPolygon(diamond, pen, brush).setZValue(3)

            # Name label below the diamond
            lbl = self._scene.addText(loc.name, name_font)
            lbl.setDefaultTextColor(QColor(loc.color))
            br = lbl.boundingRect()
            # Centre horizontally; sit just below the diamond's bottom tip
            lbl.setPos(cx - br.width() / 2, cy + h + 2)
            lbl.setZValue(4)

    # ------------------------------------------------------------------
    # Bot target indicators  (z=4.5 — above locations, below entities)
    # ------------------------------------------------------------------

    def _draw_bot_targets(self):
        """
        For every bot with a bot_target draw:
          • a dashed line from the bot's hex to the target hex
          • a small ring + dot at the target hex
        """
        for entity in self.em.toplevel:
            if not entity.is_bot:
                continue
            target = getattr(entity, "bot_target", None)
            if target is None or target == entity.node:
                continue

            src_pos = self.grid.pixel_of(entity.node)
            dst_pos = self.grid.pixel_of(target)
            if src_pos is None or dst_pos is None:
                continue

            sx, sy = src_pos
            tx, ty = dst_pos
            color = QColor(entity.color)
            color.setAlpha(160)

            # Dashed line
            line_pen = QPen(color, 1.5, Qt.PenStyle.DashLine)
            line = self._scene.addLine(sx, sy, tx, ty, line_pen)
            line.setZValue(4.5)

            # Ring at target
            ring_r = self.grid.size * 0.22
            ring_pen = QPen(color, 2, Qt.PenStyle.SolidLine)
            ring = self._scene.addEllipse(
                QRectF(tx - ring_r, ty - ring_r, 2 * ring_r, 2 * ring_r),
                ring_pen,
                QBrush(Qt.BrushStyle.NoBrush),
            )
            ring.setZValue(4.5)

            # Dot at target
            dot_r = ring_r * 0.35
            dot_brush = QBrush(color)
            dot = self._scene.addEllipse(
                QRectF(tx - dot_r, ty - dot_r, 2 * dot_r, 2 * dot_r),
                QPen(Qt.PenStyle.NoPen),
                dot_brush,
            )
            dot.setZValue(4.6)

    # ------------------------------------------------------------------
    # Fog of war  (z=8 black fill · z=9 border/tint · z=9.5 node number)
    # ------------------------------------------------------------------

    def _draw_fog(self):
        """
        For every hex NOT yet revealed, draw a solid black overlay that hides
        all terrain, location and entity information.  The hex border and node
        number remain visible in white so the player can navigate.  If an
        unrevealed hex is a valid move target it gets a green tint on top of
        the fog instead of a white border, so the player knows they can step
        there.
        """
        if not self.fog_enabled:
            return

        op = self.grid_opacity
        text_alpha = max(0, min(255, int(op * 1.2)))

        font = QFont()
        font.setPointSize(max(6, int(self.grid.size * 0.28)))

        pen_none    = QPen(Qt.PenStyle.NoPen)
        pen_white   = QPen(QColor(255, 255, 255, min(255, op + 60)), 1)
        pen_target  = QPen(QColor(80, 200, 80, min(255, op + 60)), 2)
        brush_fog    = QBrush(QColor(0, 0, 0, 245))   # near-opaque black
        brush_target = QBrush(QColor(80, 200, 80, min(255, op // 3)))
        brush_clear  = QBrush(Qt.BrushStyle.NoBrush)

        for cell in self.grid.all_cells:
            if cell.number in self._fog_revealed:
                continue                            # already uncovered — skip

            corners = self.grid.corners(cell.q, cell.r)
            poly = QPolygonF([QPointF(x, y) for x, y in corners])
            cx, cy = self.grid.hex_to_pixel(cell.q, cell.r)
            is_target = cell.number in self._valid_targets

            # ── Solid black fill ─────────────────────────────────────────
            self._scene.addPolygon(poly, pen_none, brush_fog).setZValue(8)

            # ── Border + optional move-target tint above the fog ─────────
            if is_target:
                # Green semi-transparent fill + green border
                self._scene.addPolygon(poly, pen_target, brush_target).setZValue(9)
            else:
                # White outline only
                self._scene.addPolygon(poly, pen_white, brush_clear).setZValue(9)

            # ── Node number in white ──────────────────────────────────────
            num = self._scene.addText(str(cell.number), font)
            num.setDefaultTextColor(QColor(255, 255, 255, text_alpha))
            br = num.boundingRect()
            num.setPos(cx - br.width() / 2, cy - br.height() / 2)
            num.setZValue(9.5)

    # ------------------------------------------------------------------
    # Corner-warp handles
    # ------------------------------------------------------------------

    # Corner colours: TL=cyan, TR=magenta, BL=yellow, BR=lime
    _CORNER_COLORS = ["#00e5ff", "#ff40ff", "#ffff00", "#00ff80"]
    _CORNER_LABELS = ["TL", "TR", "BL", "BR"]
    _HANDLE_R = 10          # visual radius in scene pixels
    _HIT_RADIUS = 16        # click-detection radius

    def _draw_corner_handles(self):
        corners = self.grid.get_warp_corners()   # (tl, tr, bl, br)
        font = QFont()
        font.setPointSize(7)
        font.setBold(True)
        for i, (cx, cy) in enumerate(corners):
            color = QColor(self._CORNER_COLORS[i])
            r = self._HANDLE_R
            pen = QPen(QColor("white"), 1.5)
            brush = QBrush(color)
            circle = self._scene.addEllipse(
                QRectF(cx - r, cy - r, 2 * r, 2 * r), pen, brush
            )
            circle.setZValue(10)
            lbl = self._scene.addText(self._CORNER_LABELS[i], font)
            lbl.setDefaultTextColor(QColor("black"))
            br = lbl.boundingRect()
            lbl.setPos(cx - br.width() / 2, cy - br.height() / 2)
            lbl.setZValue(11)

    def _corner_hit(self, sx: float, sy: float) -> int:
        """Return 0–3 for the first corner handle within hit radius, else -1."""
        corners = self.grid.get_warp_corners()
        for i, (cx, cy) in enumerate(corners):
            if (sx - cx) ** 2 + (sy - cy) ** 2 <= self._HIT_RADIUS ** 2:
                return i
        return -1

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _terrain_paint_at(self, sp, erase: bool):
        """Apply or erase terrain at the scene point sp."""
        coord = self.grid.pixel_to_nearest(sp.x(), sp.y())
        if coord is None:
            return None
        cell = self.grid.cell(*coord)
        if cell is None:
            return None
        if erase:
            self.tm.clear(cell.number)
        else:
            self.tm.set(cell.number, self._terrain_paint_type)
        return cell.number

    def _flood_fill_terrain(self, start_node: int, new_terrain: Optional[str]):
        """
        BFS flood fill starting at start_node.

        Spreads to all contiguous hexes that share the *same* starting terrain
        (including None = unpainted) and paints them with new_terrain.
        If new_terrain is None the matching region is cleared instead.
        """
        initial = self.tm.get(start_node)
        if initial == new_terrain:
            return                          # already the right colour — nothing to do

        visited: set[int] = {start_node}
        queue: list[int] = [start_node]
        changed: list[int] = []

        while queue:
            node = queue.pop(0)
            changed.append(node)
            for nb in self.grid.neighbor_numbers(node):
                if nb not in visited and self.tm.get(nb) == initial:
                    visited.add(nb)
                    queue.append(nb)

        for node in changed:
            if new_terrain is None:
                self.tm.clear(node)
            else:
                self.tm.set(node, new_terrain)

        self.refresh()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        # Terrain paint mode — intercepts left and right clicks
        if self._terrain_paint_mode and event.button() in (
            Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton
        ):
            erase = event.button() == Qt.MouseButton.RightButton
            sp = self.mapToScene(event.pos())
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

            if shift:
                # Shift+click → flood fill / flood erase
                coord = self.grid.pixel_to_nearest(sp.x(), sp.y())
                if coord:
                    cell = self.grid.cell(*coord)
                    if cell:
                        fill = None if erase else self._terrain_paint_type
                        self._flood_fill_terrain(cell.number, fill)
            else:
                # Normal click → single hex + start drag
                node = self._terrain_paint_at(sp, erase)
                if node is not None:
                    self._terrain_dragging = True
                    self._terrain_drag_erase = erase
                    self._terrain_last_node = node
                    self.refresh()
            return

        # Origin-click calibration mode: any left-click sets the origin
        if self._origin_click_mode and event.button() == Qt.MouseButton.LeftButton:
            sp = self.mapToScene(event.pos())
            self.set_origin_click_mode(False)
            self.origin_clicked.emit(sp.x(), sp.y())
            return

        if event.button() == Qt.MouseButton.LeftButton:
            sp = self.mapToScene(event.pos())
            idx = self._corner_hit(sp.x(), sp.y())
            if idx >= 0:
                self._dragging_corner = idx
                self._corner_drag_start_scene = (sp.x(), sp.y())
                corners = self.grid.get_warp_corners()
                self._corner_drag_origin = corners[idx]
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                return

        if event.button() == Qt.MouseButton.RightButton:
            sp = self.mapToScene(event.pos())
            coord = self.grid.pixel_to_nearest(sp.x(), sp.y())
            if coord:
                cell = self.grid.cell(*coord)
                if cell:
                    here = self.em.at_node(cell.number)
                    if here:
                        self.right_clicked_entity.emit(here[0])
                        return
            self.set_selected(None)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            sp = self.mapToScene(event.pos())
            coord = self.grid.pixel_to_nearest(sp.x(), sp.y())
            if coord is None:
                return
            cell = self.grid.cell(*coord)
            if cell is None:
                return
            clicked = cell.number

            if self._selected_entity:
                if clicked in self._valid_targets:
                    self.move_requested.emit(self._selected_entity, clicked)
                else:
                    here = self.em.at_node(clicked)
                    self.set_selected(here[0] if here else None)
            else:
                here = self.em.at_node(clicked)
                if here:
                    self.set_selected(here[0])

    def mouseMoveEvent(self, event):
        # Terrain drag-paint
        if self._terrain_dragging:
            sp = self.mapToScene(event.pos())
            coord = self.grid.pixel_to_nearest(sp.x(), sp.y())
            if coord:
                cell = self.grid.cell(*coord)
                if cell and cell.number != self._terrain_last_node:
                    self._terrain_last_node = cell.number
                    if self._terrain_drag_erase:
                        self.tm.clear(cell.number)
                    else:
                        self.tm.set(cell.number, self._terrain_paint_type)
                    self.refresh()
            return

        # Corner drag
        if self._dragging_corner >= 0 and self._corner_drag_start_scene is not None:
            sp = self.mapToScene(event.pos())
            ox, oy = self._corner_drag_origin
            sx0, sy0 = self._corner_drag_start_scene
            new_pos = (ox + sp.x() - sx0, oy + sp.y() - sy0)
            corners = list(self.grid.get_warp_corners())
            corners[self._dragging_corner] = new_pos
            self.grid.set_warp_corners(*corners)
            self.refresh()
            return

        if self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._terrain_dragging and event.button() in (
            Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton
        ):
            self._terrain_dragging = False
            self._terrain_last_node = None
            return

        if event.button() == Qt.MouseButton.LeftButton and self._dragging_corner >= 0:
            self._dragging_corner = -1
            self._corner_drag_start_scene = None
            self._corner_drag_origin = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
