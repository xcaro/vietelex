import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from engine import VietelexEngine
from shortcut import ModifierShortcut
from focus import Snapshot, Kind


class MenuItem:
    def __init__(self, title, callback=None):
        self.title, self.callback, self.state = title, callback, False
        self.children = []

    def set_callback(self, callback):
        self.callback = callback

    def add(self, item):
        self.children.append(item)


class Defaults:
    def __init__(self):
        self.values = {}

    def registerDefaults_(self, defaults):
        for key, value in defaults.items(): self.values.setdefault(key, value)

    def boolForKey_(self, key):
        return self.values[key]

    def setBool_forKey_(self, value, key):
        self.values[key] = value


class AppTests(unittest.TestCase):
    def setUp(self):
        self.defaults = Defaults()
        self.observers = []
        self.ready = False
        self.hook = types.SimpleNamespace(engine=VietelexEngine(), enabled=True,
                                          shortcut=ModifierShortcut(3, 15))
        self.epoch = 0
        self.published = []
        def invalidate():
            self.epoch += 1
            self.hook.engine.clear()
            self.hook.shortcut.reset()
            return self.epoch
        self.hook.invalidate_context = invalidate
        self.hook.focus_epoch = lambda: self.epoch
        self.refresh_requested = False
        self.refresh_calls = 0
        def consume_refresh():
            value = self.refresh_requested
            self.refresh_requested = False
            return value
        def refresh():
            self.refresh_calls += 1
        self.hook.consume_focus_refresh = consume_refresh
        self.hook.publish_focus = self.published.append
        self.requests = []
        self.snapshot = None
        self.stopped = False
        def stop():
            self.stopped = True
        service = types.SimpleNamespace(start=lambda: None, stop=stop,
            request=lambda pid, epoch: self.requests.append((pid, epoch)),
            latest=lambda: self.snapshot, refresh=refresh)
        focus_module = types.SimpleNamespace(FocusService=lambda: service)
        def start(on_toggle=None, on_status=None):
            on_status(self.ready)
            return self.ready
        self.hook.start = start
        self.front_pid = 42
        self.removed = []
        def add_observer(name, obj, queue, callback):
            self.observers.append(callback)
            return name
        center = types.SimpleNamespace(addObserverForName_object_queue_usingBlock_=add_observer,
                                      removeObserver_=self.removed.append)
        workspace = types.SimpleNamespace(notificationCenter=lambda: center,
            frontmostApplication=lambda: types.SimpleNamespace(processIdentifier=lambda: self.front_pid))
        cocoa = types.SimpleNamespace(
            NSUserDefaults=types.SimpleNamespace(standardUserDefaults=lambda: self.defaults),
            NSWorkspace=types.SimpleNamespace(sharedWorkspace=lambda: workspace),
            NSOperationQueue=types.SimpleNamespace(mainQueue=lambda: None),
            NSWorkspaceDidActivateApplicationNotification="activate",
            NSWorkspaceSessionDidResignActiveNotification="resign",
            NSWorkspaceSessionDidBecomeActiveNotification="resume")
        class App:
            def __init__(self, title, **kwargs): self.title = title
        class Timer:
            def __init__(self, callback, interval): self.running = False
            def start(self): self.running = True
            def stop(self): self.running = False
        self.quit_called = False
        def quit_app(): self.quit_called = True
        rumps = types.SimpleNamespace(App=App, MenuItem=MenuItem, alert=lambda **kw: None,
                                     Timer=Timer, quit_application=quit_app)
        class Panel:
            @classmethod
            def alloc(cls): return cls()
            def init(self): return self
            def configure(self, retry): self.retry = retry; self.visible = False
            def show(self): self.visible = True
            def close_(self, sender): self.visible = False
            def retry_(self, sender): self.close_(sender); self.retry()
        spec = importlib.util.spec_from_file_location("tested_app", Path(__file__).resolve().parents[1] / "app.py")
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, Cocoa=cocoa, Quartz=types.ModuleType("Quartz"),
                        rumps=rumps, hook=self.hook, focus=focus_module,
                        keyboard_access=types.SimpleNamespace(KeyboardAccessPanel=Panel)):
            spec.loader.exec_module(self.module)

    def test_failure_and_successful_retry_update_menu(self):
        app = self.module.TelexApp()
        self.assertEqual(app.title, "VIE!")
        self.assertEqual(app._toggle_item.title, "Retry Keyboard Access")
        self.ready = True
        app._on_toggle_click(None)
        self.assertEqual(app.title, "VIE!")
        app._keyboard_access_panel.retry_(None)
        self.assertEqual(app.title, "VIE")
        app._on_toggle_click(None)
        self.assertEqual(app.title, "ENG")

    def test_access_panel_reuses_window_and_keeps_menu_callbacks_available(self):
        self.ready = True
        app = self.module.TelexApp()
        app._on_keyboard_access(None)
        panel = app._keyboard_access_panel
        app._on_keyboard_access(None)
        self.assertIs(app._keyboard_access_panel, panel)
        app._on_toggle_click(None)
        self.assertEqual(app.title, "ENG")
        app._poll_focus(None)
        self.assertTrue(self.requests)
        app._on_quit(None)
        self.assertFalse(panel.visible)
        self.assertTrue(self.quit_called)

    def test_preferences_survive_app_recreation(self):
        app = self.module.TelexApp()
        app._on_validator(app._validator_item)
        app._on_reset_click(app._reset_click_item)
        reopened = self.module.TelexApp()
        self.assertFalse(reopened._validator_item.state)
        self.assertFalse(reopened._reset_click_item.state)
        for ch in "aisf": self.hook.engine.process(ch)
        self.assertEqual(self.hook.engine.result_str(), "ài")

    def test_workspace_notification_resets_composition_and_chord(self):
        self.module.TelexApp()
        self.assertEqual(len(self.observers), 3)
        for callback in self.observers:
            self.hook.engine.process("a")
            self.hook.shortcut.update(3)
            callback(None)
            self.assertEqual(self.hook.engine.result_str(), "")
            self.assertFalse(self.hook.shortcut.update(0))

    def test_focus_publication_rejects_old_app_results(self):
        app = self.module.TelexApp()
        app._poll_focus(None)
        self.snapshot = Snapshot(epoch=self.epoch, pid=42, kind=Kind.CONTROL)
        app._poll_focus(None)
        self.assertEqual(self.published, [self.snapshot])
        self.front_pid = 99
        app._poll_focus(None)
        self.assertEqual(len(self.published), 1)
        self.assertEqual(self.requests[-1], (99, self.epoch))

    def test_session_pause_and_quit_stop_enrichment(self):
        app = self.module.TelexApp()
        app._on_context_change(types.SimpleNamespace(name=lambda: "resign"))
        app._poll_focus(None)
        self.assertIsNone(self.requests[-1][0])
        app._on_quit(None)
        self.assertTrue(self.stopped)
        self.assertFalse(app._focus_timer.running)
        self.assertTrue(self.quit_called)
        self.assertEqual(len(self.removed), 3)

    def test_keyboard_focus_refresh_reaches_worker_once(self):
        app = self.module.TelexApp()
        self.refresh_requested = True
        app._poll_focus(None)
        app._poll_focus(None)
        self.assertEqual(self.refresh_calls, 1)


if __name__ == "__main__":
    unittest.main()
