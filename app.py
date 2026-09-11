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
        import rumps
    except ImportError:
        missing.append("rumps")
    if missing:
        print(f"Installing missing dependencies: {', '.join(missing)} ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing)
        print("Dependencies installed. Restarting...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

ensure_deps()

import rumps
import hook

def _on_off(value: bool) -> str:
    return "on" if value else "off"

def _parse_on_off(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in ("on", "true", "yes", "1"):
        return True
    if normalized in ("off", "false", "no", "0"):
        return False
    return None

def on_quit(_):
    rumps.quit_application()

class TelexApp(rumps.App):
    def __init__(self):
        super().__init__("VIE", quit_button=None)

        self._hook_ready = False
        self._validator_enabled = True
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
            rumps.MenuItem("Preferences...", callback=self._on_preferences),
            rumps.MenuItem("About VietElex", callback=self._on_about),
            None,
            rumps.MenuItem("Quit", callback=on_quit),
        ]

        hook.start(on_toggle=self._toggle, on_status=self._on_hook_status)

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
            message=("Allow VietElex (or Terminal when running from source) in "
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

    def _on_preferences(self, _):
        window = rumps.Window(
            title="VietElex Preferences",
            message=(
                "Edit values, then Save.\n"
                "Allowed values: on/off"
            ),
            default_text=(
                f"validator={_on_off(self._validator_enabled)}\n"
                f"reset_on_click={_on_off(hook.reset_on_mouse_click)}"
            ),
            ok="Save",
            cancel="Cancel",
            dimensions=(360, 96),
        )
        response = window.run()
        if not response.clicked:
            return

        updates: dict[str, bool] = {}
        for line in response.text.splitlines():
            if not line.strip() or line.strip().startswith("#"):
                continue
            if "=" not in line:
                self._show_preferences_error(line)
                return
            key, value = line.split("=", 1)
            parsed = _parse_on_off(value)
            if key.strip() not in ("validator", "reset_on_click") or parsed is None:
                self._show_preferences_error(line)
                return
            updates[key.strip()] = parsed

        if "validator" in updates:
            self._validator_enabled = updates["validator"]
            hook.engine.set_validator_enabled(self._validator_enabled)
        if "reset_on_click" in updates:
            hook.reset_on_mouse_click = updates["reset_on_click"]

    def _show_preferences_error(self, line: str):
        rumps.alert(
            title="Invalid Preferences",
            message=f"Could not parse: {line}\nUse validator=on/off and reset_on_click=on/off.",
            ok="Close",
        )

    def _on_about(self, _):
        rumps.alert(
            title="VietElex",
            message=(
                "Simple Telex input for Vietnamese.\n\n"
                "Ctrl+Shift: toggle Telex/ABC\n"
                "Reset Buffer: clear current engine state\n"
                "Mouse click into an input resets the buffer\n\n"
                "Rules: aw, ow, uw, aa, ee, oo, dd\n"
                "Tones: s f r x j z"
            ),
            ok="Close",
        )

if __name__ == "__main__":
    TelexApp().run()
