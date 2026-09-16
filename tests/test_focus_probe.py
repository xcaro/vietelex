import unittest
from types import SimpleNamespace

from samples.focus_probe.probe import Focus, MacProbe, OutputChanges, classify, record


class ClassificationTests(unittest.TestCase):
    def test_common_controls(self):
        cases = [
            (Focus(role="AXTextField", value_settable=True), "TEXT"),
            (Focus(role="AXTextArea", value_settable=True), "TEXT"),
            (Focus(role="AXComboBox", value_settable=True), "TEXT"),
            (Focus(role="AXGroup", value_settable=True, selection_settable=True), "TEXT"),
            (Focus(role="AXTextField", subrole="AXSecureTextField", value_settable=True), "SECURE"),
            (Focus(role="AXTextField", enabled=False, value_settable=True), "NON_TEXT"),
            (Focus(role="AXButton", value_settable=True), "NON_TEXT"),
            (Focus(role="AXSlider", value_settable=True), "NON_TEXT"),
            (Focus(role="AXStaticText", selection_settable=True), "NON_TEXT"),
            (Focus(role="AXPopUpButton", value_settable=True), "NON_TEXT"),
            (Focus(role="AXTextField", value_settable=False), "UNKNOWN"),
            (Focus(role="AXTextArea", selection_settable=True), "UNKNOWN"),
            (Focus(role="AXWebArea", selection_settable=True), "UNKNOWN"),
            (Focus(role="AXGroup", value_settable=True), "UNKNOWN"),
            (Focus(role="AXWindow"), "UNKNOWN"),
            (Focus(), "UNKNOWN"),
            (Focus(role="AXTextField", value_settable=True, unavailable="timeout"), "UNKNOWN"),
        ]
        for focus, expected in cases:
            with self.subTest(focus=focus):
                self.assertEqual(classify(focus)[0], expected)


class FakeAX:
    def __init__(self):
        self.attributes = {
            "AXFocusedUIElement": (0, "element"),
            "AXRole": (0, "AXTextField"),
            "AXSubrole": (-25205, None),
            "AXEnabled": (0, True),
        }
        self.reads = []
        self.targets = []
        self.trusted = True
        self.writes = []

    def AXIsProcessTrusted(self):
        return self.trusted

    def AXUIElementGetPid(self, element, out):
        return 0, 99 if element == "other_app_element" else 42

    def AXUIElementCreateApplication(self, pid):
        return f"app:{pid}"

    def AXUIElementSetMessagingTimeout(self, element, timeout):
        return 0

    def AXUIElementCopyAttributeValue(self, element, attribute, out):
        self.reads.append(attribute)
        self.targets.append((element, attribute))
        # Raises if the probe tries to read contents or traverse other UI.
        return self.attributes[attribute]

    def AXUIElementIsAttributeSettable(self, element, attribute, out):
        return 0, True

    def AXUIElementSetAttributeValue(self, element, attribute, value):
        self.writes.append((element, attribute, value))
        return 0


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.probe = MacProbe.__new__(MacProbe)
        self.probe.ax = FakeAX()
        self.probe.timeout = 0.1
        self.probe.system = "system"
        self.probe.source = "system"
        self.probe.enable_accessibility = False
        self.probe.activation_results = {}
        self.probe.same_element = lambda a, b: a == b
        self.probe.last_element = None
        self.probe.focus_serial = 0
        self.probe.running_app = lambda pid: SimpleNamespace(localizedName=lambda: f"Example {pid}")

    def test_reads_only_metadata(self):
        result = self.probe.sample()
        self.assertEqual(classify(result)[0], "TEXT")
        self.assertEqual(set(self.probe.ax.reads), {
            "AXFocusedUIElement", "AXRole", "AXSubrole", "AXEnabled"})

    def test_secure_field_skips_capability_queries(self):
        self.probe.ax.attributes["AXSubrole"] = (0, "AXSecureTextField")
        def forbidden(*args):
            self.fail("Secure field should not need further queries")
        self.probe.ax.AXUIElementIsAttributeSettable = forbidden
        self.assertEqual(classify(self.probe.sample())[0], "SECURE")

    def test_permission_denied_returns_unknown_without_queries(self):
        self.probe.ax.trusted = False
        self.assertEqual(classify(self.probe.sample())[0], "UNKNOWN")
        self.assertEqual(self.probe.ax.reads, [])

    def test_focus_failure_does_not_reuse_previous_text_result(self):
        self.assertEqual(classify(self.probe.sample())[0], "TEXT")
        for error in (-25204, -25202, -25205, -25208, -25212):
            with self.subTest(error=error):
                self.probe.ax.attributes["AXFocusedUIElement"] = (error, None)
                result = self.probe.sample()
                self.assertEqual(classify(result)[0], "UNKNOWN")
                self.assertIn("AXFocusedUIElement", result.errors)

    def test_timeout_during_metadata_query_returns_unknown(self):
        self.probe.ax.attributes["AXEnabled"] = (-25204, None)
        self.assertEqual(classify(self.probe.sample())[0], "UNKNOWN")

    def test_app_switch_during_sample_returns_unknown(self):
        original = self.probe.ax.AXUIElementCopyAttributeValue
        elements = iter(["element", "other_app_element"])
        def read(element, attribute, out):
            if attribute == "AXFocusedUIElement":
                return 0, next(elements)
            return original(element, attribute, out)
        self.probe.ax.AXUIElementCopyAttributeValue = read
        self.assertEqual(classify(self.probe.sample())[0], "UNKNOWN")

    def test_switch_app_reads_new_focus_and_pid_without_workspace_cache(self):
        first = self.probe.sample()
        self.probe.ax.attributes["AXFocusedUIElement"] = (0, "other_app_element")
        second = self.probe.sample()
        self.assertEqual((first.pid, second.pid), (42, 99))
        self.assertEqual(second.app, "Example 99")
        self.assertNotEqual(first.focus_id, second.focus_id)

    def test_two_identical_text_fields_have_different_focus_ids(self):
        first = self.probe.sample()
        again = self.probe.sample()
        self.assertEqual(first.focus_id, again.focus_id)
        self.probe.ax.attributes["AXFocusedUIElement"] = (0, "second_field")
        second = self.probe.sample()
        self.assertEqual(first.role, second.role)
        self.assertNotEqual(first.focus_id, second.focus_id)

    def test_pid_failure_returns_unknown(self):
        self.probe.ax.AXUIElementGetPid = lambda e, out: (-25202, None)
        result = self.probe.sample()
        self.assertEqual(classify(result)[0], "UNKNOWN")
        self.assertEqual(result.errors["pid"], "invalid_element")

    def test_chat_canvas_transition_uses_focus_not_enter(self):
        states = []
        for role in ("AXGroup", "AXTextField", "AXGroup", "AXTextField", "AXButton"):
            self.probe.ax.attributes["AXRole"] = (0, role)
            self.probe.ax.AXUIElementIsAttributeSettable = lambda e, a, o: (0, role == "AXTextField")
            states.append(classify(self.probe.sample())[0])
        self.assertEqual(states, ["UNKNOWN", "TEXT", "UNKNOWN", "TEXT", "NON_TEXT"])


class AppRouteTests(ProbeTests):
    def setUp(self):
        super().setUp()
        self.probe.source = "app"
        self.active_pid = 42
        self.pending_pid = None
        self.pumps = []
        def pump(seconds):
            self.pumps.append(seconds)
            if self.pending_pid is not None:
                self.active_pid = self.pending_pid
                self.pending_pid = None
        self.probe.pump = pump
        self.probe.workspace = SimpleNamespace(frontmostApplication=lambda: SimpleNamespace(
            processIdentifier=lambda: self.active_pid,
            localizedName=lambda: f"Example {self.active_pid}"))

    def test_app_route_succeeds_when_system_focus_cannot_complete(self):
        original = self.probe.ax.AXUIElementCopyAttributeValue
        def read(element, attribute, out):
            if element == "system":
                return -25204, None
            return original(element, attribute, out)
        self.probe.ax.AXUIElementCopyAttributeValue = read
        result = self.probe.sample()
        self.assertEqual(classify(result)[0], "TEXT")
        self.assertEqual(result.source, "app")
        self.assertIn(("app:42", "AXFocusedUIElement"), self.probe.ax.targets)
        self.assertFalse(any(target == "system" for target, attr in self.probe.ax.targets))

    def test_default_reads_app_role_before_focus_without_writes(self):
        self.probe.sample()
        self.assertEqual(self.probe.ax.targets[0], ("app:42", "AXRole"))
        self.assertEqual(self.probe.ax.writes, [])

    def test_enhanced_activation_once_while_waiting_for_focus(self):
        self.probe.enable_accessibility = True
        self.probe.ax.attributes["AXFocusedUIElement"] = (-25212, None)
        first = self.probe.sample()
        second = self.probe.sample()
        self.assertEqual(first.activation["AXEnhancedUserInterface"], "ok")
        self.assertEqual(classify(second)[0], "UNKNOWN")
        self.assertEqual(self.probe.ax.writes, [("app:42", "AXEnhancedUserInterface", True)])
        self.probe.ax.attributes["AXFocusedUIElement"] = (0, "element")
        self.assertEqual(classify(self.probe.sample())[0], "TEXT")
        self.assertEqual(len(self.probe.ax.writes), 1)

    def test_unsupported_activation_does_not_hide_valid_focus(self):
        self.probe.enable_accessibility = True
        self.probe.ax.AXUIElementSetAttributeValue = lambda *args: -25205
        result = self.probe.sample()
        self.assertEqual(classify(result)[0], "TEXT")
        self.assertEqual(result.activation["AXEnhancedUserInterface"], "attribute_unsupported")

    def test_switch_app_reads_new_focus_and_pid_without_workspace_cache(self):
        first = self.probe.sample()
        # Simulate an activation notification that is only applied by Cocoa's
        # run loop. A sleep-only polling loop would keep returning app 42.
        self.pending_pid = 99
        self.probe.ax.attributes["AXFocusedUIElement"] = (0, "other_app_element")
        second = self.probe.sample()
        self.assertEqual((first.pid, second.pid), (42, 99))
        self.assertEqual(second.app, "Example 99")
        self.assertNotEqual(first.focus_id, second.focus_id)
        self.assertGreaterEqual(len(self.pumps), 4)

    def test_failed_app_query_keeps_app_name_for_diagnostics(self):
        self.probe.ax.attributes["AXFocusedUIElement"] = (-25204, None)
        result = self.probe.sample()
        self.assertEqual(classify(result)[0], "UNKNOWN")
        self.assertEqual((result.app, result.pid), ("Example 42", 42))

    def test_app_switch_during_metadata_query_discards_result(self):
        original = self.probe.ax.AXUIElementIsAttributeSettable
        def settable(element, attr, out):
            self.pending_pid = 99
            return original(element, attr, out)
        self.probe.ax.AXUIElementIsAttributeSettable = settable
        result = self.probe.sample()
        self.assertEqual(classify(result)[0], "UNKNOWN")
        self.assertIn("Application changed", result.unavailable)


class OutputTests(unittest.TestCase):
    def test_only_attribute_changes_are_visible(self):
        output = OutputChanges()
        first = record(Focus(role="AXTextField", focus_id=1))
        second = record(Focus(role="AXTextField", focus_id=2))
        self.assertTrue(output.should_emit(first))
        self.assertFalse(output.should_emit(first))
        self.assertFalse(output.should_emit(second))
        changed = record(Focus(role="AXTextArea", focus_id=2))
        self.assertTrue(output.should_emit(changed))
        self.assertFalse(output.should_emit(changed))
        self.assertTrue(output.should_emit(first))

    def test_all_prints_every_sample(self):
        output = OutputChanges(every_sample=True)
        current = record(Focus(unavailable="not supported"))
        self.assertTrue(output.should_emit(current))
        self.assertTrue(output.should_emit(current))


if __name__ == "__main__":
    unittest.main()
