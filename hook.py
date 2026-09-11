import sys
import Quartz

from engine import VietelexEngine

engine    = VietelexEngine()
enabled   = True
reset_on_mouse_click = True

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
    if event_type in RESET_EVENT_TYPES:
        if reset_on_mouse_click:
            engine.clear()
        return event

    if event_type != Quartz.kCGEventKeyDown:
        return event

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

def start():
    tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionDefault,
        (Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown) |
         Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseDown) |
         Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseDown) |
         Quartz.CGEventMaskBit(Quartz.kCGEventOtherMouseDown)),
        keyboard_callback,
        None,
    )
    if tap is None:
        print("Could not create CGEventTap.")
        print("Open System Settings -> Privacy & Security -> Accessibility.")
        print("Add Terminal or this app to the list and enable it.")
        print("Restart Terminal or the app, then run again.")
        sys.exit(1)

    src = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)

    Quartz.CFRunLoopAddSource(
        Quartz.CFRunLoopGetMain(), src, Quartz.kCFRunLoopCommonModes)
    Quartz.CGEventTapEnable(tap, True)
    print("CGEventTap enabled. Ready for Vietnamese input.")
