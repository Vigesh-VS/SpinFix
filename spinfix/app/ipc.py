# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Single instance via a named pipe that only the current user can open.

Messages are small JSON objects: {"v": 1, "cmd": "open", "paths": ["C:\\\\...", ...]}.
They are size-capped (64 KB) and validated; only absolute paths to existing files or
folders are accepted. Anything else is ignored. No network sockets are ever opened.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from spinfix.core.errors import get_logger
from spinfix.core.limits import DEFAULT_LIMITS
from spinfix.platform.windows.shell import user_sid

log = get_logger("ipc")

COMMANDS = frozenset({"open", "show"})
MAX_PATHS = 2000
ASFW_ANY = -1
BATCH_WINDOW_MS = 350  # Explorer may start one process per selected file


def pipe_name() -> str:
    safe = "".join(ch for ch in user_sid() if ch.isalnum() or ch == "-")
    return f"Spinfix-{safe}"


def parse_message(raw: bytes) -> tuple[str, list[Path]] | None:
    """Validate an IPC message. Returns (command, paths) or None if invalid."""
    if len(raw) > DEFAULT_LIMITS.ipc_max_message_bytes:
        return None
    try:
        data: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or set(data) - {"v", "cmd", "paths"}:
        return None
    if data.get("v") != 1 or data.get("cmd") not in COMMANDS:
        return None
    raw_paths = data.get("paths", [])
    if not isinstance(raw_paths, list) or len(raw_paths) > MAX_PATHS:
        return None
    paths: list[Path] = []
    for item in raw_paths:
        if not isinstance(item, str) or not item or "\x00" in item or len(item) > 32767:
            continue
        p = Path(item)
        if p.is_absolute() and p.exists():
            paths.append(p)
    return str(data["cmd"]), paths


def encode_message(cmd: str, paths: Sequence[Path]) -> bytes:
    """One JSON object followed by a newline (the end-of-message marker)."""
    data = {"v": 1, "cmd": cmd, "paths": [str(p) for p in paths]}
    return json.dumps(data).encode("utf-8") + b"\n"


def send_to_running(cmd: str, paths: Sequence[Path], timeout_ms: int = 1500) -> bool:
    """Try to hand the request to an already-running Spinfix. True if delivered."""
    sock = QLocalSocket()
    sock.connectToServer(pipe_name())
    if not sock.waitForConnected(timeout_ms):
        return False
    # Let the running Spinfix bring its wheel to the front (we were started by Explorer).
    with contextlib.suppress(AttributeError, OSError):
        ctypes.windll.user32.AllowSetForegroundWindow(ASFW_ANY)
    payload = encode_message(cmd, paths)
    if len(payload) > DEFAULT_LIMITS.ipc_max_message_bytes:
        payload = encode_message(cmd, paths[:200])
    sock.write(payload)
    sock.flush()
    sock.waitForBytesWritten(timeout_ms)
    # Wait for the "ok" so we don't hang up before the running app has read the message.
    sock.waitForReadyRead(timeout_ms)
    sock.disconnectFromServer()
    return True


class InstanceServer(QObject):
    """Receives requests from later launches (right-click, Send To, second start)."""

    received = Signal(str, object)  # cmd, list[Path]

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.setMaxPendingConnections(16)
        self._pending: list[Path] = []
        self._batch = QTimer(self, singleShot=True, interval=BATCH_WINDOW_MS)
        self._batch.timeout.connect(self._flush)

    def listen(self) -> bool:
        name = pipe_name()
        if not self.server.listen(name):
            QLocalServer.removeServer(name)  # stale pipe left by a crash
            if not self.server.listen(name):
                log.error("couldn't create the IPC pipe")
                return False
        self.server.newConnection.connect(self._on_connection)
        return True

    def _on_connection(self) -> None:
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            state = {"buf": bytearray(), "done": False}

            def consume(sock: QLocalSocket = sock, state: dict[str, Any] = state) -> None:
                """Read what has arrived; handle the message once its newline is in."""
                if state["done"]:
                    return
                buf: bytearray = state["buf"]
                buf.extend(bytes(sock.readAll().data()))
                if len(buf) > DEFAULT_LIMITS.ipc_max_message_bytes:
                    state["done"] = True
                    sock.abort()
                    return
                end = buf.find(b"\n")
                closed = sock.state() == QLocalSocket.LocalSocketState.UnconnectedState
                if end >= 0 or closed:
                    state["done"] = True
                    message = bytes(buf[: end if end >= 0 else len(buf)])
                    if message:
                        self._handle(message)
                    if not closed:
                        sock.write(b"ok\n")
                        sock.flush()
                    sock.disconnectFromServer()
                    sock.deleteLater()

            sock.readyRead.connect(consume)
            sock.disconnected.connect(consume)
            consume()  # the sender may already have written (and left) before we got here

    def _handle(self, raw: bytes) -> None:
        parsed = parse_message(raw)
        if parsed is None:
            log.warning("ignored an invalid IPC message")
            return
        cmd, paths = parsed
        if cmd == "show":
            self.received.emit("show", [])
            return
        self._pending.extend(p for p in paths if p not in self._pending)
        self._batch.start()

    def _flush(self) -> None:
        paths, self._pending = self._pending, []
        if paths:
            self.received.emit("open", paths)

    def close(self) -> None:
        self.server.close()


def install(server: InstanceServer, on_request: Callable[[str, list[Path]], None]) -> None:
    server.received.connect(on_request)
