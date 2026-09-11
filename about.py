"""The original rumps-style About alert, kept above normal windows."""

from Cocoa import NSAlert, NSAppearance, NSUserDefaults, NSFloatingWindowLevel


def show_about():
    # Match rumps.alert's native layout, icon, button and appearance.
    alert = NSAlert.alertWithMessageText_defaultButton_alternateButton_otherButton_informativeTextWithFormat_(
        "VieTelex", "Close", None, None,
        "Simple Telex input for Vietnamese.\n\n"
        "Ctrl+Shift: release both keys to toggle Telex/ABC\n"
        "Reset Buffer: clear current engine state\n"
        "Mouse click into an input resets the buffer\n\n"
        "Rules: aw, ow, uw, aa, ee, oo, dd\n"
        "Tones: s f r x j z",
    )
    window = alert.window()
    if NSUserDefaults.standardUserDefaults().stringForKey_("AppleInterfaceStyle") == "Dark":
        window.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameVibrantDark"))
    alert.setAlertStyle_(0)
    window.setLevel_(NSFloatingWindowLevel)
    window.setHidesOnDeactivate_(False)
    alert.runModal()
