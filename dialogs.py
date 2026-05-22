from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)


class GridSettingsDialog(QDialog):
    """
    Live-preview grid settings dialog.
    Emits `settings_changed` on every control change so the caller can
    apply updates to the canvas in real-time.  Original values are stored
    so the caller can restore them if the user cancels.
    """
    settings_changed = pyqtSignal(dict)

    def __init__(self, grid, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Grid Settings")
        layout = QFormLayout(self)

        # Store originals for cancel-restore
        self._original = {
            "size": grid.size,
            "origin": grid.origin,
            "cols": grid.cols,
            "rows": grid.rows,
            "orientation": grid.orientation,
        }

        self.hex_size = QDoubleSpinBox()
        self.hex_size.setRange(10, 300)
        self.hex_size.setValue(grid.size)
        self.hex_size.setSuffix(" px")
        self.hex_size.setSingleStep(0.5)

        self.origin_x = QDoubleSpinBox()
        self.origin_x.setRange(-9999, 9999)
        self.origin_x.setValue(grid.origin[0])
        self.origin_x.setSingleStep(1.0)

        self.origin_y = QDoubleSpinBox()
        self.origin_y.setRange(-9999, 9999)
        self.origin_y.setValue(grid.origin[1])
        self.origin_y.setSingleStep(1.0)

        self.cols = QSpinBox()
        self.cols.setRange(1, 200)
        self.cols.setValue(grid.cols)

        self.rows = QSpinBox()
        self.rows.setRange(1, 200)
        self.rows.setValue(grid.rows)

        self.orientation = QComboBox()
        self.orientation.addItems(["flat", "pointy"])
        self.orientation.setCurrentText(grid.orientation)

        layout.addRow("Hex Size:", self.hex_size)
        layout.addRow("Origin X:", self.origin_x)
        layout.addRow("Origin Y:", self.origin_y)
        layout.addRow("Columns:", self.cols)
        layout.addRow("Rows:", self.rows)
        layout.addRow("Orientation:", self.orientation)

        note = QLabel("<small><i>Changes preview live on the map.</i></small>")
        layout.addRow(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        # Wire every control to emit a live preview
        self.hex_size.valueChanged.connect(self._emit)
        self.origin_x.valueChanged.connect(self._emit)
        self.origin_y.valueChanged.connect(self._emit)
        self.cols.valueChanged.connect(self._emit)
        self.rows.valueChanged.connect(self._emit)
        self.orientation.currentTextChanged.connect(self._emit)

    def _emit(self):
        self.settings_changed.emit(self.get_values())

    def get_values(self) -> dict:
        return {
            "size": self.hex_size.value(),
            "origin": (self.origin_x.value(), self.origin_y.value()),
            "cols": self.cols.value(),
            "rows": self.rows.value(),
            "orientation": self.orientation.currentText(),
        }

    def get_original(self) -> dict:
        return self._original

    def set_origin(self, x: float, y: float):
        """Called externally when the user clicks a hex centre on the map."""
        self.origin_x.setValue(x)
        self.origin_y.setValue(y)


class AddEntityDialog(QDialog):
    def __init__(self, max_node: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Character / Group")
        self._color = "#e74c3c"
        layout = QFormLayout(self)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Name")

        self.node_spin = QSpinBox()
        self.node_spin.setRange(1, max_node)

        self.is_group = QCheckBox("This is a group")
        self.is_bot = QCheckBox("This is a bot")
        self.seafaring = QCheckBox("Seafaring  (can enter Ocean / Rivers)")

        color_row = QHBoxLayout()
        self._preview = QLabel()
        self._preview.setFixedSize(24, 24)
        self._preview.setStyleSheet(f"background:{self._color};border:1px solid #888;")
        pick_btn = QPushButton("Pick Color")
        pick_btn.clicked.connect(self._pick_color)
        color_row.addWidget(self._preview)
        color_row.addWidget(pick_btn)
        color_row.addStretch()

        layout.addRow("Name:", self.name_edit)
        layout.addRow("Starting Node:", self.node_spin)
        layout.addRow("Color:", color_row)
        layout.addRow("", self.is_group)
        layout.addRow("", self.is_bot)
        layout.addRow("", self.seafaring)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._color), self)
        if c.isValid():
            self._color = c.name()
            self._preview.setStyleSheet(f"background:{self._color};border:1px solid #888;")

    def _on_accept(self):
        if not self.name_edit.text().strip():
            self.name_edit.setFocus()
            return
        self.accept()

    def get_values(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "node": self.node_spin.value(),
            "color": self._color,
            "is_group": self.is_group.isChecked(),
            "is_bot": self.is_bot.isChecked(),
            "seafaring": self.seafaring.isChecked(),
        }


# ---------------------------------------------------------------------------
# Edit individual entity (name / color / bot flag / flavor text / bot target)
# ---------------------------------------------------------------------------

class EditEntityDialog(QDialog):
    def __init__(self, entity, parent=None, *, lm=None, max_node: int = 9999):
        super().__init__(parent)
        self.setWindowTitle(f"Edit: {entity.name}")
        self._color = entity.color
        self._lm = lm
        # Internal storage for the resolved target node (set by combo selection)
        self._current_target: Optional[int] = getattr(entity, "bot_target", None)

        root = QVBoxLayout(self)
        root.setSpacing(8)
        layout = QFormLayout()
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        root.addLayout(layout)

        self.name_edit = QLineEdit(entity.name)

        color_row = QHBoxLayout()
        self._preview = QLabel()
        self._preview.setFixedSize(24, 24)
        self._preview.setStyleSheet(f"background:{self._color};border:1px solid #888;")
        pick_btn = QPushButton("Pick Color")
        pick_btn.clicked.connect(self._pick_color)
        color_row.addWidget(self._preview)
        color_row.addWidget(pick_btn)
        color_row.addStretch()

        self.is_bot = QCheckBox("This is a bot")
        self.is_bot.setChecked(entity.is_bot)

        self.seafaring = QCheckBox("Seafaring  (can enter Ocean / Rivers)")
        self.seafaring.setChecked(getattr(entity, "seafaring", False))

        # Flavor / notes text
        self.flavor_edit = QPlainTextEdit()
        self.flavor_edit.setPlaceholderText("Optional notes, backstory, or flavor…")
        self.flavor_edit.setFixedHeight(72)
        self.flavor_edit.setPlainText(getattr(entity, "flavor_text", "") or "")

        layout.addRow("Name:", self.name_edit)
        layout.addRow("Color:", color_row)
        layout.addRow("", self.is_bot)
        layout.addRow("", self.seafaring)
        layout.addRow("Notes:", self.flavor_edit)

        # ── Bot Target ────────────────────────────────────────────────
        self._target_group = QGroupBox("Bot Target")
        tg_layout = QFormLayout(self._target_group)
        tg_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self._target_loc_combo = QComboBox()
        self._target_loc_combo.addItem("— No target —", None)
        if lm:
            for loc in lm.all:
                self._target_loc_combo.addItem(f"{loc.name}  (node {loc.node})", loc.node)

        # Pre-select the matching location if one is already assigned
        if lm and self._current_target is not None:
            for i in range(self._target_loc_combo.count()):
                if self._target_loc_combo.itemData(i) == self._current_target:
                    self._target_loc_combo.setCurrentIndex(i)
                    break

        self._target_loc_combo.currentIndexChanged.connect(self._on_loc_selected)
        tg_layout.addRow("Move toward:", self._target_loc_combo)

        self._target_group.setEnabled(entity.is_bot)
        self.is_bot.toggled.connect(self._target_group.setEnabled)
        root.addWidget(self._target_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_loc_selected(self, idx: int):
        self._current_target = self._target_loc_combo.itemData(idx)

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._color), self)
        if c.isValid():
            self._color = c.name()
            self._preview.setStyleSheet(f"background:{self._color};border:1px solid #888;")

    def _on_accept(self):
        if not self.name_edit.text().strip():
            self.name_edit.setFocus()
            return
        self.accept()

    def get_values(self) -> dict:
        bot_target: Optional[int] = self._current_target if self.is_bot.isChecked() else None
        return {
            "name": self.name_edit.text().strip(),
            "color": self._color,
            "is_bot": self.is_bot.isChecked(),
            "seafaring": self.seafaring.isChecked(),
            "bot_target": bot_target,
            "flavor_text": self.flavor_edit.toPlainText().strip(),
        }


# ---------------------------------------------------------------------------
# Edit group — name / bot flag / member management
# ---------------------------------------------------------------------------

class EditGroupDialog(QDialog):
    """
    Lets the user rename the group, toggle bot, and move entities on the same
    hex into or out of the group.  Changes are staged locally and applied by
    the caller only when the dialog is accepted.
    """

    def __init__(self, group, em, parent=None, *, lm=None, max_node: int = 9999):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Group: {group.name}")
        self._group = group
        self._em = em
        self._lm = lm
        self._disband = False

        # Local working copies — not applied until OK
        self._members: list[str] = list(group.members)
        # Available = top-level entities at the group's node (not the group itself)
        self._available: list[str] = [
            e.id for e in em.at_node(group.node) if e.id != group.id
        ]

        # Internal storage for the resolved target node
        self._current_target: Optional[int] = getattr(group, "bot_target", None)

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # --- Header row: name + bot + seafaring ---
        hdr = QFormLayout()
        hdr.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.name_edit = QLineEdit(group.name)
        self.is_bot = QCheckBox("Bot group")
        self.is_bot.setChecked(group.is_bot)
        self.seafaring = QCheckBox("Seafaring  (can enter Ocean / Rivers)")
        self.seafaring.setChecked(getattr(group, "seafaring", False))
        hdr.addRow("Group Name:", self.name_edit)
        hdr.addRow("", self.is_bot)
        hdr.addRow("", self.seafaring)
        root.addLayout(hdr)

        # --- Dual-pane member editor ---
        panels = QHBoxLayout()

        members_box = QGroupBox("Group Members")
        ml = QVBoxLayout(members_box)
        self.members_list = QListWidget()
        ml.addWidget(self.members_list)
        remove_btn = QPushButton("Remove from Group →")
        remove_btn.clicked.connect(self._remove_member)
        ml.addWidget(remove_btn)

        avail_box = QGroupBox("On Same Hex")
        al = QVBoxLayout(avail_box)
        self.avail_list = QListWidget()
        al.addWidget(self.avail_list)
        add_btn = QPushButton("← Add to Group")
        add_btn.clicked.connect(self._add_member)
        al.addWidget(add_btn)

        panels.addWidget(members_box)
        panels.addWidget(avail_box)
        root.addLayout(panels)

        # --- Flavor / notes ---
        flavor_form = QFormLayout()
        flavor_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.flavor_edit = QPlainTextEdit()
        self.flavor_edit.setPlaceholderText("Optional notes, backstory, or flavor…")
        self.flavor_edit.setFixedHeight(72)
        self.flavor_edit.setPlainText(getattr(group, "flavor_text", "") or "")
        flavor_form.addRow("Notes:", self.flavor_edit)
        root.addLayout(flavor_form)

        # --- Bot Target section ---
        self._target_group = QGroupBox("Bot Target")
        tg_layout = QFormLayout(self._target_group)
        tg_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self._target_loc_combo = QComboBox()
        self._target_loc_combo.addItem("— No target —", None)
        if lm:
            for loc in lm.all:
                self._target_loc_combo.addItem(f"{loc.name}  (node {loc.node})", loc.node)

        if lm and self._current_target is not None:
            for i in range(self._target_loc_combo.count()):
                if self._target_loc_combo.itemData(i) == self._current_target:
                    self._target_loc_combo.setCurrentIndex(i)
                    break

        self._target_loc_combo.currentIndexChanged.connect(self._on_loc_selected)
        tg_layout.addRow("Move toward:", self._target_loc_combo)

        self._target_group.setEnabled(group.is_bot)
        self.is_bot.toggled.connect(self._target_group.setEnabled)

        root.addWidget(self._target_group)

        # --- Disband + OK/Cancel ---
        disband_btn = QPushButton("Disband Group")
        disband_btn.setStyleSheet("color: #e74c3c;")
        disband_btn.clicked.connect(self._on_disband)
        root.addWidget(disband_btn)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._populate()

    # ------------------------------------------------------------------

    def _on_loc_selected(self, idx: int):
        self._current_target = self._target_loc_combo.itemData(idx)

    def _populate(self):
        self.members_list.clear()
        self.avail_list.clear()
        for eid in self._members:
            e = self._em.get(eid)
            if e:
                self._add_row(self.members_list, e)
        for eid in self._available:
            e = self._em.get(eid)
            if e:
                self._add_row(self.avail_list, e)

    @staticmethod
    def _add_row(lst: QListWidget, entity):
        flags = []
        if entity.is_bot:
            flags.append("BOT")
        if entity.is_group:
            flags.append("GRP")
        tag = f"[{'/'.join(flags)}] " if flags else ""
        item = QListWidgetItem(f"{tag}{entity.name}")
        item.setData(Qt.ItemDataRole.UserRole, entity.id)
        item.setForeground(QColor(entity.color))
        lst.addItem(item)

    def _add_member(self):
        item = self.avail_list.currentItem()
        if not item:
            return
        eid = item.data(Qt.ItemDataRole.UserRole)
        if eid in self._available:
            self._available.remove(eid)
        if eid not in self._members:
            self._members.append(eid)
        self._populate()

    def _remove_member(self):
        item = self.members_list.currentItem()
        if not item:
            return
        eid = item.data(Qt.ItemDataRole.UserRole)
        if eid in self._members:
            self._members.remove(eid)
        if eid not in self._available:
            self._available.append(eid)
        self._populate()

    def _on_disband(self):
        self._disband = True
        self.accept()

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def should_disband(self) -> bool:
        return self._disband

    def get_values(self) -> dict:
        bot_target: Optional[int] = self._current_target if self.is_bot.isChecked() else None
        return {
            "name": self.name_edit.text().strip() or self._group.name,
            "is_bot": self.is_bot.isChecked(),
            "seafaring": self.seafaring.isChecked(),
            "members": list(self._members),        # desired final member list
            "bot_target": bot_target,
            "flavor_text": self.flavor_edit.toPlainText().strip(),
        }


# ---------------------------------------------------------------------------
# Combat resolution dialog
# ---------------------------------------------------------------------------

class CombatDialog(QDialog):
    """
    Presented when entities share a hex and the GM chooses Combat.

    The GM checks off the Winner(s); every unchecked entity is a Loser.
    A radio button group determines what happens to Losers:
      - "Move away"  → main window will ask for a destination per loser
      - "Remove"     → entity (and group members) are deleted from the map
    """

    def __init__(self, entities: list, node: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"⚔  Combat — Hex {node}")
        self.setMinimumWidth(380)
        self._entities = entities

        root = QVBoxLayout(self)
        root.setSpacing(10)

        header = QLabel(
            f"<b>Combat on hex {node}</b><br>"
            "<small>Check the <b>Winner(s)</b>. "
            "Unchecked entities are <b>Losers</b>.</small>"
        )
        header.setWordWrap(True)
        root.addWidget(header)

        # ── Checkable entity list ────────────────────────────────────
        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        for e in entities:
            if e.is_group:
                kind = f"Group · {len(e.members)} member{'s' if len(e.members) != 1 else ''}"
            elif e.is_bot:
                kind = "Bot"
            else:
                kind = "Character"
            item = QListWidgetItem(f"  {e.name}   [{kind}]")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, e.id)
            item.setForeground(QColor(e.color))
            self._list.addItem(item)
        root.addWidget(self._list)

        # ── Loser fate ───────────────────────────────────────────────
        fate_box = QGroupBox("Fate of Loser(s)")
        fate_layout = QVBoxLayout(fate_box)
        self._radio_move = QRadioButton(
            "Move to an adjacent hex  (you'll choose destination next)"
        )
        self._radio_remove = QRadioButton(
            "Remove from the map  (defeated / slain)"
        )
        self._radio_move.setChecked(True)
        fate_layout.addWidget(self._radio_move)
        fate_layout.addWidget(self._radio_remove)
        root.addWidget(fate_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ------------------------------------------------------------------

    def _on_accept(self):
        winners = self.get_winner_ids()
        if not winners:
            QMessageBox.warning(
                self, "No Winner Selected",
                "Please check at least one entity as the winner."
            )
            return
        if len(winners) == self._list.count():
            QMessageBox.warning(
                self, "No Loser",
                "At least one entity must be a loser — uncheck one."
            )
            return
        self.accept()

    def get_winner_ids(self) -> list:
        """IDs of entities marked as winners (checked)."""
        return [
            self._list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._list.count())
            if self._list.item(i).checkState() == Qt.CheckState.Checked
        ]

    def get_loser_ids(self) -> list:
        """IDs of entities NOT marked as winners."""
        return [
            self._list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._list.count())
            if self._list.item(i).checkState() != Qt.CheckState.Checked
        ]

    def get_loser_action(self) -> str:
        """'move' or 'remove'."""
        return "move" if self._radio_move.isChecked() else "remove"


class AddLocationDialog(QDialog):
    """Dialog for placing a named location on a specific hex node."""

    def __init__(self, max_node: int, parent=None, *, preset_node: int = 1):
        super().__init__(parent)
        self.setWindowTitle("Add Location")
        self._color = "#f39c12"
        layout = QFormLayout(self)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Port Nyanzaru")

        self.node_spin = QSpinBox()
        self.node_spin.setRange(1, max_node)
        self.node_spin.setValue(preset_node)

        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setPlaceholderText("Optional notes about this location")
        self.desc_edit.setFixedHeight(60)

        color_row = QHBoxLayout()
        self._preview = QLabel()
        self._preview.setFixedSize(24, 24)
        self._preview.setStyleSheet(f"background:{self._color};border:1px solid #888;")
        pick_btn = QPushButton("Pick Color")
        pick_btn.clicked.connect(self._pick_color)
        color_row.addWidget(self._preview)
        color_row.addWidget(pick_btn)
        color_row.addStretch()

        layout.addRow("Name:", self.name_edit)
        layout.addRow("Hex Node:", self.node_spin)
        layout.addRow("Description:", self.desc_edit)
        layout.addRow("Color:", color_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._color), self)
        if c.isValid():
            self._color = c.name()
            self._preview.setStyleSheet(f"background:{self._color};border:1px solid #888;")

    def _on_accept(self):
        if not self.name_edit.text().strip():
            self.name_edit.setFocus()
            return
        self.accept()

    def get_values(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "node": self.node_spin.value(),
            "color": self._color,
            "description": self.desc_edit.toPlainText().strip(),
        }
