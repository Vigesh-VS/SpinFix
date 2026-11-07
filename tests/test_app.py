# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""App layer: drag state machine, IPC validation, hotkey parsing, wheel, editors."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor

from spinfix.actions import edit_ops
from spinfix.app import editors, ipc
from spinfix.app.controller import build_pages
from spinfix.app.hotkey import MOD_ALT, MOD_CONTROL, parse_hotkey
from spinfix.app.toast import result_line
from spinfix.app.wheel import INNER, OUTER, SIZE, WheelWindow
from spinfix.core import filetype
from spinfix.core.jobs import JobResult, JobState
from spinfix.core.registry import Registry
from spinfix.platform.windows.drag_watcher import DragTracker, Phase, Reading
from tests.conftest import make_image

# ------------------------------------------------------------------ drag tracker


class Events:
    def __init__(self) -> None:
        self.log: list[str] = []

    def tracker(self) -> DragTracker:
        return DragTracker(
            on_show=lambda x, y: self.log.append("show"),
            on_cycle=lambda: self.log.append("cycle"),
            on_release=lambda: self.log.append("release"),
            on_cancel=lambda: self.log.append("cancel"),
        )


def _phase(t: DragTracker) -> Phase:
    return t.phase


def r(
    button: bool = False,
    trigger: bool = False,
    esc: bool = False,
    x: int = 0,
    y: int = 0,
    source: bool = True,
) -> Reading:
    return Reading(button, trigger, esc, x, y, source)


def test_drag_then_shift_shows_wheel() -> None:
    ev = Events()
    t = ev.tracker()
    for reading in (
        r(),
        r(button=True),
        r(button=True, x=20),
        r(button=True, x=30, trigger=True),
        r(button=True, x=30),
        r(button=True, x=30, trigger=True),
        r(),
    ):
        t.feed(reading)
    assert ev.log == ["show", "cycle", "release"]
    assert _phase(t) is Phase.IDLE


def test_shift_without_drag_does_nothing() -> None:
    ev = Events()
    t = ev.tracker()
    for reading in (r(button=True), r(button=True, trigger=True), r()):
        t.feed(reading)
    assert ev.log == []


def test_drag_from_other_app_ignored() -> None:
    ev = Events()
    t = ev.tracker()
    for reading in (
        r(button=True, source=False),
        r(button=True, x=50),
        r(button=True, x=50, trigger=True),
    ):
        t.feed(reading)
    assert ev.log == []


def test_shift_held_before_drag_needs_new_press() -> None:
    ev = Events()
    t = ev.tracker()
    for reading in (
        r(trigger=True),
        r(button=True, trigger=True),
        r(button=True, trigger=True, x=40),
    ):
        t.feed(reading)
    assert ev.log == []  # shift-select, not a request for the wheel


def test_escape_cancels_and_waits_for_release() -> None:
    ev = Events()
    t = ev.tracker()
    for reading in (
        r(),
        r(button=True),
        r(button=True, x=20),
        r(button=True, x=20, trigger=True),
        r(button=True, esc=True),
        r(button=True, x=40, trigger=True),
    ):
        t.feed(reading)
    assert ev.log == ["show", "cancel"]
    assert _phase(t) is Phase.COOLDOWN
    t.feed(r())
    assert _phase(t) is Phase.IDLE


# ------------------------------------------------------------------ IPC


def _msg(**data: object) -> bytes:
    return json.dumps(data).encode()


def test_ipc_accepts_valid(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x")
    parsed = ipc.parse_message(_msg(v=1, cmd="open", paths=[str(f)]))
    assert parsed == ("open", [f])


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"\xff\xfe",
        _msg(v=2, cmd="open", paths=[]),
        _msg(v=1, cmd="exec", paths=[]),
        _msg(v=1, cmd="open", paths="C:/"),
        _msg(v=1, cmd="open", paths=[], extra=1),
        b"[1,2,3]",
        b"x" * (70 * 1024),
    ],
)
def test_ipc_rejects_invalid(raw: bytes) -> None:
    assert ipc.parse_message(raw) is None


def test_ipc_drops_bad_paths(tmp_path: Path) -> None:
    parsed = ipc.parse_message(
        _msg(
            v=1,
            cmd="open",
            paths=["relative.txt", str(tmp_path / "missing.txt"), 5, "C:\\a\x00b", None],
        )
    )
    assert parsed == ("open", [])


def test_pipe_name_is_per_user() -> None:
    name = ipc.pipe_name()
    assert name.startswith("Spinfix-") and len(name) > 10
    assert all(ch.isalnum() or ch == "-" for ch in name)


# ------------------------------------------------------------------ hotkey


def test_parse_hotkey() -> None:
    assert parse_hotkey("ctrl+alt+space") == (MOD_CONTROL | MOD_ALT, 0x20)
    assert parse_hotkey("Ctrl + Alt + S") == (MOD_CONTROL | MOD_ALT, ord("S"))
    for bad in ("space", "shift+a", "ctrl+", "hyper+x", "ctrl+f13"):
        assert parse_hotkey(bad) is None


# ------------------------------------------------------------------ wheel


def test_pages_split_at_eight(registry: Registry, work: Path) -> None:
    info = filetype.check(make_image(work / "a.png", fmt="PNG"))
    pages = build_pages(registry, [info])
    assert all(len(p.actions) <= 8 for p in pages)
    assert pages[0].title == "Convert"
    assert any(p.title == "Tools 2" for p in pages)


def test_slice_geometry(qtbot: object, registry: Registry, work: Path) -> None:
    w = WheelWindow(lambda infos: build_pages(registry, infos))
    w.show_for_files([make_image(work / "a.png", fmt="PNG")])
    c = SIZE / 2
    mid = (INNER + OUTER) / 2
    assert w.slice_at(QPointF(c, c)) is None  # centre cancels
    assert w.slice_at(QPointF(c, c - mid)) == 0  # top slice
    n = len(w.current)
    assert w.slice_at(QPointF(c - 1, c - mid)) in (0, n - 1)
    assert w.slice_at(QPointF(c, c + mid)) == n // 2
    assert w.slice_at(QPointF(0, 0)) is None
    w.cycle()
    assert w.page_index == 1
    w.hide()


def test_result_line() -> None:
    line = result_line(
        JobResult(
            JobState.DONE, outputs=[Path(__file__)], input_bytes=2_400_000, output_bytes=600_000
        )
    )
    assert "75 % smaller" in line
    assert result_line(JobResult(JobState.FAILED, message="Nope.")) == "Nope."


# ------------------------------------------------------------------ edit ops


def test_crop_and_ratio() -> None:
    img = Image.new("RGB", (400, 300))
    assert edit_ops.crop(img, (10, 10, 110, 60)).size == (100, 50)
    assert edit_ops.crop(img, (-50, -50, 900, 900)).size == (400, 300)
    with pytest.raises(ValueError, match="empty"):
        edit_ops.crop(img, (5, 5, 5, 5))
    box = edit_ops.fit_ratio((0, 0, 400, 300), 1.0, img.size)
    assert box[2] - box[0] == box[3] - box[1] == 300


def test_adjust() -> None:
    img = Image.new("RGB", (40, 20), (100, 100, 100))
    out = edit_ops.adjust(img, edit_ops.Adjustments(rotate=90, brightness=50, width=10))
    assert out.size == (10, 20)
    assert out.getpixel((0, 0))[0] > 100  # type: ignore[index]


def test_redact_destroys_pixels() -> None:
    img = Image.effect_noise((100, 100), 100).convert("RGB")
    out = edit_ops.redact(img, [(10, 10, 50, 50)], "box")
    assert set(out.crop((10, 10, 50, 50)).get_flattened_data()) == {(0, 0, 0)}
    pix = edit_ops.redact(img, [(0, 0, 100, 100)], "pixelate")
    assert len(set(pix.get_flattened_data())) < 300  # detail is gone, not just covered
    assert img.getpixel((20, 20)) != (0, 0, 0)  # original untouched


def test_add_background() -> None:
    img = Image.new("RGB", (200, 100), "white")
    out = edit_ops.add_background(img, edit_ops.Background(padding=10, ratio="1:1"))
    assert out.width == out.height
    assert out.width > 200


# ------------------------------------------------------------------ editors (offscreen)


@pytest.mark.parametrize(
    "cls",
    [editors.CropEditor, editors.AdjustEditor, editors.AnnotateEditor, editors.BackgroundEditor],
)
def test_editors_render(qtbot: object, cls: editors.EditorFactory) -> None:
    img = Image.new("RGB", (3000, 2000), (30, 120, 200))
    dlg = cls(img)
    qtbot.addWidget(dlg)  # type: ignore[attr-defined]
    out = dlg.render_full()
    assert out.width > 0 and out.height > 0


def test_redact_editor_full_resolution(qtbot: object) -> None:
    img = Image.effect_noise((2400, 1600), 100).convert("RGB")
    dlg = editors.RedactEditor(img)
    qtbot.addWidget(dlg)  # type: ignore[attr-defined]
    dlg.boxes = [QRectF(0, 0, 100 * dlg.pscale * 10, 100 * dlg.pscale * 10)]
    out = dlg.render_full()
    assert out.size == img.size
    assert out.getpixel((500, 500)) == (0, 0, 0)


def test_annotate_draws_on_full_image(qtbot: object) -> None:
    img = Image.new("RGB", (2000, 1000), "white")
    dlg = editors.AnnotateEditor(img)
    qtbot.addWidget(dlg)  # type: ignore[attr-defined]
    s = dlg.pscale
    dlg.shapes.append(
        editors.Shape(
            "box",
            QColor("#E53935"),
            6,
            [QPointF(100 * s, 100 * s), QPointF(900 * s, 600 * s)],
        )
    )
    out = dlg.render_full()
    assert out.size == img.size
    assert out.getpixel((100, 300))[0] > 200 and out.getpixel((100, 300))[1] < 100  # type: ignore[index]


def test_save_image_action(registry: Registry, work: Path) -> None:
    from spinfix.core.jobs import Job

    src = make_image(work / "pic.jpg", (300, 200), fmt="JPEG")
    info = filetype.check(src)
    save = editors.SaveImage(Image.new("RGB", (150, 100), "red"), "Cropped", False)
    result = Job(save, [info]).run()
    assert result.ok
    assert result.outputs[0].name == "pic Cropped.jpg"


SENDER = """
import sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from spinfix.app import ipc
app = QCoreApplication([])
ipc.pipe_name = lambda: sys.argv[1]
sys.exit(0 if ipc.send_to_running("open", [Path(p) for p in sys.argv[2:]]) else 3)
"""


def test_ipc_end_to_end(qtbot: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A second process (like right-click → Spinfix) hands files to the running app."""
    import subprocess
    import sys
    import uuid

    name = f"Spinfix-test-{uuid.uuid4().hex}"
    monkeypatch.setattr(ipc, "pipe_name", lambda: name)
    server = ipc.InstanceServer()
    assert server.listen()
    got: list[tuple[str, list[Path]]] = []
    server.received.connect(lambda cmd, paths: got.append((cmd, paths)))
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("a")
    b.write_text("b")
    procs = [subprocess.Popen([sys.executable, "-c", SENDER, name, str(p)]) for p in (a, b)]
    qtbot.waitUntil(lambda: all(p.poll() is not None for p in procs), timeout=20000)  # type: ignore[attr-defined]
    assert [p.returncode for p in procs] == [0, 0]
    qtbot.waitUntil(lambda: bool(got), timeout=3000)  # type: ignore[attr-defined]
    cmd, paths = got[0]
    assert cmd == "open"
    assert sorted(paths) == [a, b]  # both launches batched into one wheel
    server.close()
