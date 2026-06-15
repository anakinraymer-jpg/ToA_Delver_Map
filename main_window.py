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

WEATHER_CONDITIONS: list[str] = [
    "Misty",
    "Heavy Mist",
    "Dry and Sunny",
    "Sunny with Rain Showers",
    "Rainy",
    "Heavy Rain",
    "Tropical Storm",
    "Extremely Warm",
    "Monsoon Shift",
]

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
from terrain import TerrainMap


class MainWindow(QMainWindow):
    def __init__(self, *, player_name: str = ""):
        super().__init__()
        self.setWindowTitle("RPG Hex Map Tool")
        self.resize(1280, 820)
        self.player_name: str = player_name  # character-sheet PC name, may be empty

        self.grid = HexGrid(**CHULT_GRID)
        self.em = EntityManager()
        self.lm = LocationManager()
        self.day: int = 1
        self._bonus_move_entity: Optional[str] = None   # ID of entity with unused bonus move
        self.current_weather: str = ""
        self.tm = TerrainMap()

        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self.canvas.fog_enabled = True   # player map — fog of war always on
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
        outer.setFixedWidth(300)
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
        edit_day_btn = QPushButton("Edit")
        edit_day_btn.setToolTip("Manually set the current day number")
        edit_day_btn.clicked.connect(self._edit_day)
        day_btn_row.addWidget(wait_btn)
        day_btn_row.addWidget(adv_btn)
        day_btn_row.addWidget(edit_day_btn)
        dg.addWidget(self.day_label)
        dg.addWidget(self.day_progress_label)
        dg.addLayout(day_btn_row)

        # ── Weather ───────────────────────────────────────────────────
        wg = QGroupBox("Weather")
        wg_layout = QVBoxLayout(wg)
        weather_row = QHBoxLayout()
        self.weather_combo = QComboBox()
        self.weather_combo.addItem("— None —", "")
        for w in WEATHER_CONDITIONS:
            self.weather_combo.addItem(w, w)
        self.weather_combo.currentIndexChanged.connect(self._on_weather_changed)
        roll_btn = QPushButton("Roll")
        roll_btn.setToolTip("Randomly pick a weather condition for today")
        roll_btn.clicked.connect(self._roll_weather)
        weather_row.addWidget(self.weather_combo, 1)
        weather_row.addWidget(roll_btn)
        wg_layout.addLayout(weather_row)

        # ── Characters & Groups ───────────────────────────────────────
        eg = QGroupBox("Characters & Groups")
        eg_layout = QVBoxLayout(eg)
        self.entity_list = QListWidget()
        self.entity_list.setMaximumHeight(130)
        self.entity_list.itemClicked.connect(self._on_list_click)
        eg_layout.addWidget(self.entity_list)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._add_entity)
        edit_entity_btn = QPushButton("Edit")
        edit_entity_btn.setToolTip(
            "Edit selected character/group: name, color, seafaring, notes"
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

        # ── Group members ─────────────────────────────────────────────
        self.members_group = QGroupBox("Group Members")
        ml = QVBoxLayout(self.members_group)
        self.members_list = QListWidget()
        self.members_list.setMaximumHeight(90)
        ml.addWidget(self.members_list)
        self.members_group.setVisible(False)

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
            "<b>Keys:</b> W = Wait · Esc = Deselect"
            "</small>"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #999;")

        layout.addWidget(day_group)
        layout.addWidget(wg)
        layout.addWidget(eg)
        layout.addWidget(lg)
        layout.addWidget(ig)
        layout.addWidget(self.members_group)
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

        map_menu.addSeparator()
        reset_fog_act = QAction("Reset Fog of War", self)
        reset_fog_act.setToolTip(
            "Clear all revealed hexes and re-cover the map.  "
            "Current character positions are kept visible."
        )
        reset_fog_act.triggered.connect(self._reset_fog)
        map_menu.addAction(reset_fog_act)

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

    def _edit_day(self):
        val, ok = QInputDialog.getInt(
            self, "Edit Day", "Set current day:", self.day, 1, 9999
        )
        if ok:
            self.day = val
            self._update_day_ui()

    def _on_weather_changed(self, _idx: int):
        self.current_weather = self.weather_combo.currentData() or ""

    def _roll_weather(self):
        self.weather_combo.setCurrentIndex(
            random.randint(1, len(WEATHER_CONDITIONS))
        )

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

    def _reset_fog(self):
        """Clear all revealed hexes, then re-reveal current entity positions."""
        self.canvas._fog_revealed.clear()
        for e in self.em.toplevel:
            self.canvas._fog_revealed.add(e.node)
        self._refresh_locations()
        self.canvas.refresh()
        self.status_bar.showMessage("Fog of war reset — entity positions kept visible.")

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
        dlg = AddEntityDialog(self.grid.max_number, self, player_name=self.player_name)
        if dlg.exec():
            v = dlg.get_values()
            is_player = bool(
                self.player_name
                and v["name"].strip().lower() == self.player_name.strip().lower()
            )
            e = Entity(
                name=v["name"], node=v["node"], color=v["color"],
                is_group=v["is_group"],
                seafaring=v["seafaring"],
                is_player=is_player,
            )
            self.em.add(e)
            self.canvas.reveal_hex(e.node)   # always reveal starting hex
            self._refresh_locations()        # may expose a location
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
        """Rebuild the locations list — only shows locations on revealed hexes."""
        self.location_list.clear()
        revealed = self.canvas._fog_revealed
        for loc in self.lm.all:
            if loc.node not in revealed:
                continue   # still hidden by fog of war
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
                    "members": list(e.members),
                    "seafaring": e.seafaring,
                    "flavor_text": e.flavor_text,
                    "is_player": e.is_player,
                }
                for e in self.em.all
            ],
            "locations": self.lm.to_list(),
            "terrain": self.tm.to_dict(),
            "fog_revealed": sorted(self.canvas._fog_revealed),
            "weather": self.current_weather,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        self.status_bar.showMessage(f"Saved: {path}")

    def _write_player_location(self) -> None:
        """Write the player entity's hex node and terrain to the shared IPC file."""
        player = next((e for e in self.em.all if getattr(e, "is_player", False)), None)
        if player is None:
            return
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return
        folder = os.path.join(appdata, "ToA_CnS_CharacterSheet")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "player_location.json")
        terrain = self.tm.get(player.node) or ""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"node": player.node, "terrain": terrain}, f)
        except OSError:
            pass

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
                name = ed["name"]
                # Re-evaluate player flag against current character sheet name
                is_player = bool(
                    self.player_name
                    and name.strip().lower() == self.player_name.strip().lower()
                ) or ed.get("is_player", False)
                self.em.add(
                    Entity(
                        name=name,
                        node=ed["node"],
                        color=ed["color"],
                        is_group=ed.get("is_group", False),
                        members=list(ed.get("members", [])),
                        seafaring=ed.get("seafaring", False),
                        flavor_text=ed.get("flavor_text", ""),
                        is_player=is_player,
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
            self.current_weather = data.get("weather", "")
            idx = self.weather_combo.findData(self.current_weather)
            self.weather_combo.setCurrentIndex(max(0, idx))
            self.canvas.clear_moved()
            self._bonus_move_entity = None
            self.canvas.set_selected(None)
            # Restore fog-of-war revealed set; pre-reveal all entity positions
            revealed = set(data.get("fog_revealed", []))
            for e in self.em.toplevel:
                revealed.add(e.node)
            self.canvas._fog_revealed = revealed
            self.canvas.set_highlighted_location(-1)
            self._refresh_list()
            self._refresh_locations()
            self._update_day_ui()
            self.canvas.refresh()
            self._write_player_location()
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
            if e.seafaring:
                tags.append("S")
            player_mark = "★ " if getattr(e, "is_player", False) else ""
            prefix = f"[{'|'.join(tags)}] " if tags else ""
            cnt = f"  ({len(e.members)} mbr)" if e.is_group and e.members else ""
            acted = e.id in self.canvas._moved_ids
            bonus = (e.id == self._bonus_move_entity)
            turn_mark = " ✓" if acted else (" ●" if bonus else "")
            item = QListWidgetItem(f"{player_mark}{prefix}{e.name}{cnt}  → {e.node}{turn_mark}")
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
                kind_line = f"Group ({len(entity.members)} members)"
            else:
                kind_line = "Character"

            # Trait badges
            trait_line = "\nSea­faring" if getattr(entity, "seafaring", False) else ""

            # Flavor text
            flavor = getattr(entity, "flavor_text", "") or ""
            flavor_line = f"\n\n{flavor}" if flavor else ""

            self.info_label.setText(
                f"{kind_line}: {entity.name}\n"
                f"Node: {entity.node}"
                f"{trait_line}{flavor_line}"
            )
            for i in range(self.entity_list.count()):
                item = self.entity_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == entity.id:
                    self.entity_list.setCurrentItem(item)
                    break
        else:
            self.info_label.setText("None")

        # Populate group members list
        self.members_list.clear()
        if entity and entity.is_group:
            self.members_group.setVisible(True)
            for mid in entity.members:
                m = self.em.get(mid)
                if m:
                    tags = []
                    if getattr(m, "seafaring", False):
                        tags.append("Seafaring")
                    label = m.name
                    if tags:
                        label += f"  [{', '.join(tags)}]"
                    self.members_list.addItem(label)
        else:
            self.members_group.setVisible(False)

    def _on_move_requested(self, entity: Entity, target_node: int):
        is_bonus = (self._bonus_move_entity == entity.id)

        self.em.move(entity.id, target_node)
        if getattr(entity, "is_player", False):
            self._write_player_location()
        self.canvas.reveal_hex(target_node)   # all movement reveals the hex
        self._refresh_locations()             # may expose a new location
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

        Called from manual movement (_check_merge_opportunity).
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
            entity.seafaring = v["seafaring"]
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
                group.seafaring = v["seafaring"]
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
