from __future__ import annotations

import threading
import unittest

from sf3000.app_state import SF3000StateMixin
from sf3000.models import UIRuntimeState


class BackgroundHarness(SF3000StateMixin):
    def __init__(self):
        self._ui_state = UIRuntimeState()
        self.callbacks = []

    def _queue_ui(self, callback, *args, **kwargs):
        callback(*args, **kwargs)


class BackgroundTaskTests(unittest.TestCase):
    def test_run_background_task_calls_success_on_ui_queue(self):
        harness = BackgroundHarness()
        done = threading.Event()

        harness._run_background_task(
            lambda: "ready",
            on_success=lambda value: (harness.callbacks.append(("success", value)), done.set()),
        )

        self.assertTrue(done.wait(2))
        self.assertEqual(harness.callbacks, [("success", "ready")])

    def test_run_background_task_calls_error_and_finally(self):
        harness = BackgroundHarness()
        done = threading.Event()

        def on_error(exc: Exception):
            harness.callbacks.append(("error", str(exc)))

        def on_finally():
            harness.callbacks.append(("finally", None))
            done.set()

        harness._run_background_task(
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            on_error=on_error,
            on_finally=on_finally,
        )

        self.assertTrue(done.wait(2))
        self.assertEqual(harness.callbacks, [("error", "boom"), ("finally", None)])


if __name__ == "__main__":
    unittest.main()
