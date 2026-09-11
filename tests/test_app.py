import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from engine import VietelexEngine
from shortcut import ModifierShortcut


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
        def start(on_toggle=None, on_status=None):
            on_status(self.ready)
            return self.ready
        self.hook.start = start
        center = types.SimpleNamespace(addObserverForName_object_queue_usingBlock_=
            lambda name, obj, queue, callback: self.observers.append(callback))
        cocoa = types.SimpleNamespace(
            NSUserDefaults=types.SimpleNamespace(standardUserDefaults=lambda: self.defaults),
            NSWorkspace=types.SimpleNamespace(sharedWorkspace=lambda:
                types.SimpleNamespace(notificationCenter=lambda: center)),
            NSOperationQueue=types.SimpleNamespace(mainQueue=lambda: None),
            NSWorkspaceDidActivateApplicationNotification="activate",
            NSWorkspaceSessionDidResignActiveNotification="resign",
            NSWorkspaceSessionDidBecomeActiveNotification="resume")
        class App:
            def __init__(self, title, **kwargs): self.title = title
        rumps = types.SimpleNamespace(App=App, MenuItem=MenuItem, alert=lambda **kw: None)
        spec = importlib.util.spec_from_file_location("tested_app", Path(__file__).resolve().parents[1] / "app.py")
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, Cocoa=cocoa, Quartz=types.ModuleType("Quartz"),
                        rumps=rumps, hook=self.hook):
            spec.loader.exec_module(self.module)

    def test_failure_and_successful_retry_update_menu(self):
        app = self.module.TelexApp()
        self.assertEqual(app.title, "VIE!")
        self.assertEqual(app._toggle_item.title, "Retry Keyboard Access")
        self.ready = True
        app._on_toggle_click(None)
        self.assertEqual(app.title, "VIE")
        app._on_toggle_click(None)
        self.assertEqual(app.title, "ENG")

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


if __name__ == "__main__":
    unittest.main()
