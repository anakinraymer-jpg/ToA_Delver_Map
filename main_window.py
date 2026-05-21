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
    QSpinBox,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from canvas import CanvasMode, HexMapCanvas
from dialogs import AddEntityDialog
from entities import Entity, EntityManager
from node_map import NodeMap

CHULT_MAP_FILE = "chult_map.png"
# Adjacent hex centres on the Chult map are ~150.7 px apart at 4476×6000.
# 200 px safely captures neighbours (150.7 px) while excluding 2-step hexes (301 px).
CHULT_ADJ_DISTANCE = 200.0

# Calibrated hex-grid constants kept for "Generate all nodes" feature only.
CHULT_GRID = dict(size=87.0, origin=(150.0, 138.0), orientation="flat", cols=33, rows=39)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ToA Delver Map")
        self.resize(1280, 820)

        self.node_map = NodeMap(adj_distance=CHULT_ADJ_DISTANCE)
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

        self.canvas = HexMapCanvas(self.node_map, self.em)
        self.canvas.entity_selected.connect(self._on_entity_selected)
        self.canvas.move_requested.connect(self._on_move_requested)
        self.canvas.node_count_changed.connect(self._on_node_count_changed)

        panel = self._build_panel()
        root.addWidget(self.canvas, 1)
        root.addWidget(panel)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def _build_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(245)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Mode toggle ──────────────────────────────────────────────
        mode_grp = QGroupBox("Mode")
        ml = QHBoxLayout(mode_grp)
        self.edit_btn = QPushButton("✏  Edit Map")
        self.play_btn = QPushButton("▶  Play")
        self.edit_btn.setCheckable(True)
        self.play_btn.setCheckable(True)
        self.edit_btn.clicked.connect(lambda: self._set_mode(CanvasMode.EDIT))
        self.play_btn.clicked.connect(lambda: self._set_mode(CanvasMode.PLAY))
        ml.addWidget(self.edit_btn)
        ml.addWidget(self.play_btn)

        # ── Edit panel ───────────────────────────────────────────────
        self.edit_panel = QGroupBox("Node Placement")
        ep = QVBoxLayout(self.edit_panel)

        self.node_count_label = QLabel("Nodes placed: 0")

        hint_edit = QLabel(
            "<small>"
            "Left-click empty space → place node<br>"
            "Left-drag existing node → reposition<br>"
            "Right-click existing node → delete"
            "</small>"
        )
        hint_edit.setWordWrap(True)

        clear_btn = QPushButton("Clear All Nodes")
        clear_btn.clicked.connect(self._clear_nodes)

        adj_row = QHBoxLayout()
        adj_row.addWidget(QLabel("Adj. distance:"))
        self.adj_spin = QSpinBox()
        self.adj_spin.setRange(50, 1000)
        self.adj_spin.setValue(int(CHULT_ADJ_DISTANCE))
        self.adj_spin.setSuffix(" px")
        self.adj_spin.valueChanged.connect(self._on_adj_changed)
        adj_row.addWidget(self.adj_spin)

        self.show_conn_check = QCheckBox("Show connections")
        self.show_conn_check.setChecked(True)
        self.show_conn_check.stateChanged.connect(
            lambda s: self.canvas.set_show_connections(bool(s))
        )

        ep.addWidget(self.node_count_label)
        ep.addWidget(hint_edit)
        ep.addWidget(clear_btn)
        ep.addLayout(adj_row)
        ep.addWidget(self.show_conn_check)

        # ── Play panel ───────────────────────────────────────────────
        self.play_panel = QWidget()
        pp = QVBoxLayout(self.play_panel)
        pp.setContentsMargins(0, 0, 0, 0)
        pp.setSpacing(6)

        eg = QGroupBox("Characters & Groups")
        eg_l = QVBoxLayout(eg)
        self.entity_list = QListWidget()
        self.entity_list.itemClicked.connect(self._on_list_click)
        eg_l.addWidget(self.entity_list)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._add_entity)
        rm_btn = QPushButton("Remove")
        rm_btn.clicked.connect(self._remove_selected_entity)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(rm_btn)
        eg_l.addLayout(btn_row)

        ig = QGroupBox("Selected")
        ig_l = QVBoxLayout(ig)
        self.info_label = QLabel("None")
        self.info_label.setWordWrap(True)
        ig_l.addWidget(self.info_label)

        self.teleport_check = QCheckBox("Teleport Mode")
        self.teleport_check.stateChanged.connect(self._toggle_teleport)

        hint_play = QLabel(
            "<small>"
            "Left-click entity → select<br>"
            "Left-click green node → move<br>"
            "Right-click / Esc → deselect<br>"
            "Middle-drag → pan  ·  Scroll → zoom"
            "</small>"
        )
        hint_play.setWordWrap(True)

        pp.addWidget(eg)
        pp.addWidget(ig)
        pp.addWidget(self.teleport_check)
        pp.addWidget(hint_play)

        # ── Overlay (always visible) ─────────────────────────────────
        ov_grp = QGroupBox("Overlay")
        og = QVBoxLayout(ov_grp)
        self.opacity_label = QLabel("Opacity: 78%")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 255)
        self.opacity_slider.setValue(200)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        og.addWidget(self.opacity_label)
        og.addWidget(self.opacity_slider)

        layout.addWidget(mode_grp)
        layout.addWidget(self.edit_panel)
        layout.addWidget(self.play_panel)
        layout.addWidget(ov_grp)
        layout.addStretch()

        # Default to Play mode
        self._set_mode(CanvasMode.PLAY)
        return panel

    def _build_menu(self):
        menu = self.menuBar()

        file_menu = menu.addMenu("File")

        open_act = QAction("Open Map Image…", self)
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self._open_map)
        file_menu.addAction(open_act)

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

        gen_act = QAction("Generate All Nodes from Chult Grid…", self)
        gen_act.triggered.connect(self._generate_chult_nodes)
        map_menu.addAction(gen_act)

    def _build_toolbar(self):
        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)

        open_act = QAction("Open Map", self)
        open_act.triggered.connect(self._open_map)
        tb.addAction(open_act)

        tb.addSeparator()

        edit_act = QAction("✏ Edit Mode", self)
        edit_act.triggered.connect(lambda: self._set_mode(CanvasMode.EDIT))
        tb.addAction(edit_act)

        play_act = QAction("▶ Play Mode", self)
        play_act.triggered.connect(lambda: self._set_mode(CanvasMode.PLAY))
        tb.addAction(play_act)

        tb.addSeparator()

        desel_act = QAction("Deselect  [Esc]", self)
        desel_act.setShortcut("Escape")
        desel_act.triggered.connect(lambda: self.canvas.set_selected(None))
        tb.addAction(desel_act)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _set_mode(self, mode: CanvasMode):
        self.edit_btn.setChecked(mode == CanvasMode.EDIT)
        self.play_btn.setChecked(mode == CanvasMode.PLAY)
        self.edit_panel.setVisible(mode == CanvasMode.EDIT)
        self.play_panel.setVisible(mode == CanvasMode.PLAY)
        self.canvas.set_mode(mode)
        if mode == CanvasMode.EDIT:
            self.status_bar.showMessage(
                f"Edit mode  |  {self.node_map.count} nodes  |  "
                "Left-click: add  ·  Drag: move  ·  Right-click: delete"
            )
        else:
            self.status_bar.showMessage(
                f"Play mode  |  {self.node_map.count} nodes  |  "
                "Click an entity to select, then click a highlighted node to move."
            )

    def _auto_load_map(self):
        if os.path.isfile(CHULT_MAP_FILE):
            self.canvas.load_image(CHULT_MAP_FILE)
            self.status_bar.showMessage(
                f"Chult map loaded  |  {self.node_map.count} nodes  |  "
                "Switch to Edit mode to start placing movement nodes."
            )

    def _open_map(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Map Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tiff *.webp)",
        )
        if path:
            self.canvas.load_image(path)
            self.status_bar.showMessage(f"Map loaded: {path}")

    def _clear_nodes(self):
        if self.node_map.count == 0:
            return
        if QMessageBox.question(
            self, "Clear All Nodes",
            f"Delete all {self.node_map.count} nodes? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.node_map.clear()
            self.canvas.refresh()
            self.node_count_label.setText("Nodes placed: 0")
            self.status_bar.showMessage("All nodes cleared.")

    def _generate_chult_nodes(self):
        from hex_grid import HexGrid

        existing = self.node_map.count
        msg = (
            f"This will generate {CHULT_GRID['cols'] * CHULT_GRID['rows']} nodes "
            f"at every Chult hex centre."
        )
        if existing:
            msg += f"\n\nYou already have {existing} node(s). They will be kept; new nodes will be added."
        msg += "\n\nContinue?"

        if QMessageBox.question(
            self, "Generate Nodes", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        grid = HexGrid(**CHULT_GRID)
        for cell in grid.all_cells:
            px, py = grid.hex_to_pixel(cell.q, cell.r)
            self.node_map.add_node(px, py)

        self.canvas.refresh()
        total = self.node_map.count
        self.node_count_label.setText(f"Nodes placed: {total}")
        self.status_bar.showMessage(
            f"Generated {grid.max_number} nodes from Chult grid  |  Total: {total}"
        )

    def _on_adj_changed(self, value: int):
        self.node_map.set_adj_distance(float(value))
        self.canvas.refresh()

    def _on_opacity_changed(self, value: int):
        pct = round(value / 255 * 100)
        self.opacity_label.setText(f"Opacity: {pct}%")
        self.canvas.set_grid_opacity(value)

    def _on_node_count_changed(self, count: int):
        self.node_count_label.setText(f"Nodes placed: {count}")
        self.status_bar.showMessage(
            f"Edit mode  |  {count} nodes  |  "
            "Left-click: add  ·  Drag: move  ·  Right-click: delete"
        )

    def _add_entity(self):
        if self.node_map.count == 0:
            QMessageBox.information(
                self, "No Nodes",
                "Place movement nodes on the map first (switch to Edit mode)."
            )
            return
        dlg = AddEntityDialog(self.node_map.max_number, self)
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
        self.status_bar.showMessage("Teleport mode " + ("ON." if enabled else "OFF."))

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------

    def _save_state(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save State", "", "JSON (*.json)")
        if not path:
            return
        data = {
            "node_map": self.node_map.to_dict(),
            "entities": [
                {
                    "id": e.id, "name": e.name, "node": e.node,
                    "color": e.color, "is_group": e.is_group,
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

            loaded_nm = NodeMap.from_dict(data["node_map"])
            self.node_map._nodes = loaded_nm._nodes
            self.node_map._next_number = loaded_nm._next_number
            self.node_map.adj_distance = loaded_nm.adj_distance
            self.node_map._cache.clear()
            self.adj_spin.setValue(int(self.node_map.adj_distance))
            self.node_count_label.setText(f"Nodes placed: {self.node_map.count}")

            for e in self.em.all:
                self.em.remove(e.id)
            for ed in data.get("entities", []):
                self.em.add(Entity(
                    name=ed["name"], node=ed["node"],
                    color=ed["color"], is_group=ed["is_group"], id=ed["id"],
                ))

            self.canvas.set_selected(None)
            self._refresh_list()
            self.canvas.refresh()
            self.status_bar.showMessage(
                f"Loaded: {path}  |  {self.node_map.count} nodes"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", f"Could not load state:\n{exc}")

    # ------------------------------------------------------------------
    # List / canvas sync
    # ------------------------------------------------------------------

    def _refresh_list(self):
        self.entity_list.clear()
        for e in self.em.all:
            prefix = "[G] " if e.is_group else ""
            item = QListWidgetItem(f"{prefix}{e.name}  → node {e.node}")
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
