from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from entities import Entity, EntityManager
from hex_grid import HexGrid


class HexMapCanvas(QGraphicsView):
    entity_selected = pyqtSignal(object)        # Entity | None
    move_requested = pyqtSignal(object, int)    # entity, target_node
    origin_clicked = pyqtSignal(float, float)   # x, y scene coords

    def __init__(self, grid: HexGrid, em: EntityManager):
        super().__init__()
        self.grid = grid
        self.em = em
        self.teleport_enabled = False
        self._selected_entity: Optional[Entity] = None
        self._valid_targets: set[int] = set()
        self._bg_pixmap: Optional[QPixmap] = None
        self._pan_start = None
        self.grid_opacity: int = 180  # 0–255
        self._origin_click_mode: bool = False

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(self.renderHints().__class__.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(30, 30, 30)))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_image(self, path: str):
        self._bg_pixmap = QPixmap(path)
        self.refresh()
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def refresh(self):
        self._scene.clear()
        self._draw_background()
        self._draw_grid()
        self._draw_entities()

    def set_selected(self, entity: Optional[Entity]):
        self._selected_entity = entity
        if entity is None:
            self._valid_targets = set()
        elif self.teleport_enabled:
            self._valid_targets = {c.number for c in self.grid.all_cells} - {entity.node}
        else:
            self._valid_targets = set(self.grid.neighbor_numbers(entity.node))
        self.refresh()
        self.entity_selected.emit(entity)

    def set_teleport(self, enabled: bool):
        self.teleport_enabled = enabled
        if self._selected_entity:
            self.set_selected(self._selected_entity)

    def set_grid_opacity(self, value: int):
        self.grid_opacity = max(0, min(255, value))
        self.refresh()

    def set_origin_click_mode(self, enabled: bool):
        self._origin_click_mode = enabled
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
        pen_normal = QPen(QColor(80, 80, 80, op), 1)
        pen_target = QPen(QColor(80, 200, 80, min(255, op + 60)), 2)
        pen_sel_node = QPen(QColor(255, 200, 0, min(255, op + 60)), 3)
        brush_clear = QBrush(Qt.BrushStyle.NoBrush)
        brush_target = QBrush(QColor(80, 200, 80, min(255, op // 3)))
        brush_sel_node = QBrush(QColor(255, 200, 0, min(255, op // 3)))

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

            if is_sel:
                pen, brush = pen_sel_node, brush_sel_node
            elif is_target:
                pen, brush = pen_target, brush_target
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

        for entity in self.em.all:
            pos = self.grid.pixel_of(entity.node)
            if pos is None:
                continue
            cx, cy = pos
            r = self.grid.size * 0.38
            is_sel = self._selected_entity and entity.id == self._selected_entity.id

            pen = QPen(QColor("yellow") if is_sel else QColor("white"), 2 if not is_sel else 3)
            circle = self._scene.addEllipse(
                QRectF(cx - r, cy - r, 2 * r, 2 * r),
                pen,
                QBrush(QColor(entity.color)),
            )
            circle.setZValue(3)

            lbl = self._scene.addText(entity.label, font)
            lbl.setDefaultTextColor(QColor("white"))
            br = lbl.boundingRect()
            lbl.setPos(cx - br.width() / 2, cy - br.height() / 2)
            lbl.setZValue(4)

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        # Origin-click calibration mode: any left-click sets the origin
        if self._origin_click_mode and event.button() == Qt.MouseButton.LeftButton:
            sp = self.mapToScene(event.pos())
            self.set_origin_click_mode(False)
            self.origin_clicked.emit(sp.x(), sp.y())
            return

        if event.button() == Qt.MouseButton.RightButton:
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
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
