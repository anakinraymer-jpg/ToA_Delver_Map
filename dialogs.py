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
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
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
        }


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
