# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Settings window (all P1 settings, saved instantly) and the About box."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from spinfix import __version__
from spinfix.app import theme
from spinfix.app.hotkey import parse_hotkey
from spinfix.core.settings import store


class SettingsWindow(QDialog):
    def __init__(self, on_change: Callable[[], None]) -> None:
        super().__init__(None)
        self.on_change = on_change
        self.setWindowTitle("Spinfix — Settings")
        self.setWindowIcon(theme.app_icon())
        self.setMinimumWidth(460)
        s = store.get()
        lay = QVBoxLayout(self)
        form = QFormLayout()
        lay.addLayout(form)

        self.trigger = QComboBox()
        for key, label in (("shift", "Shift"), ("ctrl", "Ctrl"), ("alt", "Alt")):
            self.trigger.addItem(label, key)
        self.trigger.setCurrentIndex(max(0, self.trigger.findData(s.trigger_key)))
        self.trigger.currentIndexChanged.connect(
            lambda: self._set(trigger_key=self.trigger.currentData())
        )
        form.addRow("Key to press while dragging", self.trigger)

        self.hotkey = QLineEdit(s.hotkey)
        self.hotkey.setPlaceholderText("ctrl+alt+space")
        self.hotkey.editingFinished.connect(self._hotkey_changed)
        form.addRow("Hotkey for selected files", self.hotkey)

        self.output = QComboBox()
        self.output.addItem("Next to the original", "next_to")
        self.output.addItem("In a “Spinfix” subfolder", "subfolder")
        self.output.setCurrentIndex(max(0, self.output.findData(s.output_mode)))
        self.output.currentIndexChanged.connect(
            lambda: self._set(output_mode=self.output.currentData())
        )
        form.addRow("Save results", self.output)

        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setValue(s.jpeg_quality)
        self.quality.valueChanged.connect(lambda v: self._set(jpeg_quality=v))
        form.addRow("JPG / WEBP quality", self.quality)

        self.dpi = QSpinBox()
        self.dpi.setRange(36, 600)
        self.dpi.setSuffix(" dpi")
        self.dpi.setValue(s.pdf_dpi)
        self.dpi.valueChanged.connect(lambda v: self._set(pdf_dpi=v))
        form.addRow("PDF → image sharpness", self.dpi)

        self.meta_convert = self._check(
            "Keep photo info (EXIF) when converting",
            s.keep_metadata_on_convert,
            "keep_metadata_on_convert",
        )
        self.meta_compress = self._check(
            "Keep photo info when compressing",
            s.keep_metadata_on_compress,
            "keep_metadata_on_compress",
        )
        self.toasts = self._check(
            "Show a message when a job finishes", s.show_toasts, "show_toasts"
        )
        for box in (self.meta_convert, self.meta_compress, self.toasts):
            form.addRow("", box)

        self.startup = QCheckBox("Start Spinfix when I sign in to Windows")
        self.startup.setChecked(s.start_with_windows)
        self.startup.toggled.connect(self._startup_changed)
        form.addRow("", self.startup)

        ff = QHBoxLayout()
        self.ffmpeg = QLineEdit(s.ffmpeg_path)
        self.ffmpeg.setPlaceholderText("Found automatically (winget install Gyan.FFmpeg)")
        self.ffmpeg.editingFinished.connect(self._ffmpeg_changed)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_ffmpeg)
        ff.addWidget(self.ffmpeg, 1)
        ff.addWidget(browse)
        holder = QWidget()
        holder.setLayout(ff)
        ff.setContentsMargins(0, 0, 0, 0)
        form.addRow("FFmpeg (for video)", holder)

        self.ffmpeg_status = QLabel()
        self.ffmpeg_status.setStyleSheet("color: #A8A49C;")
        form.addRow("", self.ffmpeg_status)
        self._refresh_ffmpeg()

        close = QPushButton("Done")
        close.setProperty("accent", True)
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)

    def _check(self, text: str, value: bool, key: str) -> QCheckBox:
        box = QCheckBox(text)
        box.setChecked(value)
        box.toggled.connect(lambda v: self._set(**{key: v}))
        return box

    def _set(self, **changes: object) -> None:
        store.update(**changes)
        self.on_change()

    def _hotkey_changed(self) -> None:
        text = self.hotkey.text().strip().lower()
        if parse_hotkey(text) is None:
            QMessageBox.warning(self, "Spinfix", "Use something like ctrl+alt+space.")
            self.hotkey.setText(store.get().hotkey)
            return
        self._set(hotkey=text)

    def _startup_changed(self, enabled: bool) -> None:
        from spinfix.platform.windows.shell import set_start_with_windows  # noqa: PLC0415

        try:
            set_start_with_windows(enabled)
        except OSError:
            QMessageBox.warning(self, "Spinfix", "Couldn't change the startup setting.")
            return
        self._set(start_with_windows=enabled)

    def _browse_ffmpeg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Find ffmpeg.exe", "", "ffmpeg.exe")
        if path:
            self.ffmpeg.setText(path)
            self._ffmpeg_changed()

    def _ffmpeg_changed(self) -> None:
        self._set(ffmpeg_path=self.ffmpeg.text().strip())
        self._refresh_ffmpeg()

    def _refresh_ffmpeg(self) -> None:
        from spinfix.actions.media import find_ffmpeg  # noqa: PLC0415

        found = find_ffmpeg(refresh=True)
        self.ffmpeg_status.setText(
            f"Using {found}" if found else "Not found. Install with: winget install Gyan.FFmpeg"
        )


ABOUT = f"""<h3>Spinfix {__version__}</h3>
<p><b>Spin. Drop. Fixed.</b><br>Drag a file, press Shift, drop it on a wheel.</p>
<p>Everything runs on your PC. Nothing is uploaded. No account, no ads, no tracking.</p>
<p>Copyright (c) 2026 Vigesh · MIT License<br>
<a href="https://github.com/Vigesh-VS/SpinFix">github.com/Vigesh-VS/SpinFix</a></p>
<p style="color:#A8A49C">Inspired by the open-source projects Ryshift, DragShift and McGyver.
Third-party licences are listed in THIRD_PARTY_NOTICES.md.</p>"""


def show_about() -> None:
    box = QMessageBox()
    box.setWindowTitle("About Spinfix")
    box.setWindowIcon(theme.app_icon())
    box.setTextFormat(Qt.TextFormat.RichText)
    box.setText(ABOUT)
    logo = theme.logo_pixmap()
    if not logo.isNull():
        box.setIconPixmap(
            logo.scaled(
                72,
                72,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    box.exec()
