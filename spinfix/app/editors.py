# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Editors: Crop, Edit, Annotate, Redact, Add background.

Each editor is a floating window. The result is saved as a new file (`name Cropped.jpg`…)
through the normal job pipeline, so the original is never touched.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from spinfix.actions import edit_ops
from spinfix.actions.images import INPUT_KINDS, encode, open_image, same_format
from spinfix.app import theme
from spinfix.core import safe_io
from spinfix.core.errors import UserError
from spinfix.core.filetype import FileInfo
from spinfix.core.limits import DEFAULT_LIMITS
from spinfix.core.registry import Action, JobContext, Options, Registry, Wheel

PREVIEW_MAX = 1600


def pil_to_qimage(img: Image.Image) -> QImage:
    rgba = img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    return QImage(
        data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888
    ).copy()


def qimage_to_pil(q: QImage) -> Image.Image:
    q = q.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h, bpl = q.width(), q.height(), q.bytesPerLine()
    data = bytes(q.constBits())[: bpl * h]
    return Image.frombuffer("RGBA", (w, h), data, "raw", "RGBA", bpl, 1).copy()


def preview_of(img: Image.Image) -> tuple[Image.Image, float]:
    """A downscaled copy for fast on-screen work, and its scale factor."""
    scale = min(1.0, PREVIEW_MAX / max(img.size))
    if scale >= 1.0:
        return img, 1.0
    return img.resize(
        (round(img.width * scale), round(img.height * scale)), Image.Resampling.BILINEAR
    ), scale


class Canvas(QWidget):
    """Shows an image scaled to fit; maps mouse positions to image pixels."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(560, 420)
        self.setMouseTracking(True)
        self.image = QImage()
        self.overlay: Callable[[QPainter], None] | None = None
        self.on_press: Callable[[QPointF], None] | None = None
        self.on_move: Callable[[QPointF, bool], None] | None = None
        self.on_release: Callable[[QPointF], None] | None = None
        self._down = False

    def set_image(self, image: QImage) -> None:
        self.image = image
        self.update()

    def target(self) -> QRectF:
        if self.image.isNull():
            return QRectF()
        iw, ih = self.image.width(), self.image.height()
        s = min((self.width() - 20) / iw, (self.height() - 20) / ih)
        w, h = iw * s, ih * s
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def scale(self) -> float:
        t = self.target()
        return t.width() / self.image.width() if self.image.width() else 1.0

    def to_image(self, pos: QPointF) -> QPointF:
        t = self.target()
        s = self.scale()
        x = min(max((pos.x() - t.x()) / s, 0), self.image.width())
        y = min(max((pos.y() - t.y()) / s, 0), self.image.height())
        return QPointF(x, y)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 — Qt override
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(12, 12, 15))
        if self.image.isNull():
            return
        t = self.target()
        # Checkerboard behind transparent images.
        p.fillRect(t, QBrush(QColor(60, 60, 66), Qt.BrushStyle.Dense4Pattern))
        p.drawImage(t, self.image)
        if self.overlay:
            p.translate(t.topLeft())
            p.scale(self.scale(), self.scale())
            self.overlay(p)
        p.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.on_press:
            self._down = True
            self.on_press(self.to_image(event.position()))
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self.on_move:
            self.on_move(self.to_image(event.position()), self._down)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._down:
            self._down = False
            if self.on_release:
                self.on_release(self.to_image(event.position()))
            self.update()


class EditorDialog(QDialog):
    label = "Edited"

    def __init__(self, img: Image.Image, title: str) -> None:
        super().__init__(None)
        self.setWindowTitle(f"Spinfix — {title}")
        self.setWindowIcon(theme.app_icon())
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint)
        self.resize(1000, 700)
        self.full = img
        self.preview, self.pscale = preview_of(img)
        self.result_image: Image.Image | None = None
        root = QHBoxLayout(self)
        self.canvas = Canvas()
        root.addWidget(self.canvas, 1)
        side = QVBoxLayout()
        self.panel = QFormLayout()
        side.addLayout(self.panel)
        side.addStretch(1)
        self.info = QLabel()
        self.info.setStyleSheet("color:#A8A49C;")
        side.addWidget(self.info)
        buttons = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save copy")
        save.setProperty("accent", True)
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        side.addLayout(buttons)
        holder = QWidget()
        holder.setLayout(side)
        holder.setFixedWidth(270)
        root.addWidget(holder)
        self.canvas.set_image(pil_to_qimage(self.preview))

    def _save(self) -> None:
        try:
            self.result_image = self.render_full()
        except ValueError as exc:
            self.info.setText(f"Can't save: {exc}")
            return
        self.accept()

    def render_full(self) -> Image.Image:
        raise NotImplementedError

    def to_full(self, v: float) -> int:
        return round(v / self.pscale)


# ------------------------------------------------------------------ Crop


class CropEditor(EditorDialog):
    label = "Cropped"

    def __init__(self, img: Image.Image) -> None:
        super().__init__(img, "Crop")
        self.ratio = QComboBox()
        self.ratio.addItems(list(edit_ops.RATIOS))
        self.ratio.currentTextChanged.connect(self._ratio_changed)
        self.panel.addRow("Shape", self.ratio)
        hint = QLabel("Drag on the picture to choose the area.")
        hint.setWordWrap(True)
        self.panel.addRow(hint)
        w, h = self.preview.size
        self.box = QRectF(w * 0.1, h * 0.1, w * 0.8, h * 0.8)
        self.start: QPointF | None = None
        self.canvas.overlay = self._draw
        self.canvas.on_press = self._press
        self.canvas.on_move = self._move
        self._update_info()

    def _ratio_changed(self) -> None:
        box = self._int_box()
        fitted = edit_ops.fit_ratio(
            box, edit_ops.RATIOS[self.ratio.currentText()], self.preview.size
        )
        self.box = QRectF(fitted[0], fitted[1], fitted[2] - fitted[0], fitted[3] - fitted[1])
        self._update_info()
        self.canvas.update()

    def _press(self, pos: QPointF) -> None:
        self.start = pos
        self.box = QRectF(pos, pos)

    def _move(self, pos: QPointF, down: bool) -> None:
        if not down or self.start is None:
            return
        ratio = edit_ops.RATIOS[self.ratio.currentText()]
        dx, dy = pos.x() - self.start.x(), pos.y() - self.start.y()
        if ratio:
            h = abs(dx) / ratio
            if h > abs(dy):
                dx = math.copysign(abs(dy) * ratio, dx)
            else:
                dy = math.copysign(h, dy)
        self.box = QRectF(self.start, QPointF(self.start.x() + dx, self.start.y() + dy))
        self.box = self.box.normalized()
        self._update_info()

    def _int_box(self) -> edit_ops.Box:
        b = self.box.normalized()
        return round(b.left()), round(b.top()), round(b.right()), round(b.bottom())

    def _update_info(self) -> None:
        b = self._int_box()
        self.info.setText(f"{self.to_full(b[2] - b[0])} x {self.to_full(b[3] - b[1])} px")

    def _draw(self, p: QPainter) -> None:
        w, h = self.preview.size
        shade = QPainterPath()
        shade.addRect(QRectF(0, 0, w, h))
        hole = QPainterPath()
        hole.addRect(self.box)
        p.fillPath(shade.subtracted(hole), QColor(0, 0, 0, 140))
        p.setPen(QPen(theme.ORANGE, 2 / max(self.canvas.scale(), 0.01)))
        p.drawRect(self.box)

    def render_full(self) -> Image.Image:
        b = self._int_box()
        return edit_ops.crop(self.full, tuple(self.to_full(v) for v in b))  # type: ignore[arg-type]


# ------------------------------------------------------------------ Edit


class AdjustEditor(EditorDialog):
    label = "Edited"

    def __init__(self, img: Image.Image) -> None:
        super().__init__(img, "Edit")
        self.adj = edit_ops.Adjustments()
        row = QHBoxLayout()
        for text, fn in (
            ("⟲", lambda: self._rotate(-90)),
            ("⟳", lambda: self._rotate(90)),
            ("⇋", self._flip_h),
            ("⇵", self._flip_v),
        ):
            b = QToolButton()
            b.setText(text)
            b.setFont(QFont("Segoe UI Symbol", 13))
            b.clicked.connect(fn)
            row.addWidget(b)
        holder = QWidget()
        holder.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        self.panel.addRow("Turn", holder)
        self.sliders: dict[str, QSlider] = {}
        for key, title in (
            ("brightness", "Brightness"),
            ("contrast", "Contrast"),
            ("saturation", "Colour"),
        ):
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(-100, 100)
            s.valueChanged.connect(self._schedule)
            self.sliders[key] = s
            self.panel.addRow(title, s)
        self.width_box = QSpinBox()
        self.width_box.setRange(0, 30000)
        self.width_box.setSpecialValueText("keep")
        self.width_box.setSuffix(" px")
        self.width_box.valueChanged.connect(self._schedule)
        self.panel.addRow("Width", self.width_box)
        reset = QPushButton("Reset")
        reset.clicked.connect(self._reset)
        self.panel.addRow(reset)
        self._timer = QTimer(self, singleShot=True, interval=60)
        self._timer.timeout.connect(self._refresh)
        self._refresh()

    def _rotate(self, deg: int) -> None:
        self.adj.rotate = (self.adj.rotate + deg) % 360
        self._refresh()

    def _flip_h(self) -> None:
        self.adj.flip_h = not self.adj.flip_h
        self._refresh()

    def _flip_v(self) -> None:
        self.adj.flip_v = not self.adj.flip_v
        self._refresh()

    def _reset(self) -> None:
        self.adj = edit_ops.Adjustments()
        for s in self.sliders.values():
            s.setValue(0)
        self.width_box.setValue(0)
        self._refresh()

    def _schedule(self) -> None:
        self._timer.start()

    def _current(self, width_scale: float) -> edit_ops.Adjustments:
        a = edit_ops.Adjustments(**vars(self.adj))
        a.brightness = self.sliders["brightness"].value()
        a.contrast = self.sliders["contrast"].value()
        a.saturation = self.sliders["saturation"].value()
        a.width = round(self.width_box.value() * width_scale)
        return a

    def _refresh(self) -> None:
        a = self._current(self.pscale)
        a.width = 0  # preview keeps its size
        out = edit_ops.adjust(self.preview, a)
        self.canvas.set_image(pil_to_qimage(out))
        turned = self.adj.rotate in (90, 270)
        w, h = (self.full.height, self.full.width) if turned else self.full.size
        if self.width_box.value():
            h = round(h * self.width_box.value() / w)
            w = self.width_box.value()
        self.info.setText(f"{w} x {h} px")

    def render_full(self) -> Image.Image:
        a = self._current(1.0)
        if a.width and a.width * a.width > DEFAULT_LIMITS.max_image_pixels:
            raise ValueError("that width is too large")
        return edit_ops.adjust(self.full, a)


# ------------------------------------------------------------------ Annotate


@dataclass
class Shape:
    tool: str
    color: QColor
    width: float
    points: list[QPointF] = field(default_factory=list)
    text: str = ""
    number: int = 0


SWATCHES = ("#FF5514", "#E53935", "#FDD835", "#43A047", "#1E88E5", "#FFFFFF", "#111111")


def draw_shape(p: QPainter, s: Shape) -> None:
    pen = QPen(
        s.color, s.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin
    )
    p.setBrush(Qt.BrushStyle.NoBrush)
    if s.tool in ("pen", "highlighter") and len(s.points) > 1:
        if s.tool == "highlighter":
            c = QColor(s.color)
            c.setAlpha(90)
            pen = QPen(
                c,
                s.width * 4,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.SquareCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        p.setPen(pen)
        path = QPainterPath(s.points[0])
        for pt in s.points[1:]:
            path.lineTo(pt)
        p.drawPath(path)
    elif s.tool == "box" and len(s.points) == 2:
        p.setPen(pen)
        p.drawRect(QRectF(s.points[0], s.points[1]).normalized())
    elif s.tool == "arrow" and len(s.points) == 2:
        a, b = s.points
        p.setPen(pen)
        p.drawLine(a, b)
        angle = math.atan2(b.y() - a.y(), b.x() - a.x())
        head = s.width * 4
        p.setBrush(s.color)
        p.drawPolygon(
            [
                b,
                QPointF(
                    b.x() - head * math.cos(angle - 0.45), b.y() - head * math.sin(angle - 0.45)
                ),
                QPointF(
                    b.x() - head * math.cos(angle + 0.45), b.y() - head * math.sin(angle + 0.45)
                ),
            ]
        )
    elif s.tool == "text" and s.points:
        f = QFont("Segoe UI", 1)
        f.setPixelSize(max(8, round(s.width * 6)))
        f.setBold(True)
        p.setFont(f)
        p.setPen(s.color)
        p.drawText(s.points[0], s.text)
    elif s.tool == "step" and s.points:
        r = s.width * 3.2
        centre = s.points[0]
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(s.color)
        p.drawEllipse(centre, r, r)
        f = QFont("Segoe UI", 1)
        f.setPixelSize(max(8, round(r * 1.1)))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("white") if s.color.lightness() < 160 else QColor("black"))
        p.drawText(
            QRectF(centre.x() - r, centre.y() - r, 2 * r, 2 * r),
            Qt.AlignmentFlag.AlignCenter,
            str(s.number),
        )


class AnnotateEditor(EditorDialog):
    label = "Annotated"
    TOOLS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("pen", "Pen"),
        ("arrow", "Arrow"),
        ("box", "Box"),
        ("highlighter", "Highlight"),
        ("text", "Text"),
        ("step", "Steps"),
    )

    def __init__(self, img: Image.Image) -> None:
        super().__init__(img, "Annotate")
        self.shapes: list[Shape] = []
        self.tool = "arrow"
        self.color = QColor(SWATCHES[0])
        group = QButtonGroup(self)
        grid = QVBoxLayout()
        for key, title in self.TOOLS:
            b = QToolButton()
            b.setText(title)
            b.setCheckable(True)
            b.setChecked(key == self.tool)
            b.clicked.connect(lambda _=False, k=key: setattr(self, "tool", k))
            group.addButton(b)
            grid.addWidget(b)
        holder = QWidget()
        holder.setLayout(grid)
        grid.setContentsMargins(0, 0, 0, 0)
        self.panel.addRow("Tool", holder)
        colors = QHBoxLayout()
        for hexcode in SWATCHES:
            swatch = QPushButton()
            swatch.setFixedSize(22, 22)
            swatch.setStyleSheet(
                f"background:{hexcode}; border:1px solid #555; border-radius:11px;"
            )
            swatch.clicked.connect(lambda _=False, h=hexcode: setattr(self, "color", QColor(h)))
            colors.addWidget(swatch)
        ch = QWidget()
        ch.setLayout(colors)
        colors.setContentsMargins(0, 0, 0, 0)
        self.panel.addRow("Colour", ch)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(1, 20)
        self.size_slider.setValue(5)
        self.panel.addRow("Size", self.size_slider)
        undo = QPushButton("Undo")
        undo.clicked.connect(self._undo)
        self.panel.addRow(undo)
        self.canvas.overlay = self._draw
        self.canvas.on_press = self._press
        self.canvas.on_move = self._move
        self.canvas.on_release = self._release
        self.info.setText("Draw on the picture.")

    def _width(self) -> float:
        # Size is relative to the picture so it looks the same on big and small images.
        return float(self.size_slider.value() * max(self.preview.size) / 900)

    def _press(self, pos: QPointF) -> None:
        if self.tool == "text":
            text, ok = QInputDialog.getText(self, "Spinfix", "Text:")
            if ok and text.strip():
                self.shapes.append(
                    Shape("text", QColor(self.color), self._width(), [pos], text=text.strip())
                )
            return
        if self.tool == "step":
            n = 1 + sum(1 for s in self.shapes if s.tool == "step")
            self.shapes.append(Shape("step", QColor(self.color), self._width(), [pos], number=n))
            return
        pts = [pos] if self.tool in ("pen", "highlighter") else [pos, pos]
        self.shapes.append(Shape(self.tool, QColor(self.color), self._width(), pts))

    def _move(self, pos: QPointF, down: bool) -> None:
        if not down or not self.shapes:
            return
        s = self.shapes[-1]
        if s.tool in ("pen", "highlighter"):
            s.points.append(pos)
        elif s.tool in ("arrow", "box"):
            s.points[1] = pos

    def _release(self, pos: QPointF) -> None:
        self._move(pos, True)

    def _undo(self) -> None:
        if self.shapes:
            self.shapes.pop()
            self.canvas.update()

    def _draw(self, p: QPainter) -> None:
        for s in self.shapes:
            draw_shape(p, s)

    def render_full(self) -> Image.Image:
        q = pil_to_qimage(self.full)
        p = QPainter(q)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.scale(1 / self.pscale, 1 / self.pscale)
        for s in self.shapes:
            draw_shape(p, s)
        p.end()
        out = qimage_to_pil(q)
        return out if self.full.mode == "RGBA" else out.convert("RGB")


# ------------------------------------------------------------------ Redact


class RedactEditor(EditorDialog):
    label = "Redacted"

    def __init__(self, img: Image.Image) -> None:
        super().__init__(img, "Redact")
        self.boxes: list[QRectF] = []
        self.start: QPointF | None = None
        self.mode = QComboBox()
        self.mode.addItem("Black box", "box")
        self.mode.addItem("Pixelate", "pixelate")
        self.mode.currentIndexChanged.connect(self._refresh)
        self.panel.addRow("Style", self.mode)
        undo = QPushButton("Undo")
        undo.clicked.connect(self._undo)
        self.panel.addRow(undo)
        note = QLabel(
            "The hidden pixels are really destroyed, and photo info is removed from the copy."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#A8A49C;")
        self.panel.addRow(note)
        self.canvas.overlay = self._draw
        self.canvas.on_press = self._press
        self.canvas.on_move = self._move
        self.canvas.on_release = self._release
        self.info.setText("Drag over anything private.")

    def _press(self, pos: QPointF) -> None:
        self.start = pos
        self.boxes.append(QRectF(pos, pos))

    def _move(self, pos: QPointF, down: bool) -> None:
        if down and self.start is not None and self.boxes:
            self.boxes[-1] = QRectF(self.start, pos).normalized()

    def _release(self, pos: QPointF) -> None:
        self._move(pos, True)
        self.start = None
        self._refresh()

    def _undo(self) -> None:
        if self.boxes:
            self.boxes.pop()
            self._refresh()

    def _int_boxes(self, scale: float) -> list[edit_ops.Box]:
        return [
            (
                round(b.left() / scale),
                round(b.top() / scale),
                round(b.right() / scale),
                round(b.bottom() / scale),
            )
            for b in self.boxes
        ]

    def _refresh(self) -> None:
        out = edit_ops.redact(self.preview, self._int_boxes(1.0), self.mode.currentData())
        self.canvas.set_image(pil_to_qimage(out))

    def _draw(self, p: QPainter) -> None:
        if self.start is not None and self.boxes:
            p.setPen(QPen(theme.ORANGE, 2 / max(self.canvas.scale(), 0.01), Qt.PenStyle.DashLine))
            p.drawRect(self.boxes[-1])

    def render_full(self) -> Image.Image:
        if not self.boxes:
            raise ValueError("nothing marked")
        return edit_ops.redact(self.full, self._int_boxes(self.pscale), self.mode.currentData())


# ------------------------------------------------------------------ Background


class BackgroundEditor(EditorDialog):
    label = "Background"

    def __init__(self, img: Image.Image) -> None:
        super().__init__(img, "Add background")
        self.bg = edit_ops.Background()
        self.style_box = QComboBox()
        self.style_box.addItems(list(edit_ops.GRADIENTS))
        self.style_box.currentTextChanged.connect(self._refresh)
        self.panel.addRow("Colours", self.style_box)
        self.padding = QSlider(Qt.Orientation.Horizontal)
        self.padding.setRange(0, 30)
        self.padding.setValue(self.bg.padding)
        self.padding.valueChanged.connect(self._schedule)
        self.panel.addRow("Padding", self.padding)
        self.radius = QSlider(Qt.Orientation.Horizontal)
        self.radius.setRange(0, 20)
        self.radius.setValue(self.bg.radius)
        self.radius.valueChanged.connect(self._schedule)
        self.panel.addRow("Corners", self.radius)
        self.shadow = QCheckBox("Shadow")
        self.shadow.setChecked(True)
        self.shadow.toggled.connect(self._refresh)
        self.panel.addRow(self.shadow)
        self.ratio = QComboBox()
        self.ratio.addItems(["Auto", "1:1", "4:5", "9:16", "16:9"])
        self.ratio.currentTextChanged.connect(self._refresh)
        self.panel.addRow("Shape", self.ratio)
        self._timer = QTimer(self, singleShot=True, interval=60)
        self._timer.timeout.connect(self._refresh)
        self._refresh()

    def _schedule(self) -> None:
        self._timer.start()

    def _current(self) -> edit_ops.Background:
        return edit_ops.Background(
            self.style_box.currentText(),
            self.padding.value(),
            self.radius.value(),
            self.shadow.isChecked(),
            self.ratio.currentText(),
        )

    def _refresh(self) -> None:
        out = edit_ops.add_background(self.preview, self._current())
        self.canvas.set_image(pil_to_qimage(out))
        full = edit_ops.add_background(self.full.resize((8, 8)), self._current())
        self.info.setText(f"Shape {full.width}:{full.height} (approx.)")

    def render_full(self) -> Image.Image:
        return edit_ops.add_background(self.full, self._current())


# ------------------------------------------------------------------ actions


EditorFactory = Callable[[Image.Image], EditorDialog]
EDITORS: dict[str, tuple[str, EditorFactory, int]] = {
    "edit.crop": ("Crop", CropEditor, 10),
    "edit.adjust": ("Edit", AdjustEditor, 20),
    "edit.annotate": ("Annotate", AnnotateEditor, 30),
    "edit.redact": ("Redact", RedactEditor, 40),
    "edit.background": ("Add background", BackgroundEditor, 50),
}


class SaveImage(Action):
    """Saves an editor's result next to the original (runs as a normal job)."""

    id = "edit.save"
    title = "Save"
    kinds = INPUT_KINDS

    def __init__(self, image: Image.Image, label: str, strip_metadata: bool) -> None:
        self.image = image
        self.label = label
        self.strip = strip_metadata

    def run(self, inputs: Sequence[FileInfo], options: Options, ctx: JobContext) -> list[Path]:
        info = inputs[0]
        fmt, ext = same_format(info)
        img = self.image
        low = img.getchannel("A").getextrema()[0] if img.mode == "RGBA" else 255
        if fmt in ("JPEG", "BMP") and isinstance(low, int | float) and low < 255:
            fmt, ext = "PNG", ".png"
        ctx.progress(0.3, "Saving")
        source = open_image(info.path, ctx.limits)
        data = encode(img, fmt, quality=92, keep_metadata=not self.strip, source=source)
        tmp = ctx.temp_file(f"edited{ext}")
        tmp.write_bytes(data)
        return [ctx.save(tmp, info.path, safe_io.output_name(info.path, ext, self.label))]


class EditorAction(Action):
    """A wheel slice that opens an editor window (UI only, so it lives in the app)."""

    wheel = Wheel.EDIT
    kinds = INPUT_KINDS
    max_files = 1
    interactive = True

    def __init__(self, action_id: str) -> None:
        title, cls, order = EDITORS[action_id]
        self.id = action_id  # type: ignore[misc]
        self.title = title  # type: ignore[misc]
        self.icon = action_id.split(".")[1]  # type: ignore[misc]
        self.order = order  # type: ignore[misc]
        self.cls = cls

    def edit(self, info: FileInfo) -> SaveImage | None:
        """Open the editor (GUI thread). Returns a save action, or None if cancelled."""
        try:
            img = open_image(info.path, DEFAULT_LIMITS)
        except UserError:
            raise
        dlg = self.cls(img)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.result_image is None:
            return None
        return SaveImage(dlg.result_image, dlg.label, strip_metadata=self.id == "edit.redact")

    def run(self, inputs: Sequence[FileInfo], options: Options, ctx: JobContext) -> list[Path]:
        raise UserError("Editors open from the wheel.")


def register(registry: Registry) -> None:
    for action_id in EDITORS:
        registry.register(EditorAction(action_id))


def pixmap_of(img: Image.Image) -> QPixmap:
    return QPixmap.fromImage(pil_to_qimage(img))
