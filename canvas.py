from __future__ import annotations

from enum import Enum, auto
from typing import Optional

from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from entities import Entity, EntityManager
from node_map import MapNode, NodeMap


class CanvasMode(Enum):
    EDIT = auto()
    PLAY = auto()


class HexMapCanvas(QGraphicsView):
    entity_selected = pyqtSignal(object)      # Entity | None
    move_requested = pyqtSignal(object, int)  # entity, target_node
    node_count_changed = pyqtSignal(int)

    def __init__(self, node_map: NodeMap, em: EntityManager):
        super().__init__()
        self.node_map = node_map
        self.em = em
        self.mode = CanvasMode.PLAY
        self.teleport_enabled = False
        self.show_connections = True
        self._selected_entity: Optional[Entity] = None
        self._valid_targets: set[int] = set()
        self._bg_pixmap: Optional[QPixmap] = None
        self._pan_start = None
        self.grid_opacity: int = 200
        self._dragging_node: Optional[MapNode] = None

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
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
        self._draw_connections()
        self._draw_nodes()
        self._draw_entities()

    def set_mode(self, mode: CanvasMode):
        self.mode = mode
        if mode == CanvasMode.EDIT:
            self._selected_entity = None
            self._valid_targets = set()
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.refresh()

    def set_selected(self, entity: Optional[Entity]):
        self._selected_entity = entity
        if entity is None:
            self._valid_targets = set()
        elif self.teleport_enabled:
            self._valid_targets = {n.number for n in self.node_map.all_nodes} - {entity.node}
        else:
            self._valid_targets = set(self.node_map.neighbors(entity.node))
        self.refresh()
        self.entity_selected.emit(entity)

    def set_teleport(self, enabled: bool):
        self.teleport_enabled = enabled
        if self._selected_entity:
            self.set_selected(self._selected_entity)

    def set_grid_opacity(self, value: int):
        self.grid_opacity = max(0, min(255, value))
        self.refresh()

    def set_show_connections(self, show: bool):
        self.show_connections = show
        self.refresh()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw_background(self):
        if self._bg_pixmap:
            item = self._scene.addPixmap(self._bg_pixmap)
            item.setZValue(0)
            self._scene.setSceneRect(item.boundingRect())

    def _draw_connections(self):
        if not self.show_connections or not self.node_map.all_nodes:
            return
        op = self.grid_opacity
        pen = QPen(QColor(120, 160, 255, max(0, op // 2)), 1.5)
        drawn: set[tuple[int, int]] = set()
        for node in self.node_map.all_nodes:
            for nb_num in self.node_map.neighbors(node.number):
                key = (min(node.number, nb_num), max(node.number, nb_num))
                if key in drawn:
                    continue
                drawn.add(key)
                nb = self.node_map.get_node(nb_num)
                if nb:
                    line = self._scene.addLine(node.x, node.y, nb.x, nb.y, pen)
                    line.setZValue(1)

    def _draw_nodes(self):
        op = self.grid_opacity
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        r = 16.0

        selected_node = self._selected_entity.node if self._selected_entity else None

        for node in self.node_map.all_nodes:
            is_target = node.number in self._valid_targets
            is_sel = node.number == selected_node

            if self.mode == CanvasMode.EDIT:
                pen = QPen(QColor(255, 160, 30, op), 1.5)
                brush = QBrush(QColor(80, 40, 0, max(0, op // 3)))
            elif is_sel:
                pen = QPen(QColor(255, 210, 0, 255), 2.5)
                brush = QBrush(QColor(255, 210, 0, 70))
            elif is_target:
                pen = QPen(QColor(80, 220, 80, 255), 2.5)
                brush = QBrush(QColor(80, 220, 80, 70))
            else:
                pen = QPen(QColor(200, 200, 200, op), 1)
                brush = QBrush(QColor(40, 40, 80, max(0, op // 4)))

            dot = self._scene.addEllipse(
                QRectF(node.x - r, node.y - r, 2 * r, 2 * r), pen, brush
            )
            dot.setZValue(2)

            lbl = self._scene.addText(str(node.number), font)
            lbl.setDefaultTextColor(QColor(255, 255, 255, min(255, int(op * 1.2))))
            br = lbl.boundingRect()
            lbl.setPos(node.x - br.width() / 2, node.y - br.height() / 2)
            lbl.setZValue(3)

    def _draw_entities(self):
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        r = 20.0

        for entity in self.em.all:
            node = self.node_map.get_node(entity.node)
            if not node:
                continue
            cx, cy = node.x, node.y
            is_sel = bool(self._selected_entity and entity.id == self._selected_entity.id)

            pen = QPen(QColor("yellow") if is_sel else QColor("white"), 3 if is_sel else 2)
            circle = self._scene.addEllipse(
                QRectF(cx - r, cy - r, 2 * r, 2 * r),
                pen,
                QBrush(QColor(entity.color)),
            )
            circle.setZValue(4)

            lbl = self._scene.addText(entity.label, font)
            lbl.setDefaultTextColor(QColor("white"))
            br = lbl.boundingRect()
            lbl.setPos(cx - br.width() / 2, cy - br.height() / 2)
            lbl.setZValue(5)

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def _hit_radius(self) -> float:
        """Returns a hit-test radius in scene px that feels ~12 screen-px at any zoom."""
        scale = self.transform().m11()
        return max(16.0, 12.0 / scale)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        sp = self.mapToScene(event.pos())
        x, y = sp.x(), sp.y()
        hr = self._hit_radius()

        # ---- EDIT mode ----
        if self.mode == CanvasMode.EDIT:
            if event.button() == Qt.MouseButton.LeftButton:
                existing = self.node_map.nearest_to(x, y, max_dist=hr)
                if existing:
                    self._dragging_node = existing   # start drag
                else:
                    self.node_map.add_node(x, y)
                    self.node_count_changed.emit(self.node_map.count)
                    self.refresh()
            elif event.button() == Qt.MouseButton.RightButton:
                target = self.node_map.nearest_to(x, y, max_dist=hr)
                if target:
                    self.node_map.remove_node(target.number)
                    self.node_count_changed.emit(self.node_map.count)
                    self.refresh()
            return

        # ---- PLAY mode ----
        if event.button() == Qt.MouseButton.RightButton:
            self.set_selected(None)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            clicked = self.node_map.nearest_to(x, y, max_dist=hr)
            if self._selected_entity:
                if clicked and clicked.number in self._valid_targets:
                    self.move_requested.emit(self._selected_entity, clicked.number)
                else:
                    here = self.em.at_node(clicked.number) if clicked else []
                    self.set_selected(here[0] if here else None)
            else:
                if clicked:
                    here = self.em.at_node(clicked.number)
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
            return

        if self.mode == CanvasMode.EDIT and self._dragging_node is not None:
            sp = self.mapToScene(event.pos())
            self.node_map.move_node(self._dragging_node.number, sp.x(), sp.y())
            self.refresh()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = None
            cursor = (
                Qt.CursorShape.CrossCursor
                if self.mode == CanvasMode.EDIT
                else Qt.CursorShape.ArrowCursor
            )
            self.setCursor(cursor)
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging_node = None
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
