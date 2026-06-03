import sys
import time
import threading
import Quartz

from engine import VietelexEngine

engine    = VietelexEngine()
enabled   = True
injecting = False
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

def send_backspaces(n: int):
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    for _ in range(n):
        Quartz.CGEventPost(Quartz.kCGHIDEventTap,
            Quartz.CGEventCreateKeyboardEvent(src, 51, True))
        Quartz.CGEventPost(Quartz.kCGHIDEventTap,
            Quartz.CGEventCreateKeyboardEvent(src, 51, False))
        time.sleep(0.004)

def send_string(s: str):
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    for ch in s:
        e_dn = Quartz.CGEventCreateKeyboardEvent(src, 0, True)
        e_up = Quartz.CGEventCreateKeyboardEvent(src, 0, False)
        Quartz.CGEventKeyboardSetUnicodeString(e_dn, len(ch), ch)
        Quartz.CGEventKeyboardSetUnicodeString(e_up, len(ch), ch)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, e_dn)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, e_up)
        time.sleep(0.003)

def keyboard_callback(proxy, event_type, event, refcon):
    global injecting

    if injecting:
        return event

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
    if not chars or length == 0:
        return event

    ch = chars[0]

    if ord(ch) > 127 or ord(ch) < 32:
        return event

    if not enabled:
        if ch in (' ', '\t', '\n', '\r'):
            engine.clear()

        return event

    delete_n, insert_str = engine.process(ch)

    if delete_n == 0 and insert_str == ch:
        return event

    injecting = True
    def do_inject():
        global injecting
        try:
            if delete_n > 0:
                send_backspaces(delete_n)
            send_string(insert_str)
        finally:
            injecting = False

    threading.Thread(target=do_inject, daemon=True).start()
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
