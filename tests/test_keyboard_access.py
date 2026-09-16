import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class KeyboardAccessTests(unittest.TestCase):
    def test_modeless_actions_and_reopening(self):
        alert, window, application = Mock(), Mock(), Mock()
        retry_button, close_button, retry = Mock(), Mock(), Mock()
        alert.window.return_value = window
        alert.addButtonWithTitle_.side_effect = [retry_button, close_button]
        alert.runModal.side_effect = AssertionError("Must not enter a modal run loop")
        cocoa = types.SimpleNamespace(
            NSObject=object, NSAlert=Mock(), NSApplication=Mock(),
            NSFloatingWindowLevel=3)
        cocoa.NSAlert.alloc.return_value.init.return_value = alert
        cocoa.NSApplication.sharedApplication.return_value = application
        spec = importlib.util.spec_from_file_location(
            "tested_keyboard_access", Path(__file__).resolve().parents[1] / "keyboard_access.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, Cocoa=cocoa,
                        objc=types.SimpleNamespace(python_method=lambda method: method)):
            spec.loader.exec_module(module)
        panel = module.KeyboardAccessPanel()
        panel.configure(retry)
        panel.show()
        retry.assert_not_called()
        alert.runModal.assert_not_called()
        application.activateIgnoringOtherApps_.assert_called_with(True)
        window.makeKeyAndOrderFront_.assert_called_once_with(None)
        retry_button.setTarget_.assert_called_once_with(panel)
        retry_button.setAction_.assert_called_once_with("retry:")
        close_button.setAction_.assert_called_once_with("close:")
        close_button.setKeyEquivalent_.assert_called_once_with("\x1b")
        panel.close_(None)
        retry.assert_not_called()
        window.orderOut_.assert_called_once_with(None)
        panel.show()
        panel.retry_(None)
        retry.assert_called_once_with()
        self.assertEqual(window.orderOut_.call_count, 2)
        self.assertEqual(cocoa.NSAlert.alloc.call_count, 1)


if __name__ == "__main__":
    unittest.main()
