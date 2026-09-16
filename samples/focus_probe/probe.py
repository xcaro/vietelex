#!/usr/bin/env python3
"""AX focus experiment; never installs a keyboard hook or reads text.

Read-only by default; --enable-accessibility requests enhanced AX support.
"""

import argparse
from dataclasses import asdict, dataclass, field
import json
import sys
import time


TEXT_ROLES = {"AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"}
NON_TEXT_ROLES = {
    "AXButton", "AXCheckBox", "AXRadioButton", "AXPopUpButton", "AXSlider",
    "AXMenu", "AXMenuItem", "AXMenuBarItem", "AXLink", "AXStaticText",
    "AXTabGroup", "AXToolbar", "AXImage",
}
AX_ERRORS = {
    -25200: "failure", -25201: "illegal_argument", -25202: "invalid_element",
    -25204: "cannot_complete", -25205: "attribute_unsupported",
    -25206: "action_unsupported", -25208: "not_implemented",
    -25211: "api_disabled", -25212: "no_value",
}


@dataclass
class Focus:
    app: str = ""
    pid: int | None = None
    focus_id: int | None = None
    source: str = "app"
    role: str | None = None
    subrole: str | None = None
    enabled: bool | None = None
    value_settable: bool | None = None
    selection_settable: bool | None = None
    errors: dict = field(default_factory=dict)
    unavailable: str | None = None
    activation: dict = field(default_factory=dict)


def classify(focus):
    """Return an evidence-based candidate, not proof that Telex is safe here."""
    if focus.unavailable:
        return "UNKNOWN", focus.unavailable
    if focus.subrole == "AXSecureTextField" or focus.role == "AXSecureTextField":
        return "SECURE", "Password field: do not compose Vietnamese here"
    if focus.enabled is False:
        return "NON_TEXT", "Focused control is disabled"
    if not focus.role:
        return "UNKNOWN", "Focused element has no readable role"
    if focus.role in NON_TEXT_ROLES:
        return "NON_TEXT", "Focused role identifies a non-text control"
    if focus.role in TEXT_ROLES:
        if focus.value_settable is True:
            return "TEXT", "Text role with writable AXValue"
        # A false result does NOT prove readonly: some editors accept typing
        # but do not let accessibility clients replace their AXValue.
        return "UNKNOWN", "Text role, but writable text is not confirmed"
    if focus.value_settable is True and focus.selection_settable is True:
        return "TEXT", "Custom element exposes writable value and text selection"
    # Windows, web areas, groups, canvases and missing AX implementations can
    # conceal both text editors and gameplay. Never guess from Enter or app name.
    return "UNKNOWN", "Container/custom surface without enough text evidence"


class MacProbe:
    def __init__(self, timeout, source="app", enable_accessibility=False):
        import ApplicationServices as AX
        from Cocoa import NSDate, NSRunLoop, NSRunningApplication, NSWorkspace
        from CoreFoundation import CFEqual

        self.ax = AX
        self.running_app = NSRunningApplication.runningApplicationWithProcessIdentifier_
        self.same_element = CFEqual
        self.system = AX.AXUIElementCreateSystemWide()
        self.workspace = NSWorkspace.sharedWorkspace()
        self.pump = lambda seconds: NSRunLoop.currentRunLoop().runUntilDate_(
            NSDate.dateWithTimeIntervalSinceNow_(seconds))
        self.source = source
        self.last_element = None
        self.focus_serial = 0
        self.timeout = timeout
        self.enable_accessibility = enable_accessibility
        self.activation_results = {}

    def trusted(self):
        return bool(self.ax.AXIsProcessTrusted())

    def frontmost(self):
        # Service Cocoa notifications before reading cached NSWorkspace state.
        self.pump(0.01)
        return self.workspace.frontmostApplication()

    def wait(self, seconds):
        started = time.monotonic()
        self.pump(seconds)
        # A run loop with no sources may return early; avoid spinning.
        remaining = seconds - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)

    def prepare_application(self, target, pid):
        if pid not in self.activation_results:
            # Chromium uses this read as a signal to expose basic AX support.
            status, role = self.ax.AXUIElementCopyAttributeValue(target, "AXRole", None)
            result = {"app_role": str(role) if not status else self.error_name(status)}
            if self.enable_accessibility:
                # One request per PID. Repeated requests can keep restarting
                # Chromium's delayed accessibility activation countdown.
                status = self.ax.AXUIElementSetAttributeValue(
                    target, "AXEnhancedUserInterface", True)
                result["AXEnhancedUserInterface"] = "ok" if not status else self.error_name(status)
            self.activation_results[pid] = result
        return self.activation_results[pid].copy()

    def sample(self):
        if not self.trusted():
            return Focus(source=self.source, unavailable="Accessibility permission unavailable")
        focus = Focus(source=self.source)
        if self.source == "app":
            app = self.frontmost()
            if app is None:
                focus.unavailable = "No frontmost application"
                return focus
            focus.pid = int(app.processIdentifier())
            focus.app = str(app.localizedName() or "")
            target = self.ax.AXUIElementCreateApplication(focus.pid)
        else:
            target = self.system
        status = self.ax.AXUIElementSetMessagingTimeout(target, self.timeout)
        if status:
            focus.unavailable = "Could not set AX messaging timeout"
            focus.errors["timeout"] = self.error_name(status)
            return focus
        if self.source == "app":
            focus.activation = self.prepare_application(target, focus.pid)
        element = self.read(target, "AXFocusedUIElement", focus)
        if element is None:
            focus.unavailable = "No accessible focused element"
            return focus
        status, pid = self.ax.AXUIElementGetPid(element, None)
        if status:
            focus.errors["pid"] = self.error_name(status)
            focus.unavailable = "Could not identify focused application"
            return focus
        if self.source == "app" and int(pid) != focus.pid:
            focus.unavailable = "Focused element belongs to a different application"
            return focus
        if self.source == "system":
            focus.pid = int(pid)
            app = self.running_app(focus.pid)
            focus.app = str(app.localizedName() or "") if app is not None else ""
        # Timeout on the actual target as well; AX calls stay out of event taps.
        status = self.ax.AXUIElementSetMessagingTimeout(element, self.timeout)
        if status:
            focus.unavailable = "Could not set focused-element timeout"
            focus.errors["timeout"] = self.error_name(status)
            return focus
        focus.role = self.read(element, "AXRole", focus)
        focus.subrole = self.read(element, "AXSubrole", focus)
        if focus.subrole != "AXSecureTextField" and focus.role != "AXSecureTextField":
            enabled = self.read(element, "AXEnabled", focus)
            focus.enabled = None if enabled is None else bool(enabled)
            focus.value_settable = self.settable(element, "AXValue", focus)
            focus.selection_settable = self.settable(element, "AXSelectedTextRange", focus)
        if self.source == "app":
            latest_app = self.frontmost()
            if latest_app is None or int(latest_app.processIdentifier()) != focus.pid:
                focus.unavailable = "Application changed during sample; retry next poll"
                return focus
        latest = self.read(target, "AXFocusedUIElement", focus)
        if latest is None or not self.same_element(latest, element):
            focus.unavailable = "Focus changed or became unavailable during sample; retry next poll"
        elif any(error in {"cannot_complete", "invalid_element", "api_disabled", "failure"}
                 for error in focus.errors.values()):
            focus.unavailable = "AX query failed; retry next poll"
        if not focus.unavailable:
            if self.last_element is None or not self.same_element(element, self.last_element):
                self.focus_serial += 1
            self.last_element = element
            focus.focus_id = self.focus_serial
        return focus

    @staticmethod
    def error_name(status):
        return AX_ERRORS.get(int(status), f"ax_error_{int(status)}")

    def read(self, element, attribute, focus):
        status, value = self.ax.AXUIElementCopyAttributeValue(element, attribute, None)
        if status:
            focus.errors[attribute] = self.error_name(status)
            return None
        return value

    def settable(self, element, attribute, focus):
        # Query capability only. Never retrieve AXValue/AXSelectedText contents.
        status, value = self.ax.AXUIElementIsAttributeSettable(element, attribute, None)
        if status:
            focus.errors[attribute + ".settable"] = self.error_name(status)
            return None
        return bool(value)


def record(focus):
    state, reason = classify(focus)
    return dict(state=state, reason=reason, **asdict(focus))


class OutputChanges:
    """Report attribute changes; ignore incidental focus identity changes."""

    def __init__(self, every_sample=False):
        self.every_sample = every_sample
        self.previous = None

    def should_emit(self, current):
        attributes = {key: value for key, value in current.items() if key != "focus_id"}
        if self.every_sample or attributes != self.previous:
            self.previous = attributes
            return True
        return False


def positive_float(value):
    value = float(value)
    if not 0 < value < float("inf"):
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=positive_float, default=0.25, help="poll delay, seconds")
    parser.add_argument("--timeout", type=positive_float, default=1.0, help="timeout per AX call, seconds")
    parser.add_argument("--source", choices=("app", "system"), default="app",
                        help="focus query route: app (default) or system for comparison")
    parser.add_argument("--enable-accessibility", action="store_true",
                        help="request AXEnhancedUserInterface once per app process (app source only)")
    parser.add_argument("--duration", type=positive_float, help="stop after this many seconds")
    parser.add_argument("--json", action="store_true", help="emit JSONL")
    parser.add_argument("--all", action="store_true", help="debug: print every sample, including duplicates")
    args = parser.parse_args()
    if args.enable_accessibility and args.source != "app":
        parser.error("--enable-accessibility requires --source app")
    if sys.platform != "darwin":
        parser.exit(2, "Live focus probing requires macOS. Classifier tests run on any OS.\n")
    print("Starting focus probe...", file=sys.stderr, flush=True)
    try:
        probe = MacProbe(args.timeout, args.source, args.enable_accessibility)
    except ImportError:
        parser.exit(2, "Install dependencies: python3 -m pip install pyobjc-framework-Cocoa "
                    "pyobjc-framework-ApplicationServices\n")
    if not probe.trusted():
        parser.exit(2, "Accessibility permission unavailable. Allow your Terminal/Python launcher in\n"
                    "System Settings > Privacy & Security > Accessibility, then restart it.\n"
                    "No keyboard events were intercepted.\n")
    print(f"Live AX focus via {args.source}; timeout {args.timeout:g}s; "
          f"logging {'every sample' if args.all else 'attribute changes only'}. Ctrl+C stops. "
          "No key/text contents are recorded.", file=sys.stderr, flush=True)
    if args.enable_accessibility:
        print("Enhanced accessibility requests enabled. Allow a few seconds for apps to expose focus.",
              file=sys.stderr, flush=True)
    output = OutputChanges(every_sample=args.all)
    started = time.monotonic()
    try:
        while args.duration is None or time.monotonic() - started < args.duration:
            # Bound Objective-C temporary objects in this long-running CLI loop.
            from objc import autorelease_pool
            with autorelease_pool():
                current = record(probe.sample())
            if output.should_emit(current):
                if args.json:
                    print(json.dumps(dict(time=time.strftime("%H:%M:%S"), **current), ensure_ascii=False), flush=True)
                else:
                    print(f"{time.strftime('%H:%M:%S')} {current['state']:8} "
                          f"source={current['source']} app={current['app']!r} pid={current['pid']} "
                          f"focus={current['focus_id']} role={current['role']} "
                          f"subrole={current['subrole']} value_settable={current['value_settable']} "
                          f"selection_settable={current['selection_settable']} "
                          f"— {current['reason']} errors={current['errors']} "
                          f"activation={current['activation']}", flush=True)
            with autorelease_pool():
                probe.wait(args.interval)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
