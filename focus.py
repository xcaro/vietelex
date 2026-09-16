"""Optional focus enrichment. AX IPC belongs to the worker, never the event tap."""

from dataclasses import dataclass
from enum import Enum
import logging
import threading
import time


log = logging.getLogger(__name__)
MAX_AGE = 0.5
POLL_INTERVAL = 0.1
QUERY_TIMEOUT = 0.05
QUERY_BUDGET = 0.25
TEXT_ROLES = frozenset({"AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"})
CONTROL_ROLES = frozenset({
    "AXButton", "AXCheckBox", "AXRadioButton", "AXPopUpButton", "AXSlider",
    "AXMenu", "AXMenuItem", "AXMenuBarItem", "AXLink", "AXStaticText",
    "AXTabGroup", "AXToolbar", "AXImage",
})


class Kind(str, Enum):
    TEXT = "text"
    SECURE = "secure"
    CONTROL = "control"
    SURFACE = "surface"
    UNKNOWN = "unknown"


RAW_KINDS = frozenset({Kind.SECURE, Kind.CONTROL, Kind.SURFACE})


@dataclass(frozen=True)
class Snapshot:
    epoch: int = 0
    pid: int | None = None
    observed_at: float = 0.0
    window: int | None = None
    element: int | None = None
    kind: Kind = Kind.UNKNOWN
    reason: str = "unavailable"
    control_context: bool = False  # text has a verified non-editable surface ancestor


def current(snapshot, epoch, now):
    return (snapshot.epoch == epoch and snapshot.kind != Kind.UNKNOWN
            and 0 <= now - snapshot.observed_at <= MAX_AGE)


def classify(role, subrole=None, enabled=None, writable=None, selection=None):
    if role == "AXSecureTextField" or subrole == "AXSecureTextField":
        return Kind.SECURE
    if enabled is False or role in CONTROL_ROLES:
        return Kind.CONTROL
    if role in TEXT_ROLES:
        return Kind.TEXT if writable is True else Kind.UNKNOWN
    # Value or selection on its own is not evidence of editable text.
    if role and writable is True and selection is True:
        return Kind.TEXT
    return Kind.UNKNOWN


class SurfaceEvidence:
    """Learn an iOS content surface from a verified text descendant.

    A generic AXGroup never qualifies. This is a scoped structural heuristic,
    not a claim that all iOSContentGroup elements are gameplay.
    """

    def __init__(self):
        self.scope = None
        self.seen = set()
        self.with_text = set()

    def observe(self, scope, element, kind, candidate, ancestors=()):
        if scope != self.scope:
            self.scope = scope
            self.seen.clear()
            self.with_text.clear()
        if scope[-1] is None:
            return kind
        if len(self.seen) >= 128 and element not in self.seen:
            self.seen.clear()
            self.with_text.clear()
        if kind == Kind.TEXT:
            # Ancestors have their own role/capability/window checks. They can
            # establish evidence even if polling started with chat already open.
            self.seen.update(ancestors)
            self.with_text.update(ancestors)
        if candidate:
            self.seen.add(element)
            if element in self.with_text:
                return Kind.SURFACE
        return kind


class QueryFailed(Exception):
    pass


class AXReader:
    """Construct/use on one worker; retain a bounded set of AX identities."""

    def __init__(self):
        import ApplicationServices as AX
        from CoreFoundation import CFEqual
        self.ax = AX
        self.equal = CFEqual
        self.scope = None
        self.identities = []
        self.serial = 0
        self.surfaces = SurfaceEvidence()

    def token(self, element):
        for previous, token in self.identities:
            if self.equal(previous, element):
                return token
        self.serial += 1
        self.identities.append((element, self.serial))
        if len(self.identities) > 128:
            self.identities.pop(0)
        return self.serial

    def check_budget(self):
        if time.monotonic() - self.started > QUERY_BUDGET:
            raise QueryFailed("budget_exceeded")

    def prepare(self, element):
        self.check_budget()
        if self.ax.AXUIElementSetMessagingTimeout(element, QUERY_TIMEOUT):
            raise QueryFailed("timeout_configuration_failed")

    def read(self, element, attribute, required=False):
        self.check_budget()
        status, value = self.ax.AXUIElementCopyAttributeValue(element, attribute, None)
        if status:
            if not required and status in (-25205, -25208, -25212):
                return None
            raise QueryFailed(f"{attribute}:{int(status)}")
        if required and value is None:
            raise QueryFailed(f"{attribute}:no_value")
        return value

    def settable(self, element, attribute):
        self.check_budget()
        status, value = self.ax.AXUIElementIsAttributeSettable(element, attribute, None)
        if status:
            if status in (-25205, -25208, -25212):
                return None
            raise QueryFailed(f"{attribute}:{int(status)}")
        return bool(value)

    def ancestors(self, element, window):
        """Bounded metadata-only ancestry; never enumerate arbitrary children."""
        if window is None:
            return ()
        result = []
        visited = [element]
        for _ in range(8):
            parent = self.read(element, "AXParent")
            if parent is None:
                return tuple(result)
            if any(self.equal(parent, old) for old in visited):
                return ()
            visited.append(parent)
            self.prepare(parent)
            role = self.read(parent, "AXRole", required=True)
            if role in ("AXWindow", "AXApplication"):
                return tuple(result)
            subrole = self.read(parent, "AXSubrole")
            if role == "AXGroup" and subrole == "iOSContentGroup":
                parent_window = self.read(parent, "AXWindow")
                enabled = self.read(parent, "AXEnabled")
                writable = self.settable(parent, "AXValue")
                selection = self.settable(parent, "AXSelectedTextRange")
                if (parent_window is not None and self.equal(parent_window, window)
                        and (enabled is None or bool(enabled))
                        and writable is False and selection is False):
                    result.append(self.token(parent))
            element = parent
        return ()  # Incomplete traversal is not evidence.

    def sample(self, pid, epoch):
        self.started = time.monotonic()
        if (pid, epoch) != self.scope:
            self.scope = (pid, epoch)
            self.identities.clear()
            self.surfaces = SurfaceEvidence()
        base = dict(epoch=epoch, pid=pid, observed_at=self.started)
        try:
            if not self.ax.AXIsProcessTrusted():
                raise QueryFailed("permission_unavailable")
            app = self.ax.AXUIElementCreateApplication(pid)
            self.prepare(app)
            self.read(app, "AXRole")  # Can initialize basic AX support.
            element = self.read(app, "AXFocusedUIElement", required=True)
            self.prepare(element)
            status, owner = self.ax.AXUIElementGetPid(element, None)
            if status or int(owner) != pid:
                raise QueryFailed("wrong_owner")
            role = self.read(element, "AXRole", required=True)
            subrole = self.read(element, "AXSubrole")
            enabled = writable = selection = None
            if role != "AXSecureTextField" and subrole != "AXSecureTextField":
                value = self.read(element, "AXEnabled")
                enabled = bool(value) if value is not None else None
                writable = self.settable(element, "AXValue")
                selection = self.settable(element, "AXSelectedTextRange")
            kind = classify(role, subrole, enabled, writable, selection)
            window = self.read(element, "AXWindow")
            window_id = self.token(window) if window is not None else None
            element_id = self.token(element)
            candidate = (kind == Kind.UNKNOWN and role == "AXGroup"
                         and subrole == "iOSContentGroup" and writable is False
                         and selection is False and enabled is not False)
            parents = ()
            if kind == Kind.TEXT:
                # An unavailable ancestry query must not break ordinary typing.
                try:
                    parents = self.ancestors(element, window)
                except QueryFailed:
                    parents = ()
            latest = self.read(app, "AXFocusedUIElement", required=True)
            if not self.equal(element, latest):
                raise QueryFailed("focus_changed")
            latest_window = self.read(element, "AXWindow")
            if ((window is None) != (latest_window is None)
                    or (window is not None and not self.equal(window, latest_window))):
                raise QueryFailed("window_changed")
            self.check_budget()
            kind = self.surfaces.observe((epoch, pid, window_id), element_id,
                                         kind, candidate, parents)
            reason = f"{role}/{subrole or ''}"
            if candidate:
                reason += (":returned_text_container" if kind == Kind.SURFACE else
                           ":window_unavailable" if window_id is None else
                           ":text_ancestry_unconfirmed")
            return Snapshot(**base, window=window_id, element=element_id,
                            kind=kind, reason=reason,
                            control_context=bool(parents) or kind == Kind.SURFACE)
        except QueryFailed as error:
            return Snapshot(**base, reason=str(error))


class FocusService:
    """One worker, one coalesced target, immutable latest-result handoff.

    Main-thread app timers call request/latest. Hook callbacks use only their
    already-published Snapshot and never touch this service or its condition.
    """

    def __init__(self, reader_factory=AXReader):
        self.reader_factory = reader_factory
        self._condition = threading.Condition()
        self._target = None
        self._latest = None
        self._stopped = False
        self._thread = None
        self._urgent = False

    def start(self):
        if not self._stopped and (self._thread is None or not self._thread.is_alive()):
            self._thread = threading.Thread(target=self._run, name="vietelex-focus", daemon=True)
            self._thread.start()

    def request(self, pid, epoch):
        with self._condition:
            target = (pid, epoch) if pid is not None else None
            if target != self._target:
                self._target = target
                self._latest = None
                self._condition.notify()

    def latest(self):
        with self._condition:
            return self._latest

    def refresh(self):
        with self._condition:
            if self._target is not None and not self._stopped:
                self._urgent = True
                self._condition.notify()

    def stop(self):
        with self._condition:
            self._stopped = True
            self._target = None
            self._latest = None
            self._condition.notify()
        # No main-thread join: a slow native IPC must not delay shutdown.

    def _run(self):
        try:
            from objc import autorelease_pool
            reader = self.reader_factory()
        except ImportError:
            log.warning("Focus enrichment unavailable; install pyobjc-framework-ApplicationServices. "
                        "Using legacy input.")
            return
        except Exception as error:
            log.warning("Focus initialization failed (%s); using legacy input", type(error).__name__)
            return
        previous_error = None
        while True:
            with self._condition:
                while self._target is None and not self._stopped:
                    self._condition.wait()
                if self._stopped:
                    return
                target = self._target
                self._urgent = False
            try:
                with autorelease_pool():
                    result = reader.sample(*target)
                previous_error = None
            except Exception as error:
                # Optional AX service cannot take down keyboard input. Report
                # exception types only; native exception text may contain UI data.
                name = type(error).__name__
                if name != previous_error:
                    log.warning("Focus reader failed (%s); using legacy input", name)
                previous_error = name
                result = Snapshot(epoch=target[1], pid=target[0], reason="reader_exception")
            with self._condition:
                if self._stopped:
                    return
                if target == self._target:
                    self._latest = result
                    if not self._urgent:
                        self._condition.wait(POLL_INTERVAL)
