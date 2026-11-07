# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Start the Spinfix app: single instance, tray, drag watcher, hotkey."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from spinfix import __version__


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="spinfix", add_help=True)
    parser.add_argument("--version", action="version", version=f"Spinfix {__version__}")
    parser.add_argument("--background", action="store_true", help="start quietly in the tray")
    parser.add_argument("--self-test", action="store_true", help="check this build works")
    parser.add_argument(
        "--open",
        nargs="*",
        default=[],
        metavar="FILE",
        help="open the wheel for these files (right-click / Send To)",
    )
    parser.add_argument("files", nargs="*", help="same as --open")
    return parser.parse_args(list(argv))


def run(argv: Sequence[str]) -> int:
    args = _parse(argv)
    paths = [Path(p) for p in [*args.open, *args.files]]
    paths = [p.resolve() for p in paths if p.is_absolute() or p.exists()]

    from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon  # noqa: PLC0415

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Spinfix")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)

    if args.self_test:
        from spinfix.app import selftest  # noqa: PLC0415
        from spinfix.core.errors import setup_logging  # noqa: PLC0415

        setup_logging()
        return selftest.show(selftest.run_checks())

    from spinfix.app import ipc  # noqa: PLC0415

    if ipc.send_to_running("open" if paths else "show", paths):
        return 0  # an instance is already running; it takes over

    import ctypes  # noqa: PLC0415

    from spinfix.actions import build_registry  # noqa: PLC0415
    from spinfix.app import theme  # noqa: PLC0415
    from spinfix.app.controller import Controller  # noqa: PLC0415
    from spinfix.app.hotkey import Hotkey  # noqa: PLC0415
    from spinfix.app.settings_window import SettingsWindow, show_about  # noqa: PLC0415
    from spinfix.app.welcome import Welcome  # noqa: PLC0415
    from spinfix.core import safe_io  # noqa: PLC0415
    from spinfix.core.errors import get_logger, setup_logging  # noqa: PLC0415
    from spinfix.core.settings import store  # noqa: PLC0415

    # Lets the installer/uninstaller see that Spinfix is running and ask to close it.
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "SpinfixAppMutex")

    setup_logging()
    log = get_logger("app")
    log.info("Spinfix %s starting", __version__)
    safe_io.clean_temp_root()
    app.setStyleSheet(theme.STYLE)
    app.setWindowIcon(theme.app_icon())

    server = ipc.InstanceServer()
    server.listen()
    from spinfix.app import editors  # noqa: PLC0415

    registry = build_registry()
    editors.register(registry)
    controller = Controller(registry)
    hotkey = Hotkey()
    app.installNativeEventFilter(hotkey.filter)
    hotkey.signals.pressed.connect(controller.hotkey_pressed)
    hotkey_ok = hotkey.register(store.get().hotkey)

    def on_request(cmd: str, files: list[Path]) -> None:
        if cmd == "open":
            controller.open_files(files)
        else:
            controller.toast.message(
                "Spinfix is running", "Drag a file and press Shift, or use the tray icon."
            )

    server.received.connect(on_request)

    tray = QSystemTrayIcon(theme.app_icon())
    tray.setToolTip(f"Spinfix {__version__}")
    menu = QMenu()
    pick = menu.addAction("Pick files…")
    pick.triggered.connect(controller.pick_files)
    pause = menu.addAction("Pause")
    pause.setCheckable(True)
    pause.setChecked(store.get().paused)

    def toggle_pause(checked: bool) -> None:
        store.update(paused=checked)
        tray.setToolTip(f"Spinfix {__version__}" + (" (paused)" if checked else ""))

    pause.toggled.connect(toggle_pause)
    settings_window: list[SettingsWindow] = []

    def apply_settings() -> None:
        controller.apply_settings()
        hotkey.register(store.get().hotkey)

    def open_settings() -> None:
        if not settings_window:
            settings_window.append(SettingsWindow(apply_settings))
        settings_window[0].show()
        settings_window[0].raise_()
        settings_window[0].activateWindow()

    menu.addAction("Settings…").triggered.connect(open_settings)
    menu.addAction("About Spinfix").triggered.connect(show_about)
    menu.addSeparator()
    menu.addAction("Quit").triggered.connect(app.quit)
    tray.setContextMenu(menu)

    def on_tray(reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            controller.pick_files()

    tray.activated.connect(on_tray)
    tray.show()

    def cleanup() -> None:
        controller.shutdown()
        hotkey.unregister()
        server.close()
        safe_io.clean_temp_root()
        log.info("Spinfix stopped")

    app.aboutToQuit.connect(cleanup)
    controller.start()

    if not store.get().first_run_done and not args.background:
        Welcome().exec()
    if not hotkey_ok:
        tray.showMessage(
            "Spinfix hotkey is taken",
            f"{store.get().hotkey} is used by another app. Pick another in Settings.",
            QSystemTrayIcon.MessageIcon.Warning,
            6000,
        )
    if paths:
        controller.open_files(paths)
    elif not args.background:
        tray.showMessage(
            "Spinfix is ready",
            "Drag a file and press Shift. Spinfix lives in the tray.",
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )
    return app.exec()
