from __future__ import annotations

import json
import os
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

# Calculated from chult_map.png (4476 × 6000 px): size×17.5 = 1524 → size=87
# Equal ~63 px margins all sides; 33 cols × 39 rows = 1 287 hex points
CHULT_GRID = dict(size=87.0, origin=(150.0, 138.0), orientation="flat", cols=33, rows=39)
CHULT_MAP_FILE = "chult_map.png"

from canvas import HexMapCanvas
from dialogs import AddEntityDialog, GridSettingsDialog
from entities import Entity, EntityManager
from hex_grid import HexGrid


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RPG Hex Map Tool")
        self.resize(1280, 820)

        self.grid = HexGrid(**CHULT_GRID)
        self.em = EntityManager()

        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._auto_load_map()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.canvas = HexMapCanvas(self.grid, self.em)
        self.canvas.entity_selected.connect(self._on_entity_selected)
        self.canvas.move_requested.connect(self._on_move_requested)

        panel = self._build_panel()

        root.addWidget(self.canvas, 1)
        root.addWidget(panel)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Open a map image to begin  (File → Open Map Image)")

    def _build_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(230)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)

        # Entity list
        eg = QGroupBox("Characters & Groups")
        eg_layout = QVBoxLayout(eg)
        self.entity_list = QListWidget()
        self.entity_list.itemClicked.connect(self._on_list_click)
        eg_layout.addWidget(self.entity_list)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._add_entity)
        rm_btn = QPushButton("Remove")
        rm_btn.clicked.connect(self._remove_selected_entity)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rm_btn)
        eg_layout.addLayout(btn_row)

        # Info box
        ig = QGroupBox("Selected")
        il = QVBoxLayout(ig)
        self.info_label = QLabel("None")
        self.info_label.setWordWrap(True)
        il.addWidget(self.info_label)

        # Teleport toggle
        self.teleport_check = QCheckBox("Teleport Mode")
        self.teleport_check.stateChanged.connect(self._toggle_teleport)

        # Grid opacity
        opacity_group = QGroupBox("Grid Overlay")
        og = QVBoxLayout(opacity_group)
        self.opacity_label = QLabel("Opacity: 71%")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 255)
        self.opacity_slider.setValue(180)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        og.addWidget(self.opacity_label)
        og.addWidget(self.opacity_slider)

        hint = QLabel(
            "<small>Left-click entity to select.<br>"
            "Left-click target to move.<br>"
            "Right-click to deselect.<br>"
            "Middle-drag to pan.  Scroll to zoom.</small>"
        )
        hint.setWordWrap(True)

        layout.addWidget(eg)
        layout.addWidget(ig)
        layout.addWidget(self.teleport_check)
        layout.addWidget(opacity_group)
        layout.addWidget(hint)
        layout.addStretch()
        return panel

    def _build_menu(self):
        menu = self.menuBar()

        file_menu = menu.addMenu("File")

        open_map = QAction("Open Map Image…", self)
        open_map.setShortcut("Ctrl+O")
        open_map.triggered.connect(self._open_map)
        file_menu.addAction(open_map)

        file_menu.addSeparator()

        save_act = QAction("Save State…", self)
        save_act.setShortcut("Ctrl+S")
        save_act.triggered.connect(self._save_state)
        file_menu.addAction(save_act)

        load_act = QAction("Load State…", self)
        load_act.setShortcut("Ctrl+L")
        load_act.triggered.connect(self._load_state)
        file_menu.addAction(load_act)

        file_menu.addSeparator()
        quit_act = QAction("Quit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        map_menu = menu.addMenu("Map")
        grid_act = QAction("Grid Settings…", self)
        grid_act.triggered.connect(self._grid_settings)
        map_menu.addAction(grid_act)

    def _build_toolbar(self):
        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)

        open_act = QAction("Open Map", self)
        open_act.triggered.connect(self._open_map)
        tb.addAction(open_act)

        tb.addSeparator()

        grid_act = QAction("Grid Settings", self)
        grid_act.triggered.connect(self._grid_settings)
        tb.addAction(grid_act)

        tb.addSeparator()

        desel_act = QAction("Deselect  [Esc]", self)
        desel_act.setShortcut("Escape")
        desel_act.triggered.connect(lambda: self.canvas.set_selected(None))
        tb.addAction(desel_act)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _auto_load_map(self):
        if os.path.isfile(CHULT_MAP_FILE):
            self.canvas.load_image(CHULT_MAP_FILE)
            self.status_bar.showMessage(
                f"Chult map loaded  |  {self.grid.max_number} hex points  "
                f"({self.grid.cols} cols × {self.grid.rows} rows, size {int(self.grid.size)} px)"
            )

    def _on_opacity_changed(self, value: int):
        pct = round(value / 255 * 100)
        self.opacity_label.setText(f"Opacity: {pct}%")
        self.canvas.set_grid_opacity(value)

    def _open_map(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Map Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp)",
        )
        if path:
            self.canvas.load_image(path)
            self.status_bar.showMessage(f"Map loaded: {path}")

    def _grid_settings(self):
        dlg = GridSettingsDialog(self.grid, self)
        if dlg.exec():
            self.grid.reconfigure(**dlg.get_values())
            self.canvas.refresh()
            self.status_bar.showMessage("Grid updated.")

    def _add_entity(self):
        dlg = AddEntityDialog(self.grid.max_number, self)
        if dlg.exec():
            v = dlg.get_values()
            e = Entity(name=v["name"], node=v["node"], color=v["color"], is_group=v["is_group"])
            self.em.add(e)
            self._refresh_list()
            self.canvas.refresh()

    def _remove_selected_entity(self):
        item = self.entity_list.currentItem()
        if not item:
            return
        eid = item.data(Qt.ItemDataRole.UserRole)
        sel = self.canvas._selected_entity
        if sel and sel.id == eid:
            self.canvas.set_selected(None)
        self.em.remove(eid)
        self._refresh_list()
        self.canvas.refresh()

    def _toggle_teleport(self, state):
        enabled = bool(state)
        self.canvas.set_teleport(enabled)
        self.status_bar.showMessage("Teleport mode " + ("ON" if enabled else "OFF") + ".")

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------

    def _save_state(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save State", "", "JSON (*.json)")
        if not path:
            return
        data = {
            "grid": {
                "size": self.grid.size,
                "origin": list(self.grid.origin),
                "orientation": self.grid.orientation,
                "cols": self.grid.cols,
                "rows": self.grid.rows,
            },
            "entities": [
                {
                    "id": e.id,
                    "name": e.name,
                    "node": e.node,
                    "color": e.color,
                    "is_group": e.is_group,
                }
                for e in self.em.all
            ],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        self.status_bar.showMessage(f"Saved: {path}")

    def _load_state(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load State", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path) as f:
                data = json.load(f)
            g = data["grid"]
            self.grid.reconfigure(
                size=g["size"],
                origin=tuple(g["origin"]),
                orientation=g["orientation"],
                cols=g["cols"],
                rows=g["rows"],
            )
            for e in self.em.all:
                self.em.remove(e.id)
            for ed in data["entities"]:
                self.em.add(
                    Entity(
                        name=ed["name"],
                        node=ed["node"],
                        color=ed["color"],
                        is_group=ed["is_group"],
                        id=ed["id"],
                    )
                )
            self.canvas.set_selected(None)
            self._refresh_list()
            self.canvas.refresh()
            self.status_bar.showMessage(f"Loaded: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", f"Could not load state:\n{exc}")

    # ------------------------------------------------------------------
    # Canvas / list sync
    # ------------------------------------------------------------------

    def _refresh_list(self):
        self.entity_list.clear()
        for e in self.em.all:
            prefix = "[G] " if e.is_group else ""
            item = QListWidgetItem(f"{prefix}{e.name}  → {e.node}")
            item.setData(Qt.ItemDataRole.UserRole, e.id)
            item.setForeground(QColor(e.color))
            self.entity_list.addItem(item)

    def _on_list_click(self, item: QListWidgetItem):
        e = self.em.get(item.data(Qt.ItemDataRole.UserRole))
        if e:
            self.canvas.set_selected(e)

    def _on_entity_selected(self, entity: Optional[Entity]):
        self._refresh_list()
        if entity:
            kind = "Group" if entity.is_group else "Character"
            self.info_label.setText(f"{kind}: {entity.name}\nNode: {entity.node}")
            for i in range(self.entity_list.count()):
                item = self.entity_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == entity.id:
                    self.entity_list.setCurrentItem(item)
                    break
        else:
            self.info_label.setText("None")

    def _on_move_requested(self, entity: Entity, target_node: int):
        self.em.move(entity.id, target_node)
        self.canvas.set_selected(entity)
        self.status_bar.showMessage(f"'{entity.name}' moved to node {target_node}.")
