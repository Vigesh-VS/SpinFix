# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""First-run welcome: 3 steps on how to use Spinfix + "Start with Windows?"."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from spinfix.app import theme
from spinfix.core.settings import store

STEPS = (
    ("1", "Start dragging a file", "in File Explorer or on the Desktop."),
    ("2", "Press Shift", "while you're still dragging. A wheel appears."),
    ("3", "Drop it on a slice", "The result is saved next to the original."),
)


class Welcome(QDialog):
    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowTitle("Welcome to Spinfix")
        self.setWindowIcon(theme.app_icon())
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        head = QHBoxLayout()
        logo = QLabel()
        pix = theme.logo_pixmap()
        if not pix.isNull():
            logo.setPixmap(
                pix.scaled(
                    64,
                    64,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        head.addWidget(logo)
        title = QLabel(
            "<b style='font-size:16pt'>Spin. Drop. Fixed.</b><br>"
            "<span style='color:#A8A49C'>Convert, compress or fix any file "
            "— offline.</span>"
        )
        head.addWidget(title, 1)
        lay.addLayout(head)

        for num, bold, rest in STEPS:
            row = QHBoxLayout()
            badge = QLabel(num)
            badge.setFixedSize(28, 28)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet("background:#FF5514; border-radius:14px; font-weight:bold;")
            row.addWidget(badge)
            row.addWidget(QLabel(f"<b>{bold}</b> {rest}"), 1)
            lay.addLayout(row)

        tip = QLabel(
            "No drag? Select files and press <b>Ctrl + Alt + Space</b>, or "
            "double-click the tray icon."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#A8A49C;")
        lay.addWidget(tip)

        self.startup = QCheckBox("Start Spinfix when I sign in to Windows")
        lay.addWidget(self.startup)

        go = QPushButton("Got it")
        go.setProperty("accent", True)
        go.setDefault(True)
        go.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(go)
        lay.addLayout(row)

    def accept(self) -> None:
        if self.startup.isChecked():
            from spinfix.platform.windows.shell import set_start_with_windows  # noqa: PLC0415

            try:
                set_start_with_windows(True)
                store.update(start_with_windows=True)
            except OSError:
                pass
        store.update(first_run_done=True)
        super().accept()
