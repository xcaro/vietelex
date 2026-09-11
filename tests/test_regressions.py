import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from engine import VietelexEngine


def fake_quartz():
    q = types.ModuleType("Quartz")
    names = ["kCGEventLeftMouseDown", "kCGEventRightMouseDown",
             "kCGEventOtherMouseDown", "kCGEventKeyDown",
             "kCGKeyboardEventKeycode", "kCGEventSourceStatePrivate"]
    for i, name in enumerate(names, 1):
        setattr(q, name, i)
    q.kCGEventFlagMaskCommand = 1 << 20
    q.kCGEventFlagMaskControl = 1 << 18
    q.kCGEventFlagMaskAlternate = 1 << 19
    q.CGEventGetFlags = lambda e: e.get("flags", 0)
    q.CGEventGetIntegerValueField = lambda e, field: e.get("keycode", 0)
    q.CGEventKeyboardGetUnicodeString = lambda e, *args: (len(e["chars"]), e["chars"])
    q.CGEventSourceCreate = lambda state: state
    q.CGEventCreateKeyboardEvent = lambda src, key, down: dict(keycode=key, down=down)
    q.CGEventSetFlags = lambda e, flags: e.update(flags=flags)
    q.CGEventKeyboardSetUnicodeString = lambda e, n, s: e.update(chars=s)
    return q


class EngineTests(unittest.TestCase):
    def test_simple_telex_and_tone_correction(self):
        cases = {"tieengs": "tiếng", "tieesng": "tiếng", "Vieetj": "Việt",
                 "dduowngf": "đường", "aisf": "ài", "aisz": "ai",
                 "aiss": "ais", "AISF": "ÀI", "aww": "aw", "w": "w"}
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

    def post(self, proxy, event):
        self.assertEqual(proxy, "proxy")
        self.assertEqual(event["flags"], 0)
        self.posted.append(event)
        if event["down"]:
            if event["keycode"] == 51: self.screen = self.screen[:-1]
            else: self.screen += event["chars"]

    def key(self, chars, keycode=0, flags=0):
        event = dict(chars=chars, keycode=keycode, flags=flags)
        result = self.hook.keyboard_callback("proxy", self.q.kCGEventKeyDown, event, None)
        if result is not None:
            self.screen += chars

    def test_rapid_input_is_ordered(self):
        for key in "asn": self.key(key)
        self.assertEqual(self.screen, "án")
        self.assertEqual(self.hook.engine.result_str(), "án")
        self.assertEqual(len(self.posted), 4)

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


if __name__ == "__main__":
    unittest.main()
