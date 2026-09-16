import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from engine import VietelexEngine
from shortcut import ModifierShortcut


def fake_quartz():
    q = types.ModuleType("Quartz")
    names = ["kCGEventLeftMouseDown", "kCGEventRightMouseDown",
             "kCGEventOtherMouseDown", "kCGEventKeyDown",
             "kCGKeyboardEventKeycode", "kCGEventSourceStateHIDSystemState",
             "kCGEventSourceUserData", "kCGHIDEventTap", "kCGEventKeyUp",
             "kCGEventFlagsChanged", "kCGEventTapDisabledByTimeout",
             "kCGEventTapDisabledByUserInput", "kCGSessionEventTap",
             "kCGHeadInsertEventTap", "kCGEventTapOptionDefault",
             "kCFRunLoopCommonModes", "kCGKeyboardEventAutorepeat"]
    for i, name in enumerate(names, 1):
        setattr(q, name, i)
    q.kCGEventFlagMaskShift = 1 << 17
    q.kCGEventFlagMaskSecondaryFn = 1 << 23
    q.CGEventMaskBit = lambda value: 1 << value
    q.kCGEventFlagMaskCommand = 1 << 20
    q.kCGEventFlagMaskControl = 1 << 18
    q.kCGEventFlagMaskAlternate = 1 << 19
    q.CGEventGetFlags = lambda e: e.get("flags", 0)
    q.CGEventGetIntegerValueField = lambda e, field: e.get("keycode", 0) if field == q.kCGKeyboardEventKeycode else e.get(field, 0)
    q.CGEventSetIntegerValueField = lambda e, field, value: e.update({field: value})
    q.CGEventCreateCopy = lambda e: e.copy()
    q.CGEventKeyboardGetUnicodeString = lambda e, *args: (len(e["chars"]), e["chars"])
    q.CGEventSourceCreate = lambda state: state
    q.CGEventCreateKeyboardEvent = lambda src, key, down: dict(keycode=key, down=down)
    q.CGEventSetFlags = lambda e, flags: e.update(flags=flags)
    q.CGEventKeyboardSetUnicodeString = lambda e, n, s: e.update(chars=s)
    return q


class EngineTests(unittest.TestCase):
    def test_simple_telex_and_tone_correction(self):
        cases = {"tieengs": "tiếng", "tieesng": "tiếng", "Vieetj": "Việt",
                 "hoas": "hoá", "HOAS": "HOÁ", "hoaf": "hoà",
                 "dduowngf": "đường", "aisf": "ài", "aisz": "ai",
                 "aiss": "ais", "uoww": "uow", "uwoww": "ưow",
                 "uongww": "uongw", "UOWW": "UOW", "AISF": "ÀI", "aww": "aw", "w": "w"}
        for keys, expected in cases.items():
            with self.subTest(keys=keys):
                engine = VietelexEngine()
                screen = ""
                for key in keys:
                    n, text = engine.process(key)
                    screen = (screen[:-n] if n else screen) + text
                self.assertEqual(screen, expected)
                self.assertEqual(engine.result_str(), expected)

    def test_backspace_then_tone(self):
        engine = VietelexEngine()
        for key in "ais": engine.process(key)
        engine.backspace()
        engine.process("f")
        self.assertEqual(engine.result_str(), "à")


class HookTests(unittest.TestCase):
    def setUp(self):
        self.q = fake_quartz()
        spec = importlib.util.spec_from_file_location("tested_hook", Path(__file__).resolve().parents[1] / "hook.py")
        self.hook = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, Quartz=self.q):
            spec.loader.exec_module(self.hook)
        self.screen = ""
        self.posted = []
        self.q.CGEventTapPostEvent = self.post
        self.hid = []
        self.q.CGEventPost = self.enqueue
        self.hook.time = types.SimpleNamespace(sleep=lambda seconds: None)

    def enqueue(self, location, event):
        self.assertEqual(location, self.q.kCGHIDEventTap)
        self.assertEqual(event["flags"], 0)
        self.hid.append(event)

    def deliver(self, event):
        if event["down"]:
            if event["keycode"] == 51: self.screen = self.screen[:-1]
            else: self.screen += event.get("chars", "")

    def post(self, proxy, event):
        self.assertEqual(proxy, "proxy")
        self.posted.append(event)
        self.deliver(event)

    def pump(self):
        while self.hid:
            event = self.hid.pop(0)
            event_type = self.q.kCGEventKeyDown if event["down"] else self.q.kCGEventKeyUp
            result = self.hook.keyboard_callback("proxy", event_type, event, None)
            if result is not None: self.deliver(result)

    def key(self, chars, keycode=0, flags=0, pump=True):
        event = dict(chars=chars, keycode=keycode, flags=flags, down=True)
        result = self.hook.keyboard_callback("proxy", self.q.kCGEventKeyDown, event, None)
        if result is not None:
            self.deliver(result)
        if pump: self.pump()

    def test_rapid_input_is_ordered(self):
        for key in "hoasnf": self.key(key, pump=False)
        self.pump()
        self.assertEqual(self.screen, "hoàn")
        self.assertEqual(self.hook.engine.result_str(), "hoàn")
        self.assertFalse(self.hook._replacing)
        self.assertFalse(self.hook._pending)

    def test_hoas_inserts_unicode_via_hid(self):
        for key in "hoa": self.key(key)
        self.key("s", pump=False)
        self.assertEqual(self.screen, "hoa")
        self.assertEqual([e.get("chars") for e in self.hid], [None, None, "á", "á"])
        self.assertEqual([e["down"] for e in self.hid], [True, False, True, False])
        self.pump()
        self.assertEqual(self.screen, "hoá")
        self.assertEqual(self.hook.engine.result_str(), "hoá")

    def test_click_waits_until_replacement_finishes(self):
        for key in "hoas": self.key(key, pump=False)
        click = dict(down=False)
        result = self.hook.keyboard_callback("proxy", self.q.kCGEventLeftMouseDown, click, None)
        self.assertIsNone(result)
        self.pump()
        self.assertEqual(self.screen, "hoá")
        self.assertEqual(self.hook.engine.result_str(), "")

    def test_backspace_waits_until_replacement_finishes(self):
        for key in "hoas": self.key(key, pump=False)
        self.key("", keycode=51, pump=False)
        self.pump()
        self.assertEqual(self.screen, "ho")
        self.assertEqual(self.hook.engine.result_str(), "ho")

    def test_untracked_text_invalidates_buffer(self):
        for text in ["é", "😀", "xy", ""]:
            with self.subTest(text=text):
                self.hook.engine.clear()
                self.screen = ""
                self.key("a"); self.key(text); self.key("s")
                self.assertEqual(self.screen, "a" + text + "s")

    def test_mouse_and_shortcut_reset(self):
        self.key("a")
        self.hook.keyboard_callback("proxy", self.q.kCGEventLeftMouseDown, {}, None)
        self.assertEqual(self.hook.engine.result_str(), "")
        self.key("a")
        self.key("c", flags=self.q.kCGEventFlagMaskCommand)
        self.assertEqual(self.hook.engine.result_str(), "")

    def test_start_failure_reports_status(self):
        statuses = []
        self.q.CGEventTapCreate = lambda *args: None
        self.assertFalse(self.hook.start(on_status=statuses.append))
        self.assertEqual(statuses, [False])

    def test_disabled_tap_recovers_and_clears_buffer(self):
        self.hook._tap = "tap"
        enabled = []
        statuses = []
        self.hook._on_status = statuses.append
        self.q.CGEventTapEnable = lambda tap, value: enabled.append((tap, value))
        self.q.CGEventTapIsEnabled = lambda tap: True
        self.key("a")
        self.hook.keyboard_callback("proxy", self.q.kCGEventTapDisabledByTimeout, {}, None)
        self.assertEqual(self.hook.engine.result_str(), "")
        self.assertEqual(enabled, [("tap", True)])
        self.assertEqual(statuses, [True])


class ShortcutTests(unittest.TestCase):
    def test_toggle_on_full_release_in_either_order(self):
        for sequence in [[1, 3, 2, 0], [2, 3, 1, 0]]:
            shortcut = ModifierShortcut(3, 15)
            shortcut.cancel()  # Typing before the chord must not block it.
            self.assertEqual([shortcut.update(f) for f in sequence], [False, False, False, True])

    def test_other_modifiers_or_keys_cancel(self):
        for sequence in [[4, 5, 7, 3, 1, 0], [1, 3, 7, 3, 0], [1, 0]]:
            shortcut = ModifierShortcut(3, 15)
            self.assertFalse(any(shortcut.update(f) for f in sequence))
        shortcut = ModifierShortcut(3, 15)
        shortcut.update(1)
        shortcut.update(3)
        shortcut.cancel()
        self.assertFalse(shortcut.update(0))
        shortcut.update(3)
        self.assertTrue(shortcut.update(0))


if __name__ == "__main__":
    unittest.main()
