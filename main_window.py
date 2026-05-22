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
from dialogs import AddEntityDialog, AddLocationDialog, GridSettingsDialog
from entities import Entity, EntityManager
from hex_grid import HexGrid
from locations import Location, LocationManager


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RPG Hex Map Tool")
        self.resize(1280, 820)

        self.grid = HexGrid(**CHULT_GRID)
        self.em = EntityManager()
        self.lm = LocationManager()

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

        self.canvas = HexMapCanvas(self.grid, self.em, self.lm)
        self.canvas.entity_selected.connect(self._on_entity_selected)
        self.canvas.move_requested.connect(self._on_move_requested)
        self.canvas.origin_clicked.connect(self._on_origin_clicked)
        self._grid_dlg = None  # holds open GridSettingsDialog for live updates

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
        self.entity_list.setMaximumHeight(110)
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

        # Location list
        lg = QGroupBox("Locations")
        lg_layout = QVBoxLayout(lg)
        self.location_list = QListWidget()
        self.location_list.setMaximumHeight(110)
        self.location_list.itemClicked.connect(self._on_location_list_click)
        lg_layout.addWidget(self.location_list)

        loc_btn_row = QHBoxLayout()
        add_loc_btn = QPushButton("+ Add")
        add_loc_btn.clicked.connect(self._add_location)
        rm_loc_btn = QPushButton("Remove")
        rm_loc_btn.clicked.connect(self._remove_location)
        edit_loc_btn = QPushButton("Edit")
        edit_loc_btn.clicked.connect(self._edit_location)
        loc_btn_row.addWidget(add_loc_btn)
        loc_btn_row.addWidget(edit_loc_btn)
        loc_btn_row.addWidget(rm_loc_btn)
        lg_layout.addLayout(loc_btn_row)

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
        layout.addWidget(lg)
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

        origin_act = QAction("Set Origin by Click", self)
        origin_act.setShortcut("Ctrl+Shift+O")
        origin_act.triggered.connect(self._start_origin_click)
        map_menu.addAction(origin_act)

        map_menu.addSeparator()
        reset_warp_act = QAction("Reset Warp", self)
        reset_warp_act.setShortcut("Ctrl+Shift+R")
        reset_warp_act.triggered.connect(self._reset_warp)
        map_menu.addAction(reset_warp_act)

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

        origin_act = QAction("Set Origin", self)
        origin_act.setToolTip("Click a hex centre on the map to snap the grid origin there")
        origin_act.triggered.connect(self._start_origin_click)
        tb.addAction(origin_act)

        reset_warp_act2 = QAction("Reset Warp", self)
        reset_warp_act2.setToolTip("Remove all corner warping and restore the parametric grid")
        reset_warp_act2.triggered.connect(self._reset_warp)
        tb.addAction(reset_warp_act2)

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
        self._grid_dlg = dlg
        dlg.settings_changed.connect(self._on_grid_preview)
        if dlg.exec():
            # Settings already applied live — just confirm
            self.status_bar.showMessage(
                f"Grid updated  |  size={self.grid.size:.1f} px  "
                f"origin=({self.grid.origin[0]:.0f}, {self.grid.origin[1]:.0f})  "
                f"{self.grid.cols}×{self.grid.rows}"
            )
        else:
            # Cancel — restore originals
            self.grid.reconfigure(**dlg.get_original())
            self.canvas.refresh()
            self.status_bar.showMessage("Grid settings cancelled — reverted.")
        self._grid_dlg = None

    def _on_grid_preview(self, values: dict):
        self.grid.reconfigure(**values)
        self.canvas.refresh()

    def _reset_warp(self):
        self.grid.reset_warp()
        self.canvas.refresh()
        self.status_bar.showMessage("Warp reset — grid restored to parametric layout.")

    def _start_origin_click(self):
        self.canvas.set_origin_click_mode(True)
        self.status_bar.showMessage(
            "Click on any hex centre on the map to set the grid origin there."
        )

    def _on_origin_clicked(self, x: float, y: float):
        self.grid.reconfigure(origin=(x, y))
        self.canvas.refresh()
        # Update dialog if it's open
        if self._grid_dlg is not None:
            self._grid_dlg.set_origin(x, y)
        self.status_bar.showMessage(
            f"Origin set to ({x:.0f}, {y:.0f})  —  use Grid Settings to fine-tune size."
        )

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
    # Location actions
    # ------------------------------------------------------------------

    def _add_location(self):
        dlg = AddLocationDialog(self.grid.max_number, self)
        if dlg.exec():
            v = dlg.get_values()
            loc = Location(
                name=v["name"], node=v["node"],
                color=v["color"], description=v["description"],
            )
            self.lm.add(loc)
            self._refresh_locations()
            self.canvas.refresh()
            self.status_bar.showMessage(f"Location '{loc.name}' placed at node {loc.node}.")

    def _remove_location(self):
        item = self.location_list.currentItem()
        if not item:
            return
        lid = item.data(Qt.ItemDataRole.UserRole)
        loc = self.lm.get(lid)
        if loc:
            self.lm.remove(lid)
            self.canvas.set_highlighted_location(-1)
            self._refresh_locations()
            self.canvas.refresh()
            self.status_bar.showMessage(f"Location '{loc.name}' removed.")

    def _edit_location(self):
        item = self.location_list.currentItem()
        if not item:
            return
        lid = item.data(Qt.ItemDataRole.UserRole)
        loc = self.lm.get(lid)
        if not loc:
            return
        dlg = AddLocationDialog(self.grid.max_number, self, preset_node=loc.node)
        dlg.setWindowTitle("Edit Location")
        dlg.name_edit.setText(loc.name)
        dlg.node_spin.setValue(loc.node)
        dlg.desc_edit.setPlainText(loc.description)
        dlg._color = loc.color
        dlg._preview.setStyleSheet(f"background:{loc.color};border:1px solid #888;")
        if dlg.exec():
            v = dlg.get_values()
            self.lm.update(lid, name=v["name"], node=v["node"],
                           color=v["color"], description=v["description"])
            self._refresh_locations()
            self.canvas.refresh()
            self.status_bar.showMessage(f"Location '{v['name']}' updated.")

    def _refresh_locations(self):
        self.location_list.clear()
        for loc in self.lm.all:
            item = QListWidgetItem(f"{loc.name}  → {loc.node}")
            item.setData(Qt.ItemDataRole.UserRole, loc.id)
            item.setForeground(QColor(loc.color))
            self.location_list.addItem(item)

    def _on_location_list_click(self, item: QListWidgetItem):
        loc = self.lm.get(item.data(Qt.ItemDataRole.UserRole))
        if not loc:
            return
        # Clear entity selection when focusing a location
        self.canvas._selected_entity = None
        self.canvas._valid_targets = set()
        self.entity_list.clearSelection()
        desc_line = f"\n{loc.description}" if loc.description else ""
        self.info_label.setText(f"Location: {loc.name}\nNode: {loc.node}{desc_line}")
        self.canvas.set_highlighted_location(loc.node)
        pos = self.grid.pixel_of(loc.node)
        if pos:
            self.canvas.centerOn(pos[0], pos[1])

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
            "locations": self.lm.to_list(),
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
            # Reload locations (mutate in-place so canvas ref stays valid)
            for loc in list(self.lm.all):
                self.lm.remove(loc.id)
            for ld in data.get("locations", []):
                self.lm.add(
                    Location(
                        name=ld["name"],
                        node=ld["node"],
                        color=ld.get("color", "#f39c12"),
                        description=ld.get("description", ""),
                        id=ld["id"],
                    )
                )
            self.canvas.set_selected(None)
            self.canvas.set_highlighted_location(-1)
            self._refresh_list()
            self._refresh_locations()
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
            # Clear any location highlight when switching to an entity
            self.canvas._highlighted_location_node = -1
            self.location_list.clearSelection()
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
