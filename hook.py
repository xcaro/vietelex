import Quartz

from engine import VietelexEngine
from shortcut import ModifierShortcut

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

# Events posted through the callback proxy enter downstream of this tap, in
# order, before the next physical event. No worker or global bypass is needed.
def _post_key(proxy, src, keycode, down, text=None):
    event = Quartz.CGEventCreateKeyboardEvent(src, keycode, down)
    Quartz.CGEventSetFlags(event, 0)
    if text is not None:
        Quartz.CGEventKeyboardSetUnicodeString(event, len(text), text)
    Quartz.CGEventTapPostEvent(proxy, event)


def send_replacement(proxy, delete_n: int, text: str):
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStatePrivate)
    for _ in range(delete_n):
        _post_key(proxy, src, 51, True)
        _post_key(proxy, src, 51, False)
    for ch in text:
        _post_key(proxy, src, 0, True, ch)
        _post_key(proxy, src, 0, False, ch)


def keyboard_callback(proxy, event_type, event, refcon):
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
        shortcut.cancel()
        if reset_on_mouse_click:
            engine.clear()
        return event

    if event_type != Quartz.kCGEventKeyDown:
        return event

    shortcut.cancel()
    flags    = Quartz.CGEventGetFlags(event)
    mod_mask = (Quartz.kCGEventFlagMaskCommand |
                Quartz.kCGEventFlagMaskControl  |
                Quartz.kCGEventFlagMaskAlternate)
    if flags & mod_mask:
        engine.clear()
        return event

    keycode = Quartz.CGEventGetIntegerValueField(
        event, Quartz.kCGKeyboardEventKeycode)

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

    send_replacement(proxy, delete_n, insert_str)
    return None

def start(on_toggle=None, on_status=None):
    """Install the tap on the main run loop; report failure to the menu UI."""
    global _tap, _source, _on_toggle, _on_status
    _on_toggle, _on_status = on_toggle, on_status
    engine.clear()
    shortcut.reset()
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
