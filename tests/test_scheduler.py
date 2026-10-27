import threading
import time
import unittest

from monitor.scheduler import BackgroundMonitor


class FakeRunner:
    def __init__(self):
        self.calls = 0

    def get_snapshot(self, **_kwargs):
        self.calls += 1
        return {"run_id": f"run-{self.calls}"}


class SchedulerTests(unittest.TestCase):
    def test_stop_waits_until_inflight_run_finishes(self):
        started = threading.Event()
        release = threading.Event()

        class BlockingRunner:
            def get_snapshot(self, **_kwargs):
                started.set()
                release.wait(5)
                return {"run_id": "done"}

        scheduler = BackgroundMonitor(BlockingRunner(), interval_seconds=0.05)
        scheduler.start()
        self.assertTrue(started.wait(2))
        stopping = threading.Thread(target=scheduler.stop)
        stopping.start()
        try:
            stopping.join(0.15)
            self.assertTrue(stopping.is_alive())
        finally:
            release.set()
            stopping.join(2)
        self.assertFalse(stopping.is_alive())
        self.assertFalse(scheduler.status()["running"])

    def test_background_loop_samples_and_stops(self):
        runner = FakeRunner()
        scheduler = BackgroundMonitor(runner, interval_seconds=0.05)
        scheduler.start()
        deadline = time.monotonic() + 2
        while runner.calls < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        status = scheduler.status()
        scheduler.stop()

        self.assertGreaterEqual(runner.calls, 2)
        self.assertTrue(status["running"])
        self.assertIsNotNone(status["last_run_id"])
        self.assertIsNone(status["last_error"])
        self.assertFalse(scheduler.status()["running"])

    def test_failed_run_is_reported_without_leaking_exception_text(self):
        class FailingRunner:
            def get_snapshot(self, **_kwargs):
                raise RuntimeError("secret path /private/value")

        scheduler = BackgroundMonitor(FailingRunner(), interval_seconds=60)
        self.assertIsNone(scheduler.run_once())
        status = scheduler.status()
        self.assertEqual(status["last_error"], "RuntimeError")
        self.assertNotIn("secret", str(status))


if __name__ == "__main__":
    unittest.main()
