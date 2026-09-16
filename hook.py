import os
import logging
import time
from collections import deque

import Quartz

from engine import VietelexEngine
from shortcut import ModifierShortcut
from focus import Kind, Snapshot, RAW_KINDS, current

log = logging.getLogger(__name__)

engine    = VietelexEngine()
enabled   = True
reset_on_mouse_click = True
_tap = None
_source = None
_on_toggle = None
_on_status = None
shortcut = ModifierShortcut(
    Quartz.kCGEventFlagMaskControl | Quartz.kCGEventFlagMaskShift,
    Quartz.kCGEventFlagMaskControl | Quartz.kCGEventFlagMaskShift |
    Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskAlternate |
    Quartz.kCGEventFlagMaskSecondaryFn,
)

RESET_KEYCODES = {
    36,
    48,
    49,
    51,
    53,
    123, 124, 125, 126,
    115, 119, 116, 121,
    71, 76,
}

RESET_EVENT_TYPES = {
    Quartz.kCGEventLeftMouseDown,
    Quartz.kCGEventRightMouseDown,
    Quartz.kCGEventOtherMouseDown,
}

# Unicode replacements must enter through HID, as in the original version.
# Tag our events instead of ignoring all keyboard input during replacement.
_TAG_BASE = (os.getpid() << 32) | 0x5649
_EVENT_TAG = _TAG_BASE
_END_TAG = _EVENT_TAG + 1
_replacing = False
_pending = deque()
_replacement_started = 0.0
_REPLACEMENT_TIMEOUT = 0.5
_clock = time.monotonic
_focus = Snapshot()
_focus_epoch = 0
_route_signature = None
_input_epoch = 0
_held = {}  # physical keycode -> raw latch until release
_last_route_log = None
_transition_started = None
_transition_text_seen = None
_TRANSITION_TIMEOUT = 0.5
_TEXT_CONFIRM_INTERVAL = 0.08
_refresh_requested = False


def invalidate_context():
    """Main-thread boundary; queued physical events retain their arrival epoch."""
    global _focus, _focus_epoch, _input_epoch, _route_signature
    global _transition_started, _transition_text_seen, _refresh_requested
    _focus_epoch += 1
    _input_epoch += 1
    _focus = Snapshot(epoch=_focus_epoch)
    _route_signature = None
    _transition_started = _transition_text_seen = None
    _refresh_requested = False
    engine.clear()
    shortcut.reset()
    # Do not reinterpret a repeat of a pre-boundary press as fresh text.
    for code in _held:
        _held[code] = True
    return _focus_epoch


def publish_focus(snapshot):
    global _focus, _transition_started, _transition_text_seen
    if snapshot.epoch == _focus_epoch:
        if snapshot.observed_at < _focus.observed_at:
            return
        _focus = snapshot
        if (_transition_started is not None and snapshot.observed_at > _transition_started
                and current(snapshot, _focus_epoch, _clock())):
            if snapshot.kind in RAW_KINDS:
                _transition_started = _transition_text_seen = None
            elif snapshot.kind == Kind.TEXT:
                # Do not trust a single in-flight/read-too-early sample just
                # after Enter was delivered; confirm text with another sample.
                if _transition_text_seen is None:
                    _transition_text_seen = (snapshot.element, snapshot.observed_at)
                elif snapshot.element != _transition_text_seen[0]:
                    _transition_text_seen = (snapshot.element, snapshot.observed_at)
                elif snapshot.observed_at - _transition_text_seen[1] >= _TEXT_CONFIRM_INTERVAL:
                    _transition_started = _transition_text_seen = None
        elif _transition_started is not None and snapshot.kind == Kind.UNKNOWN:
            _transition_text_seen = None
        _sync_route()


def focus_epoch():
    return _focus_epoch


def consume_focus_refresh():
    global _refresh_requested
    result = _refresh_requested
    _refresh_requested = False
    return result


def _focus_may_change():
    global _transition_started, _transition_text_seen, _refresh_requested
    if (enabled and current(_focus, _focus_epoch, _clock())
            and _focus.kind == Kind.TEXT and _focus.control_context):
        _transition_started = _clock()
        _transition_text_seen = None
        _refresh_requested = True
        _sync_route()


def _sync_route():
    global _route_signature, _input_epoch, _last_route_log
    global _transition_started, _transition_text_seen
    now = _clock()
    if _transition_started is not None and now - _transition_started >= _TRANSITION_TIMEOUT:
        _transition_started = _transition_text_seen = None
    guarding = _transition_started is not None
    valid = current(_focus, _focus_epoch, now)
    raw = not enabled or guarding or (valid and _focus.kind in RAW_KINDS)
    if log.isEnabledFor(logging.INFO):
        diagnostic = ("RAW" if raw else "LEGACY", _focus.pid, _focus.kind.value,
                      valid, enabled, _focus.reason, guarding)
        if diagnostic != _last_route_log:
            log.info("focus route=%s pid=%s kind=%s usable=%s VIE=%s reason=%s transition=%s", *diagnostic)
            _last_route_log = diagnostic
    signature = ((_focus.pid, _focus.window, _focus.element, _focus.kind, enabled, guarding)
                 if valid else ("legacy", enabled, guarding))
    if signature != _route_signature:
        # Steady UNKNOWN must not reset composition on every event or poll.
        if _route_signature is not None:
            engine.clear()
            _input_epoch += 1
        _route_signature = signature
        if raw:
            for code in _held:
                _held[code] = True
    return raw


def _physical_route(event_type, event):
    raw = _sync_route()
    if event_type in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp):
        code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        if event_type == Quartz.kCGEventKeyUp:
            raw = _held.pop(code, False) or raw
        else:
            repeat = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat)
            raw = raw or (bool(repeat) and _held.get(code, False))
            _held[code] = raw
    return raw


def _post_key(src, keycode, down, text=None, final=False):
    event = Quartz.CGEventCreateKeyboardEvent(src, keycode, down)
    Quartz.CGEventSetFlags(event, 0)
    Quartz.CGEventSetIntegerValueField(
        event, Quartz.kCGEventSourceUserData, _END_TAG if final else _EVENT_TAG)
    if text is not None:
        Quartz.CGEventKeyboardSetUnicodeString(event, len(text), text)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def send_replacement(delete_n: int, text: str):
    global _replacing, _EVENT_TAG, _END_TAG, _replacement_started
    if not delete_n and not text:
        return
    _EVENT_TAG += 2
    _END_TAG = _EVENT_TAG + 1
    _replacing = True
    _replacement_started = _clock()
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    for i in range(delete_n):
        _post_key(src, 51, True)
        _post_key(src, 51, False, final=(not text and i == delete_n - 1))
        time.sleep(0.004)
    for i, ch in enumerate(text):
        _post_key(src, 0, True, ch)
        _post_key(src, 0, False, ch, final=(i == len(text) - 1))
        time.sleep(0.003)


def _finish_replacement(proxy, event):
    global _replacing
    # Deliver the final keyup before any physical events held behind it.
    Quartz.CGEventTapPostEvent(proxy, event)
    _replacing = False
    _drain_pending(proxy)


def _drain_pending(proxy, force_raw=False):
    while _pending and not _replacing:
        _sync_route()
        event_type, queued, raw, epoch = _pending.popleft()
        raw = raw or force_raw or epoch != _input_epoch
        if raw and epoch != _input_epoch:
            engine.clear()
        result = _handle_event(proxy, event_type, queued, None, raw=raw)
        if result is not None:
            Quartz.CGEventTapPostEvent(proxy, result)


def _recover_replacement(proxy):
    global _replacing, _input_epoch
    _replacing = False
    _input_epoch += 1
    engine.clear()
    _drain_pending(proxy, force_raw=True)


def keyboard_callback(proxy, event_type, event, refcon):
    global _replacing
    if event_type in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
        result = _handle_event(proxy, event_type, event, refcon)
        _held.clear()
        _recover_replacement(proxy)
        return result

    tag = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUserData)
    if tag == _END_TAG and _replacing:
        _finish_replacement(proxy, event)
        return None
    if _TAG_BASE <= tag <= _END_TAG:
        # Old completion tags may pass, but cannot complete a newer batch.
        return event
    if _replacing and _clock() - _replacement_started > _REPLACEMENT_TIMEOUT:
        _recover_replacement(proxy)
    raw = _physical_route(event_type, event)
    if _replacing:
        _pending.append((event_type, Quartz.CGEventCreateCopy(event), raw, _input_epoch))
        return None
    return _handle_event(proxy, event_type, event, refcon, raw=raw)


def _handle_event(proxy, event_type, event, refcon, raw=False):
    if event_type in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
        engine.clear()
        shortcut.reset()
        if _tap is not None:
            Quartz.CGEventTapEnable(_tap, True)
            if _on_status:
                _on_status(bool(Quartz.CGEventTapIsEnabled(_tap)))
        return event

    if event_type == Quartz.kCGEventFlagsChanged:
        if shortcut.update(Quartz.CGEventGetFlags(event)) and _on_toggle:
            _on_toggle()
        return event

    if event_type in RESET_EVENT_TYPES:
        _focus_may_change()
        shortcut.cancel()
        if reset_on_mouse_click:
            engine.clear()
        return event

    if event_type != Quartz.kCGEventKeyDown:
        return event

    shortcut.cancel()
    keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
    if keycode in (36, 76, 53, 48):
        if not Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat):
            _focus_may_change()
    if raw:
        # Route boundaries already clear composition. A movement key held
        # across opening chat must not erase newly typed text on each repeat.
        return event
    flags    = Quartz.CGEventGetFlags(event)
    mod_mask = (Quartz.kCGEventFlagMaskCommand |
                Quartz.kCGEventFlagMaskControl  |
                Quartz.kCGEventFlagMaskAlternate)
    if flags & mod_mask:
        engine.clear()
        return event

    if keycode == 51:
        engine.backspace()
        return event

    if keycode in RESET_KEYCODES:
        engine.clear()
        return event

    length, chars = Quartz.CGEventKeyboardGetUnicodeString(event, 8, None, None)
    if length != 1 or len(chars or "") != 1 or not (32 <= ord(chars) < 127):
        engine.clear()
        return event

    ch = chars

    if not enabled:
        if ch in (' ', '\t', '\n', '\r'):
            engine.clear()

        return event

    delete_n, insert_str = engine.process(ch)

    if delete_n == 0 and insert_str == ch:
        return event

    send_replacement(delete_n, insert_str)
    return None

def start(on_toggle=None, on_status=None):
    """Install the tap on the main run loop; report failure to the menu UI."""
    global _tap, _source, _on_toggle, _on_status
    _on_toggle, _on_status = on_toggle, on_status
    invalidate_context()
    if _tap is not None:
        Quartz.CGEventTapEnable(_tap, True)
        ready = bool(Quartz.CGEventTapIsEnabled(_tap))
        if _on_status:
            _on_status(ready)
        return ready
    tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionDefault,
        (Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown) |
         Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp) |
         Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged) |
         Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseDown) |
         Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseDown) |
         Quartz.CGEventMaskBit(Quartz.kCGEventOtherMouseDown)),
        keyboard_callback,
        None,
    )
    if tap is None:
        if _on_status:
            _on_status(False)
        return False

    _tap = tap
    _source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    Quartz.CFRunLoopAddSource(
        Quartz.CFRunLoopGetMain(), _source, Quartz.kCFRunLoopCommonModes)
    Quartz.CGEventTapEnable(tap, True)
    ready = bool(Quartz.CGEventTapIsEnabled(tap))
    if _on_status:
        _on_status(ready)
    return ready
