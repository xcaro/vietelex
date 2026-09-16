from contextlib import nullcontext
import threading
import time
import types
import unittest
from unittest.mock import patch

from focus import (AXReader, FocusService, Kind, Snapshot, SurfaceEvidence,
                   MAX_AGE, classify, current)


class PolicyTests(unittest.TestCase):
    def test_roles_and_incomplete_capabilities(self):
        cases = [
            (("AXTextField", None, True, True, True), Kind.TEXT),
            (("AXTextArea", None, None, False, True), Kind.UNKNOWN),
            (("AXTextField", None, None, False, True), Kind.UNKNOWN),
            (("AXTextField", "AXSecureTextField", True, True, True), Kind.SECURE),
            (("AXTextField", None, False, True, True), Kind.CONTROL),
            (("AXStaticText", None, None, True, True), Kind.CONTROL),
            (("AXSlider", None, True, True, False), Kind.CONTROL),
            (("AXGroup", None, None, False, False), Kind.UNKNOWN),
            (("AXGroup", "iOSContentGroup", None, False, False), Kind.UNKNOWN),
            (("AXGroup", None, None, True, True), Kind.TEXT),
            (("AXWebArea", None, None, False, True), Kind.UNKNOWN),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertEqual(classify(*args), expected)

    def test_surface_requires_seen_identity_descendant_and_same_window(self):
        evidence = SurfaceEvidence()
        scope = (1, 42, 10)
        self.assertEqual(evidence.observe(scope, 1, Kind.UNKNOWN, True), Kind.UNKNOWN)
        self.assertEqual(evidence.observe(scope, 2, Kind.TEXT, False, (1,)), Kind.TEXT)
        self.assertEqual(evidence.observe(scope, 1, Kind.UNKNOWN, True), Kind.SURFACE)
        self.assertEqual(evidence.observe(scope, 3, Kind.UNKNOWN, True), Kind.UNKNOWN)
        self.assertEqual(evidence.observe((1, 42, 20), 1, Kind.UNKNOWN, True), Kind.UNKNOWN)
        self.assertEqual(evidence.observe((2, 42, 10), 1, Kind.UNKNOWN, True), Kind.UNKNOWN)

    def test_unrelated_text_or_missing_window_cannot_establish_surface(self):
        for window in (None, 10):
            evidence = SurfaceEvidence()
            scope = (1, 42, window)
            evidence.observe(scope, 1, Kind.UNKNOWN, True)
            evidence.observe(scope, 2, Kind.TEXT, False, (99,))
            self.assertEqual(evidence.observe(scope, 1, Kind.UNKNOWN, True), Kind.UNKNOWN)

    def test_freshness_epoch_and_future_timestamps(self):
        sample = Snapshot(epoch=1, kind=Kind.CONTROL, observed_at=100)
        self.assertTrue(current(sample, 1, 100))
        self.assertFalse(current(sample, 2, 100))
        self.assertFalse(current(sample, 1, 99))
        self.assertFalse(current(sample, 1, 100 + MAX_AGE + 0.01))


class FakeAX:
    def __init__(self):
        self.focus = "surface"
        self.fail = {}
        self.calls = []
        self.nodes = {
            "app": {"AXRole": "AXApplication"},
            "window": {"AXRole": "AXWindow"},
            "surface": {"AXRole": "AXGroup", "AXSubrole": "iOSContentGroup",
                        "AXWindow": "window", "AXParent": "window"},
            "text": {"AXRole": "AXTextField", "AXWindow": "window", "AXParent": "surface"},
        }
        self.trusted = True

    def AXIsProcessTrusted(self): return self.trusted
    def AXUIElementCreateApplication(self, pid): return "app"
    def AXUIElementSetMessagingTimeout(self, element, timeout): return 0
    def AXUIElementGetPid(self, element, out): return 0, 42

    def AXUIElementCopyAttributeValue(self, element, attr, out):
        self.calls.append((element, attr))
        if (element, attr) in self.fail:
            return self.fail[element, attr], None
        if element == "app" and attr == "AXFocusedUIElement":
            return 0, self.focus
        if attr in self.nodes[element]:
            return 0, self.nodes[element][attr]
        return -25205, None

    def AXUIElementIsAttributeSettable(self, element, attr, out):
        return 0, element == "text"


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.ax = FakeAX()
        self.reader = AXReader.__new__(AXReader)
        self.reader.ax = self.ax
        self.reader.equal = lambda a, b: a == b
        self.reader.scope = None
        self.reader.identities = []
        self.reader.serial = 0
        self.reader.surfaces = SurfaceEvidence()

    def test_structural_surface_text_return_and_epoch_reset(self):
        self.assertEqual(self.reader.sample(42, 1).kind, Kind.UNKNOWN)
        self.ax.focus = "text"
        self.assertEqual(self.reader.sample(42, 1).kind, Kind.TEXT)
        self.ax.focus = "surface"
        self.assertEqual(self.reader.sample(42, 1).kind, Kind.SURFACE)
        self.assertEqual(self.reader.sample(42, 2).kind, Kind.UNKNOWN)
        self.assertFalse(any(attr in ("AXValue", "AXSelectedText", "AXChildren")
                             for _, attr in self.ax.calls))

    def test_chat_already_open_can_establish_surface_without_prior_poll(self):
        self.ax.focus = "text"
        self.assertEqual(self.reader.sample(42, 1).kind, Kind.TEXT)
        self.ax.focus = "surface"
        self.assertEqual(self.reader.sample(42, 1).kind, Kind.SURFACE)

    def test_writable_or_wrong_window_parent_cannot_establish_surface(self):
        for invalid in ("writable", "wrong_window"):
            with self.subTest(invalid=invalid):
                self.setUp()
                self.ax.focus = "text"
                if invalid == "writable":
                    self.ax.AXUIElementIsAttributeSettable = lambda *args: (0, True)
                else:
                    self.ax.nodes["surface"]["AXWindow"] = "other_window"
                self.assertEqual(self.reader.sample(42, 1).kind, Kind.TEXT)
                self.ax.AXUIElementIsAttributeSettable = lambda e, a, o: (0, e == "text")
                self.ax.nodes["surface"]["AXWindow"] = "window"
                self.ax.focus = "surface"
                self.assertEqual(self.reader.sample(42, 1).kind, Kind.UNKNOWN)

    def test_generic_editor_group_is_not_learned(self):
        self.ax.nodes["surface"].pop("AXSubrole")
        self.reader.sample(42, 1)
        self.ax.focus = "text"
        self.reader.sample(42, 1)
        self.ax.focus = "surface"
        self.assertEqual(self.reader.sample(42, 1).kind, Kind.UNKNOWN)

    def test_parent_cycle_and_failed_parent_do_not_learn(self):
        for failure in ("cycle", "ipc"):
            with self.subTest(failure=failure):
                self.reader.sample(42, 1)
                if failure == "cycle":
                    self.ax.nodes["surface"]["AXParent"] = "text"
                else:
                    self.ax.fail["text", "AXParent"] = -25204
                self.ax.focus = "text"
                self.assertEqual(self.reader.sample(42, 1).kind, Kind.TEXT)
                self.ax.focus = "surface"
                self.assertEqual(self.reader.sample(42, 1).kind, Kind.UNKNOWN)

    def test_focus_errors_and_permission_never_reuse_success(self):
        self.ax.focus = "text"
        self.assertEqual(self.reader.sample(42, 1).kind, Kind.TEXT)
        for status in (-25204, -25202, -25205, -25208, -25212):
            self.ax.fail["app", "AXFocusedUIElement"] = status
            self.assertEqual(self.reader.sample(42, 1).kind, Kind.UNKNOWN)
        self.ax.trusted = False
        self.assertEqual(self.reader.sample(42, 1).reason, "permission_unavailable")

    def test_budget_and_owner_errors_are_unknown(self):
        with patch("focus.time.monotonic", side_effect=[1, 2]):
            self.assertEqual(self.reader.sample(42, 1).reason, "budget_exceeded")
        self.ax.AXUIElementGetPid = lambda *args: (0, 99)
        self.assertEqual(self.reader.sample(42, 1).reason, "wrong_owner")

    def test_changed_focus_discards_mixed_result(self):
        self.ax.focus = "text"
        original = self.ax.AXUIElementCopyAttributeValue
        count = 0
        def read(element, attr, out):
            nonlocal count
            if attr == "AXFocusedUIElement":
                count += 1
                if count == 2:
                    self.ax.focus = "surface"
            return original(element, attr, out)
        self.ax.AXUIElementCopyAttributeValue = read
        self.assertEqual(self.reader.sample(42, 1).reason, "focus_changed")


class ServiceTests(unittest.TestCase):
    def start_service(self, factory):
        patcher = patch.dict("sys.modules", objc=types.SimpleNamespace(autorelease_pool=nullcontext))
        patcher.start()
        self.addCleanup(patcher.stop)
        service = FocusService(factory)
        service.start()
        def stop():
            service.stop()
            service._thread.join(timeout=1)
            self.assertFalse(service._thread.is_alive())
        self.addCleanup(stop)
        return service

    def wait_latest(self, service):
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            value = service.latest()
            if value is not None:
                return value
            time.sleep(0.001)
        self.fail("worker did not publish")

    def test_old_inflight_result_rejected_and_target_coalesced(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def sample(pid, epoch):
            calls.append((pid, epoch))
            if pid == 42:
                entered.set()
                release.wait(1)
            return Snapshot(epoch=epoch, pid=pid, kind=Kind.TEXT, observed_at=time.monotonic())
        service = self.start_service(lambda: types.SimpleNamespace(sample=sample))
        service.request(42, 1)
        self.assertTrue(entered.wait(1))
        service.request(99, 2)
        service.request(100, 3)
        self.assertIsNone(service.latest())
        release.set()
        latest = self.wait_latest(service)
        self.assertEqual((latest.pid, latest.epoch), (100, 3))
        self.assertNotIn((99, 2), calls)

    def test_reader_exception_is_unknown_and_worker_survives(self):
        def fail(*args): raise RuntimeError("do not log arbitrary native contents")
        with self.assertLogs("focus", level="WARNING") as captured:
            service = self.start_service(lambda: types.SimpleNamespace(sample=fail))
            service.request(42, 1)
            self.assertEqual(self.wait_latest(service).kind, Kind.UNKNOWN)
        self.assertNotIn("do not log", "".join(captured.output))
        self.assertTrue(service._thread.is_alive())

    def test_missing_dependency_falls_back_without_keyboard_failure(self):
        def missing(): raise ImportError("ApplicationServices")
        with self.assertLogs("focus", level="WARNING"):
            service = self.start_service(missing)
            service._thread.join(timeout=1)
        self.assertIsNone(service.latest())

    def test_start_is_idempotent_and_stop_discards_pending_result(self):
        entered, release = threading.Event(), threading.Event()
        def sample(pid, epoch):
            entered.set()
            release.wait(1)
            return Snapshot(epoch=epoch, pid=pid, kind=Kind.TEXT)
        service = self.start_service(lambda: types.SimpleNamespace(sample=sample))
        worker = service._thread
        service.start()
        self.assertIs(service._thread, worker)
        service.request(42, 1)
        self.assertTrue(entered.wait(1))
        service.stop()
        release.set()
        worker.join(timeout=1)
        self.assertIsNone(service.latest())

    def test_refresh_during_inflight_sample_skips_normal_poll_delay(self):
        entered, release, second_sample = threading.Event(), threading.Event(), threading.Event()
        calls = 0
        def sample(pid, epoch):
            nonlocal calls
            calls += 1
            if calls == 1:
                entered.set()
                release.wait(1)
            else:
                second_sample.set()
            return Snapshot(epoch=epoch, pid=pid, kind=Kind.TEXT)
        with patch("focus.POLL_INTERVAL", 10):
            service = self.start_service(lambda: types.SimpleNamespace(sample=sample))
            service.request(42, 1)
            self.assertTrue(entered.wait(1))
            service.refresh()
            release.set()
            self.assertTrue(second_sample.wait(1))
            service.stop()


if __name__ == "__main__":
    unittest.main()
