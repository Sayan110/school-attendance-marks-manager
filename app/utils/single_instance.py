"""Single-instance handling for the desktop application.

A lock file is the source of truth: on Windows a same-named ``QLocalServer``
can be opened twice (verified on Qt 6.12), so owning the socket alone does not
prove that this process is the primary one. The lock file carries the owning
PID, so a crashed instance is detected and taken over, while a live instance
keeps the lock and is only asked to come to the front via the local socket.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QCoreApplication, QEventLoop, QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "ShikshaVikash.SchoolManager.v1"
LOCK_FILE_NAME = "instance.lock"


class SingleInstance:
    def __init__(
        self,
        on_activate: Callable[[], None] | None = None,
        lock_path: Path | str | None = None,
    ) -> None:
        self._server: QLocalServer | None = None
        self._lock: QLockFile | None = None
        self._lock_override = Path(lock_path) if lock_path is not None else None
        self._notify_socket: QLocalSocket | None = None
        self._on_activate = on_activate

    def lock_path(self) -> Path:
        """Lock file next to the database, never in the install directory."""
        if self._lock_override is not None:
            return self._lock_override
        from app import config

        base = config.ensure_data_dirs()["base"]
        return base / f"{SERVER_NAME}.{LOCK_FILE_NAME}"

    def notify_existing(self, timeout_ms: int = 400) -> bool:
        """If another instance is listening, ask it to show itself.

        The request has to reach the pipe before this process exits, otherwise
        the fresh launch would close a queued write and the primary window
        would never come forward. Nested event processing flushes the socket
        (and, in tests, lets the primary accept the connection immediately).
        """
        socket = QLocalSocket()
        socket.connectToServer(SERVER_NAME)
        if not socket.waitForConnected(timeout_ms):
            return False
        socket.write(b"SHOW")
        self._notify_socket = socket
        deadline = time.monotonic() + max(timeout_ms, 200) / 1000
        while socket.bytesToWrite() > 0 and time.monotonic() < deadline:
            QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 5)
            socket.waitForBytesWritten(10)
        socket.flush()
        socket.disconnectFromServer()
        socket.waitForDisconnected(timeout_ms)
        return True

    def start_server(self) -> bool:
        """Become the primary instance. Returns False if another instance owns it.

        The lock is taken first, so two processes can never both believe they
        are primary. ``QLockFile`` treats a lock whose PID is gone as stale and
        takes it over, which recovers cleanly after a crash. Listen failures
        that are not caused by a live owner (a stale pipe name) are retried once
        after clearing the socket name.
        """
        if self._lock is not None:
            return True

        path = self.lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(path))
        if not lock.tryLock(0):
            self.notify_existing()
            return False

        server = QLocalServer()
        if not server.listen(SERVER_NAME):
            QLocalServer.removeServer(SERVER_NAME)
            if not server.listen(SERVER_NAME):
                lock.unlock()
                return False

        self._lock = lock
        server.newConnection.connect(self._handle_connection)
        self._server = server
        return True

    def _handle_connection(self) -> None:
        if not self._server:
            return
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(socket.deleteLater)
            # The message may already be buffered before readyRead is wired up.
            if socket.bytesAvailable() > 0:
                self._read(socket)

    def _read(self, socket: QLocalSocket) -> None:
        try:
            data = bytes(socket.readAll())
        except RuntimeError:
            return
        if b"SHOW" in data and self._on_activate:
            self._on_activate()

    def close(self) -> None:
        if self._notify_socket is not None:
            self._notify_socket.abort()
            self._notify_socket = None
        if self._server is not None:
            self._server.close()
            self._server = None
            QLocalServer.removeServer(SERVER_NAME)
        if self._lock is not None:
            self._lock.unlock()
            self._lock = None
