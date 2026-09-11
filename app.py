#!/usr/bin/env python3

import sys
import os
import subprocess

def ensure_deps():
    missing = []
    try:
        import Cocoa
    except ImportError:
        missing.append("pyobjc-framework-Cocoa")
    try:
        import Quartz
    except ImportError:
        missing.append("pyobjc-framework-Quartz")
    try:
        import rumps
    except ImportError:
        missing.append("rumps")
    if missing and getattr(sys, "frozen", False):
        raise RuntimeError("Missing bundled dependencies: " + ", ".join(missing))
    if missing:
        print(f"Installing missing dependencies: {', '.join(missing)} ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing)
        print("Dependencies installed. Restarting...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

ensure_deps()

import rumps
import hook

from Cocoa import (
    NSUserDefaults, NSWorkspace, NSOperationQueue,
    NSWorkspaceDidActivateApplicationNotification,
    NSWorkspaceSessionDidResignActiveNotification,
    NSWorkspaceSessionDidBecomeActiveNotification,
)


def on_quit(_):
    rumps.quit_application()

class TelexApp(rumps.App):
    def __init__(self):
        super().__init__("VIE", quit_button=None)

        self._hook_ready = False
        self._defaults = NSUserDefaults.standardUserDefaults()
        self._defaults.registerDefaults_({
            "vietelex.validator": True, "vietelex.reset_on_click": True,
        })
        self._validator_enabled = bool(self._defaults.boolForKey_("vietelex.validator"))
        hook.engine.set_validator_enabled(self._validator_enabled)
        hook.reset_on_mouse_click = bool(self._defaults.boolForKey_("vietelex.reset_on_click"))
        self._validator_item = rumps.MenuItem("Phonology Validator", callback=self._on_validator)
        self._validator_item.state = self._validator_enabled
        self._reset_click_item = rumps.MenuItem("Reset on Click", callback=self._on_reset_click)
        self._reset_click_item.state = hook.reset_on_mouse_click
        preferences = rumps.MenuItem("Preferences")
        preferences.add(self._validator_item)
        preferences.add(self._reset_click_item)
        self._mode_item = rumps.MenuItem("", callback=None)
        self._mode_item.set_callback(None)
        self._toggle_item = rumps.MenuItem("", callback=self._on_toggle_click)
        self._sync_mode_ui()

        self.menu = [
            self._mode_item,
            self._toggle_item,
            rumps.MenuItem("Reset Buffer", callback=self._on_reset_buffer),
            rumps.MenuItem("Keyboard Access...", callback=self._on_keyboard_access),
            None,
            preferences,
            rumps.MenuItem("About VieTelex", callback=self._on_about),
            None,
            rumps.MenuItem("Quit", callback=on_quit),
        ]

        # Workspace notifications cover app switches that arrive without a
        # mouse click or keydown (Dock, Mission Control, session changes).
        center = NSWorkspace.sharedWorkspace().notificationCenter()
        self._workspace_observers = [
            center.addObserverForName_object_queue_usingBlock_(
                name, None, NSOperationQueue.mainQueue(), self._on_context_change)
            for name in (NSWorkspaceDidActivateApplicationNotification,
                         NSWorkspaceSessionDidResignActiveNotification,
                         NSWorkspaceSessionDidBecomeActiveNotification)
        ]
        hook.start(on_toggle=self._toggle, on_status=self._on_hook_status)

    def _on_context_change(self, _):
        hook.engine.clear()
        hook.shortcut.reset()

    def _toggle(self):
        hook.enabled = not hook.enabled
        hook.engine.clear()
        self._sync_mode_ui()

    def _sync_mode_ui(self):
        if not self._hook_ready:
            self.title = "VIE!"
            self._mode_item.title = "Keyboard access unavailable"
            self._toggle_item.title = "Retry Keyboard Access"
        elif hook.enabled:
            self.title = "VIE"
            self._mode_item.title = "Mode: Simple Telex"
            self._toggle_item.title = "Switch to ABC"
        else:
            self.title = "ENG"
            self._mode_item.title = "Mode: ABC"
            self._toggle_item.title = "Switch to Telex"

    def _on_hook_status(self, ready):
        self._hook_ready = ready
        self._sync_mode_ui()

    def _on_keyboard_access(self, _):
        rumps.alert(
            title="Keyboard Access",
            message=("Allow VieTelex (or Terminal when running from source) in "
                     "System Settings → Privacy & Security → Accessibility.\n\n"
                     "Then choose Retry. If access is still unavailable, restart the app."),
            ok="Retry",
        )
        hook.start(on_toggle=self._toggle, on_status=self._on_hook_status)

    def _on_toggle_click(self, _):
        if not self._hook_ready:
            self._on_keyboard_access(None)
        else:
            self._toggle()

    def _on_reset_buffer(self, _):
        hook.engine.clear()

    def _on_validator(self, item):
        self._validator_enabled = not self._validator_enabled
        item.state = self._validator_enabled
        hook.engine.set_validator_enabled(self._validator_enabled)
        self._defaults.setBool_forKey_(self._validator_enabled, "vietelex.validator")

    def _on_reset_click(self, item):
        hook.reset_on_mouse_click = not hook.reset_on_mouse_click
        item.state = hook.reset_on_mouse_click
        hook.engine.clear()
        self._defaults.setBool_forKey_(hook.reset_on_mouse_click, "vietelex.reset_on_click")

    def _on_about(self, _):
        from about import show_about
        show_about()

if __name__ == "__main__":
    TelexApp().run()
