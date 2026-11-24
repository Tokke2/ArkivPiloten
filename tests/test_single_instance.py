"""Cross-process single-instance lock and second-launch handoff."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pdfsorter as P
import pdfsorter_data as D


def test_only_one_lock_owner_can_start_and_lock_is_released(tmp_path):
    path = tmp_path / "json" / "arkivpiloten.lock"
    first = D.InstanceLock(path)
    second = D.InstanceLock(path)

    assert first.acquire() is True
    assert first.acquire() is True  # same owner may confirm its lock
    assert second.acquire() is False
    assert second.other_pid == os.getpid()
    assert not second.lock_error

    first.release()
    assert path.exists()  # stale metadata is retained, not used as a lock
    assert second.acquire() is True
    second.release()


def test_stale_or_corrupt_metadata_does_not_block_os_lock(tmp_path):
    path = tmp_path / "arkivpiloten.lock"
    path.write_text(json.dumps({"pid": 999_999_999, "started": "old"}),
                    encoding="utf-8")

    lock = D.InstanceLock(path)
    assert lock.acquire() is True
    lock.release()

    path.write_text("{ broken", encoding="utf-8")
    next_lock = D.InstanceLock(path)
    assert next_lock.acquire() is True
    next_lock.release()


def test_running_legacy_pid_lock_is_honoured_during_upgrade(tmp_path):
    path = tmp_path / "arkivpiloten.lock"
    old_process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
    try:
        path.write_text(json.dumps({"pid": old_process.pid, "started": "old"}),
                        encoding="utf-8")
        lock = D.InstanceLock(path)
        assert lock.acquire() is False
        assert lock.other_pid == old_process.pid
        assert not lock.lock_error
    finally:
        old_process.terminate()
        old_process.wait(timeout=5)

    next_lock = D.InstanceLock(path)
    assert next_lock.acquire() is True
    next_lock.release()


def test_lock_failure_fails_closed_instead_of_starting_a_second_instance(
        tmp_path):
    not_a_directory = tmp_path / "not-a-directory"
    not_a_directory.write_text("file", encoding="utf-8")
    lock = D.InstanceLock(not_a_directory / "lock")

    assert lock.acquire() is False
    assert lock.lock_error
    assert not lock.acquired


def test_second_launch_requests_existing_window_without_new_dialog():
    source = Path(P.__file__).read_text(encoding="utf-8")
    start = source.index("    # Bara en instans åt gången får äga rules.json.")
    end = source.index("    hjälpare = install_helpers()", start)
    branch = source[start:end]

    assert "request_show()" in branch
    assert "return 0" in branch
    assert "messagebox.showinfo" not in branch
    assert "tkinter.Tk()" not in branch
