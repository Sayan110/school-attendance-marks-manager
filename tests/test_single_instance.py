"""Single-instance lock: one primary window, others ask it to come forward."""
from __future__ import annotations

import subprocess
import sys
import time

import pytest
from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication

from app.utils import single_instance as module
from app.utils.single_instance import SingleInstance


@pytest.fixture()
def server_name(monkeypatch, tmp_path):
    name = f"SVSM.Test.{tmp_path.name}"
    monkeypatch.setattr(module, "SERVER_NAME", name)
    yield name
    QApplication.processEvents()


class InstanceFactory:
    """Hands out SingleInstance objects that share one lock file."""

    def __init__(self, lock_path):
        self.lock_path = lock_path

    def __call__(self, on_activate=None) -> SingleInstance:
        return SingleInstance(on_activate, lock_path=self.lock_path)


@pytest.fixture()
def make_instance(server_name, tmp_path):
    return InstanceFactory(tmp_path / "instance.lock")


def wait_for(qapp, predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_second_instance_is_rejected_and_activates_the_first(qapp, make_instance):
    activated = []
    primary = make_instance(lambda: activated.append(True))
    secondary = make_instance()
    assert primary.start_server() is True
    try:
        assert secondary.start_server() is False
        assert wait_for(qapp, lambda: bool(activated)) is True
    finally:
        primary.close()
        secondary.close()


def test_lock_file_exists_while_primary_and_is_released_on_close(make_instance):
    assert make_instance.lock_path.exists() is False
    primary = make_instance()
    assert primary.start_server() is True
    try:
        assert make_instance.lock_path.exists() is True
        # A second lock object in this process must not be able to take it.
        other = QLockFile(str(make_instance.lock_path))
        assert other.tryLock(0) is False
        other.unlock()
    finally:
        primary.close()
    assert make_instance.lock_path.exists() is False


def test_notify_existing_without_server_returns_false(qapp, make_instance):
    instance = make_instance()
    assert instance.notify_existing(timeout_ms=100) is False


def test_server_can_be_restarted_after_close(qapp, make_instance):
    first = make_instance()
    assert first.start_server() is True
    first.close()
    second = make_instance()
    try:
        assert second.start_server() is True
    finally:
        second.close()


def test_stale_lock_from_a_crashed_process_is_taken_over(make_instance):
    # A killed process leaves its lock file behind; the PID check must free it.
    lock_path = make_instance.lock_path
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    child = (
        "import sys, time\n"
        "from PySide6.QtCore import QLockFile\n"
        "lock = QLockFile(sys.argv[1])\n"
        "print('locked' if lock.tryLock(0) else 'busy', flush=True)\n"
        "time.sleep(30)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", child, str(lock_path)],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "locked"
        assert lock_path.exists()
    finally:
        proc.kill()
        proc.wait(timeout=15)
        if proc.stdout is not None:
            proc.stdout.close()

    instance = make_instance()
    try:
        assert instance.start_server() is True
    finally:
        instance.close()


def test_stale_socket_is_cleared_and_server_recovers(qapp, server_name, make_instance):
    # Simulate a crash leaving the socket name behind without a listener.
    from PySide6.QtNetwork import QLocalServer

    QLocalServer.removeServer(server_name)
    instance = make_instance()
    try:
        assert instance.start_server() is True
    finally:
        instance.close()
        QLocalServer.removeServer(server_name)
