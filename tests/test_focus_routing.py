import itertools
from unittest.mock import Mock
import test_focus as focus_fixtures

from focus import Kind, Snapshot, MAX_AGE
from test_regressions import HookTests


KEYS = {"a": 0, "s": 1, "d": 2, "w": 13}


def legal_events(unpressed, held):
    if not unpressed and not held:
        yield []
    for key in sorted(unpressed):
        for suffix in legal_events(unpressed - {key}, held | {key}):
            yield [(True, key)] + suffix
    for key in sorted(held):
        for suffix in legal_events(unpressed, held - {key}):
            yield [(False, key)] + suffix


class FocusRoutingTests(HookTests):
    def setUp(self):
        super().setUp()
        self.now = 100.0
        self.hook._clock = lambda: self.now
        self.trace = []
        self.held = set()
        original = self.deliver
        def deliver(event):
            self.trace.append(event.copy())
            code = event.get("keycode")
            if code is not None:
                if event.get("down"):
                    self.held.add(code)
                else:
                    self.held.discard(code)
            if "down" in event:
                original(event)
        self.deliver = deliver

    def focus(self, kind, element=1, control_context=False):
        self.hook.publish_focus(Snapshot(
            epoch=self.hook.focus_epoch(), pid=42, observed_at=self.now,
            window=1, element=element, kind=kind, control_context=control_context))

    def event(self, down, code, chars="", flags=0, repeat=False, pump=False):
        event = dict(down=down, keycode=code, chars=chars, flags=flags)
        event[self.q.kCGKeyboardEventAutorepeat] = int(repeat)
        kind = self.q.kCGEventKeyDown if down else self.q.kCGEventKeyUp
        result = self.hook.keyboard_callback("proxy", kind, event, None)
        if result is not None:
            self.deliver(result)
        if pump:
            self.pump()
        return event

    def test_all_2920_legal_wasd_press_release_sequences(self):
        self.focus(Kind.SURFACE)
        self.hook.engine.process = Mock(side_effect=AssertionError("RAW reached Telex"))
        count = 0
        for size in range(1, 5):
            for subset in itertools.combinations(KEYS, size):
                for sequence in legal_events(set(subset), set()):
                    expected = set()
                    start = len(self.trace)
                    source = []
                    for down, key in sequence:
                        source.append(self.event(down, KEYS[key], key))
                        if down:
                            expected.add(KEYS[key])
                        else:
                            expected.remove(KEYS[key])
                        self.assertEqual(self.held, expected, sequence)
                    self.assertEqual(self.trace[start:], source, sequence)
                    self.assertFalse(self.hid)
                    self.assertFalse(self.hook._replacing)
                    count += 1
        self.assertEqual(count, 2920)
        self.hook.engine.process.assert_not_called()

    def test_all_subsets_modifiers_and_interleaved_repeats(self):
        self.focus(Kind.CONTROL)
        masks = [self.q.kCGEventFlagMaskShift, self.q.kCGEventFlagMaskControl,
                 self.q.kCGEventFlagMaskAlternate, self.q.kCGEventFlagMaskCommand]
        for bits in itertools.product((False, True), repeat=4):
            flags = sum(mask for mask, on in zip(masks, bits) if on)
            for size in range(1, 5):
                for subset in itertools.combinations(KEYS, size):
                    start = len(self.trace)
                    source = []
                    for key in subset:
                        source.append(self.event(True, KEYS[key], key.upper(), flags))
                        for held in subset[:subset.index(key) + 1]:
                            source.append(self.event(True, KEYS[held], held.upper(), flags, repeat=True))
                    for key in reversed(subset):
                        source.append(self.event(False, KEYS[key], key.upper(), flags))
                    self.assertEqual(self.trace[start:], source)
                    self.assertFalse(self.held)
                    self.assertFalse(self.hid)

    def test_raw_is_key_and_character_agnostic(self):
        self.focus(Kind.SURFACE)
        for code in (0, 1, 2, 13, 12, 14, 15, 3, 18, 36, 76, 53, 51, 49, 123, 124, 125, 126):
            for chars in ("", "é", "😀", "ab", "W"):
                start = len(self.trace)
                down = self.event(True, code, chars)
                up = self.event(False, code, chars)
                self.assertEqual(self.trace[start:], [down, up])
        self.assertFalse(self.hid)

    def test_text_triggers_are_raw_on_surface(self):
        self.focus(Kind.SURFACE)
        for word in ("aw", "as", "aa", "dd", "aww", "ass", "aaa", "wasd", "asdw", "dsaｗ"):
            for key in word:
                self.event(True, KEYS.get(key, 13), key, pump=True)
                self.event(False, KEYS.get(key, 13), key)
        self.assertFalse(any(self.q.kCGEventSourceUserData in event for event in self.trace))

    def test_chat_surface_chat_round_trip(self):
        self.focus(Kind.TEXT)
        for ch in "tieengs": self.key(ch)
        self.assertEqual(self.screen, "tiếng")
        self.focus(Kind.SURFACE, 2)
        self.assertEqual(self.hook.engine.result_str(), "")
        self.event(True, 0, "a")
        self.event(True, 13, "w")
        self.assertEqual(self.held, {0, 13})
        self.event(False, 0, "a")
        self.event(False, 13, "w")
        self.focus(Kind.TEXT, 3)
        self.screen = ""
        for ch in "aw": self.key(ch)
        self.assertEqual(self.screen, "ă")

    def test_ax_chat_first_to_surface_preserves_all_wasd_pairs(self):
        # Exercise actual AX classification/learning -> published snapshot ->
        # hook -> receiver, without assigning SURFACE directly in the test.
        fixture = focus_fixtures.ReaderTests()
        fixture.setUp()
        fixture.ax.focus = "text"
        snapshot = fixture.reader.sample(42, self.hook.focus_epoch())
        self.now = snapshot.observed_at
        self.hook.publish_focus(snapshot)
        for ch in "tieengs": self.key(ch)
        self.key("\r", keycode=36)
        fixture.ax.focus = "surface"
        snapshot = fixture.reader.sample(42, self.hook.focus_epoch())
        self.now = snapshot.observed_at
        self.hook.publish_focus(snapshot)
        self.assertEqual(snapshot.kind, Kind.SURFACE)
        for first, second in itertools.permutations(KEYS, 2):
            self.held.clear()
            start = len(self.trace)
            source = [self.event(True, KEYS[first], first),
                      self.event(True, KEYS[second], second)]
            self.assertEqual(self.held, {KEYS[first], KEYS[second]})
            source += [self.event(False, KEYS[first], first),
                       self.event(False, KEYS[second], second)]
            self.assertEqual(self.trace[start:], source)
            self.assertFalse(self.hid)

    def test_enter_does_not_infer_gameplay(self):
        self.focus(Kind.TEXT)
        self.key("\r", keycode=36)
        self.key("a")
        self.key("w", keycode=13)
        self.assertTrue(self.screen.endswith("ă"))

    def test_control_chat_boundary_protects_all_pairs_before_ax_update(self):
        for boundary in (36, 76, 53, 48):
            for first, second in itertools.permutations(KEYS, 2):
                self.hook.invalidate_context()
                self.focus(Kind.TEXT, control_context=True)
                self.event(True, boundary)
                self.event(False, boundary)
                self.held.clear()
                start = len(self.trace)
                source = [self.event(True, KEYS[first], first),
                          self.event(True, KEYS[second], second)]
                self.assertEqual(self.held, {KEYS[first], KEYS[second]})
                source += [self.event(False, KEYS[first], first),
                           self.event(False, KEYS[second], second)]
                self.assertEqual(self.trace[start:], source)
                self.assertFalse(self.hid)

    def test_mouse_chat_boundary_protects_before_ax_update(self):
        self.focus(Kind.TEXT, control_context=True)
        self.hook.keyboard_callback("proxy", self.q.kCGEventLeftMouseDown, {}, None)
        self.event(True, 0, "a")
        self.event(True, 13, "w")
        self.assertEqual(self.held, {0, 13})
        self.assertFalse(self.hid)

    def test_guard_waits_for_post_boundary_text_confirmation(self):
        self.focus(Kind.TEXT, control_context=True)
        self.event(True, 36)
        self.event(False, 36)
        self.assertTrue(self.hook.consume_focus_refresh())
        self.assertFalse(self.hook.consume_focus_refresh())
        self.focus(Kind.TEXT, control_context=True)  # old sample timestamp
        self.assertIsNotNone(self.hook._transition_started)
        self.now += 0.02
        self.focus(Kind.TEXT, control_context=True)
        self.assertIsNotNone(self.hook._transition_started)
        self.now += 0.1
        self.focus(Kind.TEXT, control_context=True)
        self.assertIsNone(self.hook._transition_started)
        self.key("a")
        self.key("w", keycode=13)
        self.assertTrue(self.screen.endswith("ă"))

    def test_guard_finishes_on_surface_and_bounds_failure_fallback(self):
        self.focus(Kind.TEXT, control_context=True)
        self.event(True, 36)
        self.now += 0.02
        self.focus(Kind.SURFACE, element=2, control_context=True)
        self.assertIsNone(self.hook._transition_started)
        self.focus(Kind.TEXT, element=3, control_context=True)
        self.event(True, 36)
        self.focus(Kind.UNKNOWN)
        self.assertIsNotNone(self.hook._transition_started)
        self.now += self.hook._TRANSITION_TIMEOUT + 0.01
        self.key("a")
        self.key("w", keycode=13)
        self.assertIsNone(self.hook._transition_started)
        self.assertTrue(self.screen.endswith("ă"))

    def test_queued_enter_arms_guard_when_delivered_not_at_arrival(self):
        self.focus(Kind.TEXT, control_context=True)
        self.key("a")
        self.key("s", keycode=1, pump=False)
        self.event(True, 36)
        self.assertIsNone(self.hook._transition_started)
        source = [self.event(True, 0, "a"), self.event(True, 13, "w")]
        self.pump()
        self.assertIsNotNone(self.hook._transition_started)
        self.assertEqual(self.trace[-2:], source)
        self.assertTrue({0, 13}.issubset(self.held))

    def test_unknown_and_expired_focus_keep_legacy_composition(self):
        for kind in (Kind.UNKNOWN, Kind.SURFACE):
            self.hook.engine.clear()
            self.screen = ""
            self.focus(kind)
            if kind == Kind.SURFACE:
                self.now += MAX_AGE + 0.01
            for ch in "tieengs":
                if kind == Kind.UNKNOWN:
                    self.focus(kind)  # repeated unknown publication must not reset
                self.key(ch)
            self.assertEqual(self.screen, "tiếng")

    def test_same_attributes_new_field_clears_buffer(self):
        self.focus(Kind.TEXT, 1)
        self.key("a")
        self.focus(Kind.TEXT, 2)
        self.key("w", keycode=13)
        self.assertEqual(self.screen, "aw")

    def test_secure_and_eng_never_compose(self):
        for kind, enabled in ((Kind.SECURE, True), (Kind.TEXT, False)):
            self.hook.enabled = enabled
            self.focus(kind)
            start = len(self.trace)
            self.event(True, 0, "a")
            self.event(True, 13, "w")
            self.assertEqual(len(self.trace) - start, 2)
            self.assertFalse(self.hid)

    def test_raw_gesture_remains_raw_across_text_focus(self):
        self.focus(Kind.SURFACE)
        self.event(True, 0, "a")
        self.focus(Kind.TEXT)
        self.event(True, 0, "a", repeat=True)
        self.event(False, 0, "a")
        self.assertFalse(self.hid)
        self.key("a")
        self.key("w", keycode=13)
        self.assertTrue(self.screen.endswith("ă"))

    def test_old_raw_repeat_does_not_reset_new_chat_composition(self):
        self.focus(Kind.SURFACE)
        self.event(True, 13, "w")
        self.focus(Kind.TEXT)
        self.event(True, 0, "a", pump=True)
        self.event(False, 0, "a")
        self.event(True, 13, "w", repeat=True)
        self.assertEqual(self.hook.engine.result_str(), "a")
        self.event(True, 0, "a", pump=True)
        self.assertEqual(self.hook.engine.result_str(), "â")

    def test_old_queue_is_raw_in_new_context_and_ordered(self):
        self.focus(Kind.TEXT)
        self.key("a")
        self.key("s", keycode=1, pump=False)
        source = [self.event(True, 0, "a")]
        self.focus(Kind.SURFACE, 2)
        source += [self.event(True, 13, "w"), self.event(False, 0, "a"),
                   self.event(False, 13, "w")]
        self.pump()
        physical = [e for e in self.trace if self.q.kCGEventSourceUserData not in e]
        self.assertEqual(physical[-4:], source)
        self.assertFalse(self.hook._pending)
        self.assertFalse(self.hook._replacing)
        self.assertFalse(self.held)

    def test_old_completion_cannot_finish_new_batch(self):
        self.key("a")
        self.key("s", keycode=1, pump=False)
        old_end = self.hid[-1].copy()
        self.pump()
        self.key("f", keycode=3, pump=False)
        self.assertTrue(self.hook._replacing)
        self.hook.keyboard_callback("proxy", self.q.kCGEventKeyUp, old_end, None)
        self.assertTrue(self.hook._replacing)
        self.pump()
        self.assertFalse(self.hook._replacing)

    def test_missing_end_recovers_physical_queue_on_next_event(self):
        self.key("a")
        self.key("w", keycode=13, pump=False)
        self.hid.clear()  # lost native completion; do not pretend this is a normal batch
        source = [self.event(True, 2, "d"), self.event(False, 2, "d")]
        self.now += 1
        source.append(self.event(True, 1, "s"))
        self.assertEqual(self.trace[-3:], source)
        self.assertFalse(self.hook._replacing)
        self.assertFalse(self.hook._pending)

    def test_tap_disabled_flushes_queued_physical_release(self):
        self.key("a")
        self.key("w", keycode=13, pump=False)
        source = [self.event(True, 2, "d"), self.event(False, 2, "d")]
        self.hook.keyboard_callback("proxy", self.q.kCGEventTapDisabledByTimeout, {}, None)
        self.assertEqual(self.trace[-2:], source)
        self.assertFalse(self.hook._pending)

    def test_shortcut_cancelled_by_raw_movement(self):
        self.focus(Kind.SURFACE)
        toggle = Mock()
        self.hook._on_toggle = toggle
        flags = self.q.kCGEventFlagMaskControl | self.q.kCGEventFlagMaskShift
        def modifiers(value):
            self.hook.keyboard_callback("proxy", self.q.kCGEventFlagsChanged, {"flags": value}, None)
        modifiers(flags)
        self.event(True, 0, "a", flags)
        modifiers(0)
        toggle.assert_not_called()
        modifiers(flags)
        modifiers(0)
        toggle.assert_called_once()

    def test_stale_worker_result_cannot_restore_previous_context(self):
        old_epoch = self.hook.focus_epoch()
        self.hook.invalidate_context()
        self.hook.publish_focus(Snapshot(epoch=old_epoch, pid=42, kind=Kind.SURFACE,
                                         observed_at=self.now, element=1))
        for ch in "aw": self.key(ch)
        self.assertEqual(self.screen, "ă")
