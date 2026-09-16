"""Modeless permission help; keep the menu and default run loop available."""

import objc
from Cocoa import NSObject, NSAlert, NSApplication, NSFloatingWindowLevel


class KeyboardAccessPanel(NSObject):
    @objc.python_method
    def configure(self, retry):
        self._retry = retry
        self._alert = NSAlert.alloc().init()
        self._alert.setMessageText_("Keyboard Access")
        self._alert.setInformativeText_(
            "Allow VieTelex (or Terminal when running from source) in "
            "System Settings → Privacy & Security → Accessibility.\n\n"
            "Then choose Retry. If access is still unavailable, restart the app.")
        retry_button = self._alert.addButtonWithTitle_("Retry")
        close_button = self._alert.addButtonWithTitle_("Close")
        # Lay out the alert without entering runModal: modal mode disables the
        # status menu and prevents rumps' default-mode Mach SIGINT delivery.
        self._alert.layout()
        for button, action in ((retry_button, "retry:"), (close_button, "close:")):
            button.setTarget_(self)
            button.setAction_(action)
        close_button.setKeyEquivalent_("\x1b")
        self._window = self._alert.window()
        self._window.setReleasedWhenClosed_(False)
        self._window.setLevel_(NSFloatingWindowLevel)
        self._window.setHidesOnDeactivate_(False)
        self._window.center()

    @objc.python_method
    def show(self):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self._window.makeKeyAndOrderFront_(None)

    def retry_(self, sender):
        self.close_(sender)
        self._retry()

    def close_(self, sender):
        self._window.orderOut_(None)
