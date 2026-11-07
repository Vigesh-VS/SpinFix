# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Colours, fonts and the app icon."""

from __future__ import annotations

import sys
from functools import cache
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QIcon, QPixmap

ORANGE = QColor(255, 85, 20)
ORANGE_SOFT = QColor(255, 85, 20, 60)
GLASS = QColor(16, 16, 20, 232)
GLASS_EDGE = QColor(255, 255, 255, 38)
SLICE = QColor(32, 32, 38, 235)
TEXT = QColor(250, 247, 240)
TEXT_DIM = QColor(250, 247, 240, 150)

STYLE = """
QWidget { color: #FAF7F0; font-family: 'Segoe UI'; font-size: 10pt; }
QDialog, QMainWindow { background: #141418; }
QPushButton { background: #26262D; border: 1px solid #3A3A44; border-radius: 6px;
              padding: 5px 12px; }
QPushButton:hover { border-color: #FF5514; }
QPushButton:default, QPushButton[accent="true"] { background: #FF5514; border-color: #FF5514;
              color: white; }
QLineEdit, QSpinBox, QComboBox { background: #1E1E24; border: 1px solid #3A3A44;
              border-radius: 5px; padding: 4px 6px; selection-background-color: #FF5514; }
QComboBox QAbstractItemView { background: #1E1E24; selection-background-color: #FF5514; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked { background: #FF5514; }
QProgressBar { background: #2A2A31; border: none; border-radius: 3px; height: 6px; }
QProgressBar::chunk { background: #FF5514; border-radius: 3px; }
QSlider::groove:horizontal { background: #2A2A31; height: 4px; border-radius: 2px; }
QSlider::handle:horizontal { background: #FF5514; width: 14px; margin: -6px 0;
              border-radius: 7px; }
QListWidget { background: #1E1E24; border: 1px solid #3A3A44; border-radius: 5px; }
QListWidget::item:selected { background: #FF5514; }
QMenu { background: #1E1E24; border: 1px solid #3A3A44; }
QMenu::item:selected { background: #FF5514; }
QToolButton { background: #26262D; border: 1px solid #3A3A44; border-radius: 6px;
              padding: 5px 8px; }
QToolButton:checked { background: #FF5514; border-color: #FF5514; }
QGroupBox { border: 1px solid #3A3A44; border-radius: 6px; margin-top: 12px; padding: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #FF8A5C; }
"""


def resource_root() -> Path:
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen)
    return Path(__file__).resolve().parents[2]


@cache
def logo_pixmap() -> QPixmap:
    return QPixmap(str(resource_root() / "assets" / "logo" / "spinfix-logo.png"))


@cache
def app_icon() -> QIcon:
    ico = resource_root() / "assets" / "spinfix.ico"
    if ico.exists():
        return QIcon(str(ico))
    return QIcon(logo_pixmap())


def font(size: float, bold: bool = False) -> QFont:
    f = QFont("Segoe UI")
    f.setPointSizeF(size)
    f.setBold(bold)
    return f
