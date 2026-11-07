# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Small dialogs that ask for an action's option (target size, size, pages)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from spinfix.app import theme
from spinfix.core.registry import Action, Options


class _Ask(QDialog):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Spinfix — {title}")
        self.setWindowIcon(theme.app_icon())
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.layout_ = QVBoxLayout(self)
        self.form = QFormLayout()
        self.layout_.addLayout(self.form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.layout_.addWidget(buttons)

    def hint(self, text: str) -> None:
        label = QLabel(text)
        label.setStyleSheet("color: #A8A49C;")
        label.setWordWrap(True)
        self.layout_.insertWidget(0, label)


def ask_options(action: Action, file_count: int) -> Options | None:
    """Show the dialog the action needs. None means the user cancelled."""
    if action.asks == "target_size":
        dlg = _Ask(action.title)
        edit = QLineEdit("200 KB")
        dlg.form.addRow("Make it under", edit)
        dlg.hint("Type a size such as 200 KB, 50 KB or 1.5 MB.")
        if dlg.exec() == QDialog.DialogCode.Accepted and edit.text().strip():
            return {"target_size": edit.text()}
        return None
    if action.asks == "size":
        dlg = _Ask(action.title)
        width, height = QSpinBox(), QSpinBox()
        for box in (width, height):
            box.setRange(0, 30000)
            box.setSuffix(" px")
            box.setSpecialValueText("auto")
        width.setValue(1280)
        dlg.form.addRow("Width", width)
        dlg.form.addRow("Height", height)
        dlg.hint("Leave one as “auto” to keep the shape.")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return {"width": width.value(), "height": height.value()}
        return None
    if action.asks == "pages":
        dlg = _Ask(action.title)
        edit = QLineEdit("1")
        dlg.form.addRow("Pages", edit)
        dlg.hint("For example: 1-3, 5, 8-  (8- means 8 to the end).")
        if dlg.exec() == QDialog.DialogCode.Accepted and edit.text().strip():
            return {"pages": edit.text()}
        return None
    return {}
