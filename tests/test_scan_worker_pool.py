from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import unity_font_replacer_core as core
from scan_worker_pool import (
    ActivitySnapshot,
    PersistentScanWorkerPool,
    PersistentScanWorkerSession,
    ScanPoolResult,
    ScanWorkerCrashed,
    ScanWorkerStalled,
    WorkerActivityTracker,
)

_FAKE_WORKER = r"""
import json
import os
import sys
import time

PREFIX = "__UFR_SCAN_WORKER_V1__"

def emit(payload):
    print(PREFIX + json.dumps(payload, separators=(",", ":")), flush=True)

emit({"type": "ready", "pid": os.getpid()})
for raw_line in sys.stdin:
    if not raw_line.startswith(PREFIX):
        continue
    message = json.loads(raw_line[len(PREFIX):])
    if message.get("type") == "shutdown":
        break
    if message.get("type") != "scan":
        continue
    job_id = message["job_id"]
    path = message["path"]
    emit({"type": "activity", "job_id": job_id, "phase": "scan_begin"})
    if path == "hard-crash.assets":
        os._exit(23)
    if path.startswith("crash-once:"):
        marker = path[len("crash-once:"):]
        if not os.path.exists(marker):
            with open(marker, "w", encoding="utf-8"):
                pass
            os._exit(23)
    if path == "hang.assets":
        time.sleep(60)
    emit(
        {
            "type": "result",
            "job_id": job_id,
            "payload": {
                "ttf": [{"file": path, "pid": os.getpid()}],
                "sdf": [],
                "error": None,
            },
        }
    )
"""


class ScanWorkerSessionTests(unittest.TestCase):
    def _command(self) -> list[str]:
        return [sys.executable, "-u", "-c", _FAKE_WORKER]

    def test_session_reuses_one_process_for_multiple_files(self) -> None:
        session = PersistentScanWorkerSession(
            self._command(),
            worker_id=0,
            startup_timeout=10.0,
            stall_seconds=5.0,
            poll_interval=0.05,
            max_jobs=10,
        )
        try:
            first = session.scan(1, "first.assets")
            second = session.scan(2, "second.assets")
        finally:
            session.close()

        self.assertEqual(first["ttf"][0]["file"], "first.assets")
        self.assertEqual(second["ttf"][0]["file"], "second.assets")
        self.assertEqual(first["ttf"][0]["pid"], second["ttf"][0]["pid"])

    def test_hard_exit_reports_the_in_flight_file_and_exit_code(self) -> None:
        session = PersistentScanWorkerSession(
            self._command(),
            worker_id=0,
            startup_timeout=10.0,
            stall_seconds=5.0,
            poll_interval=0.05,
            max_jobs=10,
        )
        try:
            with self.assertRaises(ScanWorkerCrashed) as raised:
                session.scan(7, "hard-crash.assets")
        finally:
            session.close()

        failure = raised.exception
        self.assertEqual(failure.asset_path, "hard-crash.assets")
        self.assertEqual(failure.exit_code, 23)

    def test_inactive_live_process_is_reported_as_stalled_not_crashed(self) -> None:
        unchanged = ActivitySnapshot(cpu_seconds=1.0, io_bytes=1)
        session = PersistentScanWorkerSession(
            self._command(),
            worker_id=0,
            startup_timeout=10.0,
            stall_seconds=0.15,
            poll_interval=0.05,
            max_jobs=10,
            activity_sampler=lambda _pid: unchanged,
        )
        try:
            with self.assertRaises(ScanWorkerStalled) as raised:
                session.scan(8, "hang.assets")
        finally:
            session.close(force=True)

        self.assertEqual(raised.exception.asset_path, "hang.assets")
        self.assertGreaterEqual(raised.exception.idle_seconds, 0.15)


class WorkerActivityTrackerTests(unittest.TestCase):
    def test_total_elapsed_time_does_not_stall_a_worker_that_is_active(self) -> None:
        tracker = WorkerActivityTracker(
            stall_seconds=10.0,
            now=0.0,
            initial_snapshot=ActivitySnapshot(cpu_seconds=1.0, io_bytes=100),
        )

        tracker.observe(
            ActivitySnapshot(cpu_seconds=2.0, io_bytes=100),
            now=1000.0,
        )

        self.assertFalse(tracker.is_stalled(now=1009.9))
        self.assertTrue(tracker.is_stalled(now=1010.1))

    def test_unavailable_activity_sample_never_causes_a_false_stall(self) -> None:
        tracker = WorkerActivityTracker(
            stall_seconds=1.0,
            now=0.0,
            initial_snapshot=None,
        )

        tracker.observe(None, now=500.0)

        self.assertFalse(tracker.is_stalled(now=1000.0))


class PersistentScanWorkerPoolTests(unittest.TestCase):
    def test_hard_crash_is_retried_on_a_fresh_process(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            marker = os.path.join(temp_dir, "crashed.once")
            asset_path = f"crash-once:{marker}"
            pool = PersistentScanWorkerPool(
                [sys.executable, "-u", "-c", _FAKE_WORKER],
                worker_count=1,
                max_retries=1,
                startup_timeout=10.0,
                stall_seconds=5.0,
                poll_interval=0.05,
            )

            result = pool.scan([asset_path])[0]

        self.assertEqual(result.payload["ttf"][0]["file"], asset_path)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.recovered_failure_kind, "crashed")
        self.assertIsNone(result.error)

    def test_core_submits_all_files_to_one_bounded_pool(self) -> None:
        paths = ["a.assets", "b.assets", "c.assets"]
        pool_results = [
            ScanPoolResult(
                index=index,
                asset_path=path,
                payload={
                    "ttf": [{"file": path}],
                    "sdf": [],
                    "error": None,
                },
                error=None,
                warning=None,
                attempts=1,
            )
            for index, path in enumerate(paths)
        ]

        with (
            patch.object(core, "get_data_path", return_value="Game_Data"),
            patch.object(core, "find_assets_files", return_value=paths),
            patch.object(
                core,
                "_build_scan_worker_server_command",
                return_value=["worker"],
            ),
            patch.object(core, "PersistentScanWorkerPool") as pool_type,
        ):
            pool_type.return_value.scan.return_value = pool_results
            scanned = core.scan_fonts(
                "Game",
                isolate_files=True,
                scan_jobs=2,
                scan_ttf=True,
                scan_sdf=False,
            )

        pool_type.assert_called_once()
        self.assertEqual(pool_type.call_args.kwargs["worker_count"], 2)
        pool_type.return_value.scan.assert_called_once_with(paths)
        self.assertEqual(
            [entry["file"] for entry in scanned["ttf"]],
            paths,
        )

    def test_stalled_job_is_restarted_and_retried_once(self) -> None:
        class FakeSession:
            def __init__(self) -> None:
                self.scan_calls = 0
                self.restart_calls = 0
                self.closed = False

            def scan(self, job_id: int, asset_path: str):
                self.scan_calls += 1
                if self.scan_calls == 1:
                    raise ScanWorkerStalled(
                        asset_path=asset_path,
                        worker_id=0,
                        pid=os.getpid(),
                        idle_seconds=301.0,
                    )
                return {"ttf": [{"file": asset_path}], "sdf": [], "error": None}

            def restart(self) -> None:
                self.restart_calls += 1

            def close(self) -> None:
                self.closed = True

        fake = FakeSession()
        pool = PersistentScanWorkerPool(
            ["unused"],
            worker_count=1,
            max_retries=1,
            session_factory=lambda _worker_id: fake,
        )

        result = pool.scan(["large.assets"])[0]

        self.assertEqual(result.payload["ttf"], [{"file": "large.assets"}])
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.recovered_failure_kind, "stalled")
        self.assertEqual(fake.restart_calls, 1)
        self.assertTrue(fake.closed)


if __name__ == "__main__":
    unittest.main()
