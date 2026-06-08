from __future__ import annotations

import json
import os
import random
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
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

from PyQt6.QtWidgets import QInputDialog

from canvas import HexMapCanvas
from dialogs import (
    AddEntityDialog,
    AddLocationDialog,
    CombatDialog,
    EditEntityDialog,
    EditGroupDialog,
    GridSettingsDialog,
)
from entities import Entity, EntityManager
from hex_grid import HexGrid
from locations import Location, LocationManager
from pathfinding import find_next_step
from terrain import TERRAIN_COLORS, TERRAINS, TerrainMap


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RPG Hex Map Tool")
        self.resize(1280, 820)

        self.grid = HexGrid(**CHULT_GRID)
        self.em = EntityManager()
        self.lm = LocationManager()
        self.day: int = 1
        self._bonus_move_entity: Optional[str] = None   # ID of entity with unused bonus move
        self.tm = TerrainMap()

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

        self.canvas = HexMapCanvas(self.grid, self.em, self.lm, self.tm)
        self.canvas.entity_selected.connect(self._on_entity_selected)
        self.canvas.move_requested.connect(self._on_move_requested)
        self.canvas.origin_clicked.connect(self._on_origin_clicked)
        self.canvas.right_clicked_entity.connect(self._on_right_click_entity)
        self._grid_dlg = None  # holds open GridSettingsDialog for live updates

        panel = self._build_panel()

        root.addWidget(self.canvas, 1)
        root.addWidget(panel)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Open a map image to begin  (File → Open Map Image)")

    def _build_panel(self) -> QWidget:
        # Outer fixed-width shell with a scroll area so all sections fit
        outer = QWidget()
        outer.setFixedWidth(272)
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Day counter ───────────────────────────────────────────────
        day_group = QGroupBox("Day")
        dg = QVBoxLayout(day_group)
        self.day_label = QLabel("Day 1")
        self.day_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        self.day_progress_label = QLabel("0 / 0 acted")
        self.day_progress_label.setStyleSheet("color: #aaa;")
        day_btn_row = QHBoxLayout()
        wait_btn = QPushButton("Wait  [W]")
        wait_btn.setToolTip("End selected entity's turn without moving")
        wait_btn.clicked.connect(self._on_entity_wait)
        adv_btn = QPushButton("Advance Day")
        adv_btn.clicked.connect(self._advance_day_manual)
        day_btn_row.addWidget(wait_btn)
        day_btn_row.addWidget(adv_btn)
        bots_btn = QPushButton("Move All Bots")
        bots_btn.setToolTip("Move every bot one step toward its target")
        bots_btn.clicked.connect(self._move_all_bots)
        dg.addWidget(self.day_label)
        dg.addWidget(self.day_progress_label)
        dg.addLayout(day_btn_row)
        dg.addWidget(bots_btn)

        # ── Characters & Groups ───────────────────────────────────────
        eg = QGroupBox("Characters & Groups")
        eg_layout = QVBoxLayout(eg)
        self.entity_list = QListWidget()
        self.entity_list.setMaximumHeight(130)
        self.entity_list.setWordWrap(True)
        self.entity_list.itemClicked.connect(self._on_list_click)
        eg_layout.addWidget(self.entity_list)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._add_entity)
        edit_entity_btn = QPushButton("Edit")
        edit_entity_btn.setToolTip(
            "Edit selected character/group: name, color, notes, bot target"
        )
        edit_entity_btn.clicked.connect(self._edit_selected_entity)
        rm_btn = QPushButton("Remove")
        rm_btn.clicked.connect(self._remove_selected_entity)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_entity_btn)
        btn_row.addWidget(rm_btn)
        eg_layout.addLayout(btn_row)

        # ── Locations ─────────────────────────────────────────────────
        lg = QGroupBox("Locations")
        lg_layout = QVBoxLayout(lg)
        self.location_list = QListWidget()
        self.location_list.setMaximumHeight(115)
        self.location_list.setWordWrap(True)
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

        # ── Terrain Paint ─────────────────────────────────────────────
        tg = QGroupBox("Terrain Paint")
        tg_layout = QVBoxLayout(tg)

        # Row 1: combo + swatch + paint toggle
        terrain_row = QHBoxLayout()
        self.terrain_combo = QComboBox()
        self.terrain_combo.addItems(TERRAINS)
        self.terrain_combo.currentTextChanged.connect(self._on_terrain_type_changed)

        self.terrain_swatch = QLabel()
        self.terrain_swatch.setFixedSize(22, 22)

        self.terrain_paint_btn = QPushButton("Paint  [P]")
        self.terrain_paint_btn.setCheckable(True)
        self.terrain_paint_btn.setShortcut("P")
        self.terrain_paint_btn.toggled.connect(self._on_terrain_paint_toggled)

        terrain_row.addWidget(self.terrain_combo, 1)
        terrain_row.addWidget(self.terrain_swatch)
        terrain_row.addWidget(self.terrain_paint_btn)
        tg_layout.addLayout(terrain_row)

        # Row 2: clear-hex button
        clear_terrain_btn = QPushButton("Clear This Hex  [Del]")
        clear_terrain_btn.setShortcut("Del")
        clear_terrain_btn.setToolTip(
            "Remove terrain from the hex under the cursor\n"
            "(or right-click any hex while Paint is on)"
        )
        clear_terrain_btn.clicked.connect(self._clear_selected_terrain)
        tg_layout.addWidget(clear_terrain_btn)

        # Colour legend
        legend_layout = QVBoxLayout()
        legend_layout.setSpacing(1)
        for name in TERRAINS:
            row = QHBoxLayout()
            swatch = QLabel()
            swatch.setFixedSize(14, 14)
            swatch.setStyleSheet(
                f"background:{TERRAIN_COLORS[name]};border:1px solid #555;"
            )
            lbl = QLabel(name)
            lbl.setStyleSheet("font-size: 9pt;")
            row.addWidget(swatch)
            row.addWidget(lbl)
            row.addStretch()
            legend_layout.addLayout(row)
        tg_layout.addLayout(legend_layout)

        # Initialise swatch to the first terrain
        self._on_terrain_type_changed(TERRAINS[0])

        # ── Selected info ─────────────────────────────────────────────
        ig = QGroupBox("Selected")
        il = QVBoxLayout(ig)
        self.info_label = QLabel("None")
        self.info_label.setWordWrap(True)
        self.info_label.setMinimumHeight(88)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.info_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        il.addWidget(self.info_label)

        # ── Teleport toggle ───────────────────────────────────────────
        self.teleport_check = QCheckBox("Teleport Mode")
        self.teleport_check.stateChanged.connect(self._toggle_teleport)

        # ── Grid opacity ──────────────────────────────────────────────
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
            "<small>"
            "<b>Map:</b> left-click to select/move · right-click to edit<br>"
            "<b>Pan/Zoom:</b> middle-drag · scroll wheel<br>"
            "<b>Paint:</b> click/drag to paint · Shift+click to flood-fill<br>"
            "Right-click to erase · Shift+right-click to flood-erase<br>"
            "<b>Keys:</b> W = Wait · P = Paint · Del = Clear terrain hex"
            "</small>"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #999;")

        layout.addWidget(day_group)
        layout.addWidget(eg)
        layout.addWidget(lg)
        layout.addWidget(tg)
        layout.addWidget(ig)
        layout.addWidget(self.teleport_check)
        layout.addWidget(opacity_group)
        layout.addWidget(hint)
        layout.addStretch()

        scroll.setWidget(inner)
        outer_layout.addWidget(scroll)
        return outer

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

        wait_act = QAction("Wait  [W]", self)
        wait_act.setShortcut("W")
        wait_act.setToolTip("End selected entity's turn without moving (also ends bonus move)")
        wait_act.triggered.connect(self._on_entity_wait)
        tb.addAction(wait_act)

        bots_act = QAction("Move All Bots", self)
        bots_act.setToolTip("Move every bot one step toward its assigned target")
        bots_act.triggered.connect(self._move_all_bots)
        tb.addAction(bots_act)

        desel_act = QAction("Deselect  [Esc]", self)
        desel_act.setShortcut("Escape")
        desel_act.triggered.connect(lambda: self.canvas.set_selected(None))
        tb.addAction(desel_act)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _auto_load_map(self):
        self._update_day_ui()
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
            e = Entity(
                name=v["name"], node=v["node"], color=v["color"],
                is_group=v["is_group"], is_bot=v["is_bot"],
                seafaring=v["seafaring"],
            )
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
        # If it's a group, disband cleanly so members are freed
        entity = self.em.get(eid)
        if entity and entity.is_group:
            self.em.disband_group(eid)
        else:
            self.em.remove(eid)
        if eid == self._bonus_move_entity:
            self._bonus_move_entity = None
        self._refresh_list()
        self._update_day_ui()
        self.canvas.refresh()

    def _edit_selected_entity(self):
        """Edit button in the Characters & Groups panel — opens the edit dialog."""
        item = self.entity_list.currentItem()
        if not item:
            self.status_bar.showMessage("Select a character or group first.")
            return
        eid = item.data(Qt.ItemDataRole.UserRole)
        entity = self.em.get(eid)
        if entity:
            self._on_right_click_entity(entity)

    def _toggle_teleport(self, state):
        enabled = bool(state)
        self.canvas.set_teleport(enabled)
        self.status_bar.showMessage("Teleport mode " + ("ON" if enabled else "OFF") + ".")

    # ------------------------------------------------------------------
    # Terrain actions
    # ------------------------------------------------------------------

    def _on_terrain_type_changed(self, name: str):
        color = TERRAIN_COLORS.get(name, "#ffffff")
        self.terrain_swatch.setStyleSheet(
            f"background:{color};border:1px solid #888;"
        )
        if self.terrain_paint_btn.isChecked():
            self.canvas.set_terrain_paint(True, name)

    def _on_terrain_paint_toggled(self, enabled: bool):
        terrain = self.terrain_combo.currentText()
        self.canvas.set_terrain_paint(enabled, terrain)
        if enabled:
            self.status_bar.showMessage(
                f"Terrain Paint: {terrain} — "
                f"click/drag to paint · Shift+click to flood-fill · "
                f"right-click to erase · Shift+right to flood-erase · P to exit"
            )
        else:
            self.status_bar.showMessage("Terrain Paint: OFF")

    def _clear_selected_terrain(self):
        """Clear terrain from the hex the selected entity or location is on,
        or from the canvas mouse-hover position (rough fallback)."""
        # Prefer the currently selected entity's node
        sel = self.canvas._selected_entity
        if sel:
            self.tm.clear(sel.node)
            self.canvas.refresh()
            self.status_bar.showMessage(f"Terrain cleared at node {sel.node}.")
            return
        self.status_bar.showMessage(
            "Select an entity or use right-click in Paint mode to erase terrain."
        )

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
                location_type=v["location_type"],
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
        # Pre-select the current location type in the combo
        idx = dlg.type_combo.findData(loc.location_type)
        if idx >= 0:
            dlg.type_combo.setCurrentIndex(idx)
        if dlg.exec():
            v = dlg.get_values()
            self.lm.update(lid, name=v["name"], node=v["node"],
                           color=v["color"], description=v["description"],
                           location_type=v["location_type"])
            self._refresh_locations()
            self.canvas.refresh()
            self.status_bar.showMessage(f"Location '{v['name']}' updated.")

    def _refresh_locations(self):
        self.location_list.clear()
        for loc in self.lm.all:
            type_tag = f"  [{loc.location_type}]" if loc.location_type else ""
            item = QListWidgetItem(f"{loc.name}{type_tag}  → {loc.node}")
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
        type_line = f"\nType: {loc.location_type}" if loc.location_type else ""
        desc_line = f"\n{loc.description}" if loc.description else ""
        self.info_label.setText(f"Location: {loc.name}\nNode: {loc.node}{type_line}{desc_line}")
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
            "day": self.day,
            "grid": {
                "size": self.grid.size,
                "origin": list(self.grid.origin),
                "orientation": self.grid.orientation,
                "cols": self.grid.cols,
                "rows": self.grid.rows,
                # warp_corners is None when no bilinear warp has been applied
                "warp_corners": (
                    [list(c) for c in self.grid.get_warp_corners()]
                    if self.grid.is_warped else None
                ),
            },
            "entities": [
                {
                    "id": e.id,
                    "name": e.name,
                    "node": e.node,
                    "color": e.color,
                    "is_group": e.is_group,
                    "is_bot": e.is_bot,
                    "members": list(e.members),
                    "seafaring": e.seafaring,
                    "bot_target": e.bot_target,
                    "flavor_text": e.flavor_text,
                }
                for e in self.em.all
            ],
            "locations": self.lm.to_list(),
            "terrain": self.tm.to_dict(),
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
            # Restore warp corners AFTER reconfigure() (which resets them)
            wc = g.get("warp_corners")
            if wc is not None:
                self.grid.set_warp_corners(*[tuple(c) for c in wc])
            for e in self.em.all:
                self.em.remove(e.id)
            for ed in data["entities"]:
                self.em.add(
                    Entity(
                        name=ed["name"],
                        node=ed["node"],
                        color=ed["color"],
                        is_group=ed.get("is_group", False),
                        is_bot=ed.get("is_bot", False),
                        members=list(ed.get("members", [])),
                        seafaring=ed.get("seafaring", False),
                        bot_target=ed.get("bot_target"),
                        flavor_text=ed.get("flavor_text", ""),
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
                        location_type=ld.get("location_type", ""),
                        id=ld["id"],
                    )
                )
            # Restore terrain (mutate in-place so canvas ref stays valid)
            self.tm.clear_all()
            for k, v in TerrainMap.from_dict(data.get("terrain", {}))._data.items():
                self.tm.set(k, v)
            self.day = data.get("day", 1)
            self.canvas.clear_moved()
            self._bonus_move_entity = None
            self.canvas.set_selected(None)
            self.canvas.set_highlighted_location(-1)
            self._refresh_list()
            self._refresh_locations()
            self._update_day_ui()
            self.canvas.refresh()
            self.status_bar.showMessage(f"Loaded: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", f"Could not load state:\n{exc}")

    # ------------------------------------------------------------------
    # Canvas / list sync
    # ------------------------------------------------------------------

    def _refresh_list(self):
        self.entity_list.clear()
        for e in self.em.toplevel:
            tags = []
            if e.is_group:
                tags.append("G")
            if e.is_bot:
                tags.append("B")
            if e.seafaring:
                tags.append("S")
            prefix = f"[{'|'.join(tags)}] " if tags else ""
            cnt = f"  ({len(e.members)} mbr)" if e.is_group and e.members else ""
            acted = e.id in self.canvas._moved_ids
            bonus = (e.id == self._bonus_move_entity)
            turn_mark = " ✓" if acted else (" ★" if bonus else "")
            item = QListWidgetItem(f"{prefix}{e.name}{cnt}  → {e.node}{turn_mark}")
            item.setData(Qt.ItemDataRole.UserRole, e.id)
            color = QColor(e.color)
            if acted:
                color.setAlpha(140)
            item.setForeground(color)
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
            if entity.is_group:
                mbr_names = ", ".join(
                    self.em.get(mid).name
                    for mid in entity.members
                    if self.em.get(mid)
                )
                kind_line = f"Group ({len(entity.members)} members)"
                mbr_line = f"\nMembers: {mbr_names}" if mbr_names else ""
            else:
                kind_line = "Bot" if entity.is_bot else "Character"
                mbr_line = ""

            # Trait badges
            traits = []
            if getattr(entity, "seafaring", False):
                traits.append("Seafaring")
            if entity.is_bot:
                traits.append("Bot")
            trait_line = f"\n{' · '.join(traits)}" if traits else ""

            # Bot target line (show location name if available, else node number)
            target_line = ""
            if entity.is_bot and entity.bot_target is not None:
                loc = next(
                    (l for l in self.lm.all if l.node == entity.bot_target), None
                )
                target_str = loc.name if loc else f"node {entity.bot_target}"
                target_line = f"\nTarget: {target_str}"

            # Flavor text
            flavor = getattr(entity, "flavor_text", "") or ""
            flavor_line = f"\n\n{flavor}" if flavor else ""

            self.info_label.setText(
                f"{kind_line}: {entity.name}\n"
                f"Node: {entity.node}"
                f"{trait_line}{mbr_line}{target_line}{flavor_line}"
            )
            for i in range(self.entity_list.count()):
                item = self.entity_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == entity.id:
                    self.entity_list.setCurrentItem(item)
                    break
        else:
            self.info_label.setText("None")

    def _on_move_requested(self, entity: Entity, target_node: int):
        is_bonus = (self._bonus_move_entity == entity.id)

        self.em.move(entity.id, target_node)
        self._check_merge_opportunity(target_node, entity)

        # If the entity merged into a group it's no longer top-level — clear bonus,
        # the new group starts its turn fresh.
        if self.em.is_group_member(entity.id):
            self._bonus_move_entity = None
            self._refresh_list()
            self._update_day_ui()
            return

        if is_bonus:
            # Player used the bonus move — turn fully done
            self._bonus_move_entity = None
            self.canvas.mark_moved(entity.id)
            self.canvas.set_selected(entity)
            self.status_bar.showMessage(
                f"'{entity.name}' used bonus move → node {target_node}.  "
                f"[{self._progress_str()}]"
            )
            self._check_day_end()
        else:
            if random.random() < 0.25:
                # Lucky extra move
                self._bonus_move_entity = entity.id
                self.canvas.set_selected(entity)    # not in moved_ids yet → targets shown
                self.status_bar.showMessage(
                    f"'{entity.name}' moved → node {target_node}.  "
                    f"Lucky! One extra move available — click target or press W to pass."
                )
            else:
                self._bonus_move_entity = None
                self.canvas.mark_moved(entity.id)
                self.canvas.set_selected(entity)
                self.status_bar.showMessage(
                    f"'{entity.name}' moved → node {target_node}.  [{self._progress_str()}]"
                )
                self._check_day_end()

        self._refresh_list()
        self._update_day_ui()

    # ------------------------------------------------------------------
    # Encounter dispatch  (Merge / Combat / Nothing)
    # ------------------------------------------------------------------

    def _check_merge_opportunity(self, node: int, moved: Entity):
        """
        Called after any manual move.  Delegates to the shared encounter
        resolver if two or more top-level entities now share the hex.
        """
        entities = self.em.at_node(node)
        if len(entities) >= 2:
            self._resolve_encounter_on_hex(node, entities)

    def _resolve_encounter_on_hex(self, node: int, entities: list):
        """
        Show the Merge / ⚔ Combat / Nothing prompt for all top-level
        entities currently on *node*.

        Called from both manual movement (_check_merge_opportunity) and
        bot movement (_move_all_bots), so the logic lives in one place.
        """
        if len(entities) < 2:
            return

        names_str = " &amp; ".join(e.name for e in entities)

        msg = QMessageBox(self)
        msg.setWindowTitle(f"Encounter — Hex {node}")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(
            f"<b>{names_str}</b><br>are on hex {node}.<br><br>What happens?"
        )
        merge_btn  = msg.addButton("Merge",      QMessageBox.ButtonRole.ActionRole)
        combat_btn = msg.addButton("⚔  Combat", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Nothing",                  QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        clicked = msg.clickedButton()

        if clicked == combat_btn:
            self._resolve_combat(node, entities)
            return                  # _resolve_combat handles its own refresh

        if clicked != merge_btn:
            self._refresh_list()
            self.canvas.refresh()
            return

        # ── Merge sub-dialog ──────────────────────────────────────
        groups_there = [e for e in entities if e.is_group]
        indivs_there = [e for e in entities if not e.is_group]

        if groups_there and indivs_there:
            # At least one existing group + loose entities → offer to add them in
            group = groups_there[0]
            add_names = ", ".join(e.name for e in indivs_there)
            plural = len(indivs_there) > 1
            ans = QMessageBox.question(
                self,
                "Join Group?",
                f"<b>{add_names}</b> {'are' if plural else 'is'} on the same hex "
                f"as group <b>{group.name}</b>.<br>"
                f"Add {'them' if plural else 'them'} to the group?",
            )
            if ans == QMessageBox.StandardButton.Yes:
                for e in indivs_there:
                    self.em.add_to_group(group.id, e.id)
                self.canvas.set_selected(group)

        elif len(indivs_there) >= 2:
            # All individuals — offer to form a new group
            names = " &amp; ".join(e.name for e in indivs_there)
            ans = QMessageBox.question(
                self,
                "Merge Into Group?",
                f"Multiple entities on hex {node}:<br><b>{names}</b>"
                f"<br><br>Merge them into a group?",
            )
            if ans == QMessageBox.StandardButton.Yes:
                default_name = " & ".join(e.name.split()[0] for e in indivs_there)
                group_name, ok = QInputDialog.getText(
                    self, "Group Name", "Name the new group:", text=default_name
                )
                if ok and group_name.strip():
                    new_group = self.em.merge_into_group(
                        [e.id for e in indivs_there],
                        group_name.strip(),
                        indivs_there[0].color,
                    )
                    self.canvas.set_selected(new_group)

        self._refresh_list()
        self.canvas.refresh()

    # ------------------------------------------------------------------
    # Combat resolution
    # ------------------------------------------------------------------

    def _resolve_combat(self, node: int, entities: list):
        """
        Open CombatDialog, then apply the result:
          - Winners stay on the hex untouched.
          - Losers are either moved to an adjacent hex or removed.
        """
        dlg = CombatDialog(entities, node, self)
        if not dlg.exec():
            self._refresh_list()
            self.canvas.refresh()
            return

        winner_ids = set(dlg.get_winner_ids())
        loser_action = dlg.get_loser_action()
        losers = [e for e in entities if e.id not in winner_ids]

        neighbors = self.grid.neighbor_numbers(node)
        # Build human-readable neighbor labels (include terrain type if set)
        neighbor_labels = []
        for n in neighbors:
            terrain = self.tm.get(n)
            label = f"{n}  [{terrain}]" if terrain else str(n)
            neighbor_labels.append((n, label))

        for loser in losers:
            if loser_action == "remove":
                self._remove_entity_and_members(loser)
                self.status_bar.showMessage(
                    f"'{loser.name}' was removed from the map after combat."
                )
            else:
                # Move — let the GM pick a destination
                if not neighbor_labels:
                    # Isolated hex — fall back to removal
                    self._remove_entity_and_members(loser)
                    self.status_bar.showMessage(
                        f"'{loser.name}' has nowhere to flee — removed."
                    )
                    continue

                options = [lbl for _, lbl in neighbor_labels]
                chosen, ok = QInputDialog.getItem(
                    self,
                    f"Move Loser — {loser.name}",
                    f"Move '<b>{loser.name}</b>' to which adjacent hex?\n"
                    f"(Currently on hex {node})",
                    options,
                    editable=False,
                )
                if ok:
                    # Parse the node number from the label string
                    dest_node = int(chosen.split()[0])
                    self.em.move(loser.id, dest_node)
                    self.status_bar.showMessage(
                        f"'{loser.name}' fled to hex {dest_node} after combat."
                    )
                else:
                    # GM cancelled the destination picker — leave in place
                    self.status_bar.showMessage(
                        f"'{loser.name}' stays on hex {node} (no destination chosen)."
                    )

        # Deselect if the selected entity no longer exists
        sel = self.canvas._selected_entity
        if sel and self.em.get(sel.id) is None:
            self.canvas.set_selected(None)

        self._refresh_list()
        self._update_day_ui()
        self.canvas.refresh()

    def _remove_entity_and_members(self, entity: Entity):
        """
        Remove an entity from the map.  For groups, all members are also
        removed.  Clears the entity from any active turn-tracking state.
        """
        # Clear turn state
        self.canvas._moved_ids.discard(entity.id)
        if self._bonus_move_entity == entity.id:
            self._bonus_move_entity = None

        if entity.is_group:
            for mid in list(entity.members):
                self.canvas._moved_ids.discard(mid)
                self.em.remove(mid)
        self.em.remove(entity.id)

    # ------------------------------------------------------------------
    # Day / turn system
    # ------------------------------------------------------------------

    def _progress_str(self) -> str:
        entities = self.em.toplevel
        n = sum(1 for e in entities if e.id in self.canvas._moved_ids)
        return f"{n}/{len(entities)} acted"

    def _update_day_ui(self):
        entities = self.em.toplevel
        n = sum(1 for e in entities if e.id in self.canvas._moved_ids)
        self.day_label.setText(f"Day {self.day}")
        self.day_progress_label.setText(f"{n} / {len(entities)} acted")

    def _on_entity_wait(self):
        """End the selected entity's turn in place (skips or ends bonus move)."""
        e = self.canvas._selected_entity
        if e is None or e.id in self.canvas._moved_ids:
            return
        self._bonus_move_entity = None
        self.canvas.mark_moved(e.id)
        self.canvas.set_selected(e)          # keep selected, targets cleared
        self.status_bar.showMessage(
            f"'{e.name}' is waiting.  [{self._progress_str()}]"
        )
        self._refresh_list()
        self._update_day_ui()
        self._check_day_end()

    def _check_day_end(self):
        entities = self.em.toplevel
        if not entities:
            return
        if all(e.id in self.canvas._moved_ids for e in entities):
            self._request_day_advance()

    def _request_day_advance(self):
        """All entities have acted — ask the GM whether to advance the day."""
        self.status_bar.showMessage(
            f"All entities have acted on Day {self.day}.  "
            f"Advance to Day {self.day + 1}?"
        )
        ans = QMessageBox.question(
            self,
            "Advance Day?",
            f"All entities have acted.\n\nAdvance to Day {self.day + 1}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self._advance_day()
        else:
            self.status_bar.showMessage(
                f"Day {self.day} held — click Advance Day when ready."
            )

    def _advance_day(self):
        """Increment day and reset all turn state."""
        self.day += 1
        self.canvas.clear_moved()
        self._bonus_move_entity = None
        self.canvas.set_selected(None)
        self._refresh_list()
        self._update_day_ui()
        self.status_bar.showMessage(
            f"All entities have acted — Day {self.day} has begun!"
        )

    def _advance_day_manual(self):
        """Manual 'Advance Day' button — advances regardless of who has acted."""
        self._advance_day()

    # ------------------------------------------------------------------
    # Bot auto-movement
    # ------------------------------------------------------------------

    def _water_blocked_nodes(self) -> set[int]:
        """Return the set of all Ocean/Rivers hex nodes (used for terrain gating)."""
        from canvas import WATER_TERRAINS
        return {
            cell.number
            for cell in self.grid.all_cells
            if self.tm.get(cell.number) in WATER_TERRAINS
        }

    def _random_passable_neighbor(self, node: int, blocked: set[int]) -> Optional[int]:
        """
        Return a random neighbor of *node* that is not in *blocked*, or None
        if every neighbor is blocked (or the node has no neighbors).
        Used for the 'lost' wandering mechanic.
        """
        choices = [
            n for n in self.grid.neighbor_numbers(node)
            if n not in blocked
        ]
        return random.choice(choices) if choices else None

    def _move_all_bots(self):
        """
        Move every top-level bot one step toward its target (25 % bonus step).

        Each individual step (main and bonus) has an independent 25 % chance
        of the bot becoming 'lost' — it wanders to a random adjacent passable
        hex instead of following its planned path.

        After all bots have moved, any hexes where a bot landed alongside
        other entities are resolved as standard encounters (Merge / Combat /
        Nothing), one at a time.  If there are multiple encounters a summary
        is shown first so the GM knows what to expect.
        """
        bots = [e for e in self.em.toplevel if e.is_bot]
        moved_count = 0
        lost_count = 0
        all_water = self._water_blocked_nodes()

        # Track the final position of each bot that actually moves,
        # preserving encounter order and deduplicating same-node arrivals.
        encounter_candidates: list[int] = []
        seen_dest: set[int] = set()

        for bot in bots:
            if bot.id in self.canvas._moved_ids:
                continue

            if bot.bot_target is None or bot.node == bot.bot_target:
                self.canvas.mark_moved(bot.id)
                continue

            blocked = set() if bot.seafaring else all_water

            # ── Main step: 25 % chance of wandering (lost) ───────────
            if random.random() < 0.25:
                next_node = self._random_passable_neighbor(bot.node, blocked)
                if next_node is not None:
                    lost_count += 1          # only count if there was somewhere to go
            else:
                next_node = find_next_step(
                    self.grid, bot.node, bot.bot_target, blocked=blocked
                )

            if next_node is None:
                self.canvas.mark_moved(bot.id)
                continue

            self.em.move(bot.id, next_node)
            moved_count += 1

            # ── Bonus step (25 % chance), also subject to lost roll ───
            if random.random() < 0.25:
                if random.random() < 0.25:
                    bonus = self._random_passable_neighbor(bot.node, blocked)
                    if bonus is not None:
                        lost_count += 1
                else:
                    bonus = find_next_step(
                        self.grid, bot.node, bot.bot_target, blocked=blocked
                    )
                if bonus is not None:
                    self.em.move(bot.id, bonus)

            self.canvas.mark_moved(bot.id)

            # Record destination (bot.node is now the final position)
            dest = bot.node
            if dest not in seen_dest:
                seen_dest.add(dest)
                encounter_candidates.append(dest)

        # Refresh display before any encounter dialogs
        self.canvas.set_selected(None)
        self._refresh_list()
        self._update_day_ui()
        self.canvas.refresh()

        # Build the ordered list of hexes that actually have encounters
        pending: list[int] = [
            n for n in encounter_candidates
            if len(self.em.at_node(n)) > 1
        ]

        if not pending:
            if moved_count:
                lost_note = f", {lost_count} lost" if lost_count else ""
                self.status_bar.showMessage(
                    f"Bots moved: {moved_count}{lost_note}  [{self._progress_str()}]"
                )
            else:
                self.status_bar.showMessage(
                    f"No bots needed to move.  [{self._progress_str()}]"
                )
            self._check_day_end()
            return

        # ── One or more encounters to resolve ────────────────────────
        lost_note = f", {lost_count} lost" if lost_count else ""
        if len(pending) == 1:
            node = pending[0]
            self.status_bar.showMessage(
                f"Bots moved: {moved_count}{lost_note} — encounter on hex {node}."
            )
            entities = self.em.at_node(node)
            if len(entities) > 1:
                self._resolve_encounter_on_hex(node, entities)
        else:
            # Show a summary list first so the GM knows what's coming
            lines = []
            for n in pending:
                ents = self.em.at_node(n)
                if len(ents) > 1:
                    lines.append(
                        f"  Hex {n}:  "
                        + "  &amp;  ".join(e.name for e in ents)
                    )

            if lines:
                summary_msg = QMessageBox(self)
                summary_msg.setWindowTitle("Bot Movement — Encounters")
                summary_msg.setTextFormat(Qt.TextFormat.RichText)
                lost_line = (
                    f"<br><small><i>{lost_count} step(s) were lost wandering.</i></small>"
                    if lost_count else ""
                )
                summary_msg.setText(
                    f"Bot movement caused <b>{len(lines)} encounter(s)</b>.{lost_line}<br>"
                    f"They will be resolved one at a time.<br><br>"
                    + "<br>".join(lines)
                )
                resolve_btn = summary_msg.addButton(
                    "Resolve All", QMessageBox.ButtonRole.AcceptRole
                )
                skip_btn = summary_msg.addButton(
                    "Skip All", QMessageBox.ButtonRole.RejectRole
                )
                summary_msg.exec()

                if summary_msg.clickedButton() == skip_btn:
                    self._check_day_end()
                    return

            # Process sequentially; re-check each hex in case earlier
            # combat resolution already removed or moved some entities.
            total = len(pending)
            for i, node in enumerate(pending, 1):
                entities = self.em.at_node(node)
                if len(entities) > 1:
                    self.status_bar.showMessage(
                        f"Encounter {i} of {total} — Hex {node}"
                    )
                    self._resolve_encounter_on_hex(node, entities)

        self._check_day_end()

    # ------------------------------------------------------------------
    # Right-click entity editor
    # ------------------------------------------------------------------

    def _on_right_click_entity(self, entity: Entity):
        if entity.is_group:
            self._edit_group(entity)
        else:
            self._edit_individual(entity)

    def _edit_individual(self, entity: Entity):
        dlg = EditEntityDialog(entity, self, lm=self.lm, max_node=self.grid.max_number)
        if dlg.exec():
            v = dlg.get_values()
            entity.name = v["name"]
            entity.color = v["color"]
            entity.is_bot = v["is_bot"]
            entity.seafaring = v["seafaring"]
            entity.bot_target = v["bot_target"]
            entity.flavor_text = v["flavor_text"]
            self._refresh_list()
            self._on_entity_selected(entity)   # refresh info panel
            # Recalculate valid targets in case seafaring changed
            if self.canvas._selected_entity and self.canvas._selected_entity.id == entity.id:
                self.canvas.set_selected(entity)
            self.canvas.refresh()
            self.status_bar.showMessage(f"'{entity.name}' updated.")

    def _edit_group(self, group: Entity):
        dlg = EditGroupDialog(group, self.em, self, lm=self.lm, max_node=self.grid.max_number)
        if dlg.exec():
            if dlg.should_disband():
                self.em.disband_group(group.id)
                self.canvas.set_selected(None)
                self.status_bar.showMessage(f"Group '{group.name}' disbanded.")
            else:
                v = dlg.get_values()
                group.name = v["name"]
                group.is_bot = v["is_bot"]
                group.seafaring = v["seafaring"]
                group.bot_target = v["bot_target"]
                group.flavor_text = v["flavor_text"]
                # Apply member changes
                new_members = set(v["members"])
                old_members = set(group.members)
                for eid in old_members - new_members:
                    self.em.remove_from_group(group.id, eid)
                for eid in new_members - old_members:
                    self.em.add_to_group(group.id, eid)
                self.canvas.set_selected(group)
                self._on_entity_selected(group)   # refresh info panel
                self.status_bar.showMessage(f"Group '{group.name}' updated.")
        self._refresh_list()
        self.canvas.refresh()
