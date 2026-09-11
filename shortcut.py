class ModifierShortcut:
    """Toggle on release of a modifier-only chord; cancel on other input."""

    def __init__(self, required: int, allowed_mask: int):
        self.required = required
        self.allowed_mask = allowed_mask
        self.reset()

    def reset(self):
        self.previous = 0
        self.armed = False
        self.cancelled = False

    def cancel(self):
        if self.previous:
            self.cancelled = True

    def update(self, flags: int) -> bool:
        flags &= self.allowed_mask
        if flags == 0:
            toggle = self.armed and not self.cancelled
            self.reset()
            return toggle
        if flags & ~self.required:
            self.cancelled = True
        if flags == self.required:
            self.armed = True
        self.previous = flags
        return False
