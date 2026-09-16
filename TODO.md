# VieTelex: focus-aware input routing — implementation specification

```yaml
document_type: implementation_handoff
status: implemented_with_native_validation_pending
platform: macOS
language: Python / PyObjC
scope:
  - preserve physical keyboard events in positively identified non-text contexts
  - retain Telex in editable text contexts
  - preserve existing behavior when detection is unavailable or ambiguous
  - cover arbitrary keys; exhaustively exercise WASD combinations
priority: supported_happy_paths
deprioritized: universal browser / custom-editor / game compatibility
current_deliverable: focus routing implementation; see implementation audit below
```

## 0. Requirements and exclusions

### Implementation audit (2026-09-16)

```yaml
implemented:
  - focus.py pure policy, scoped surface evidence, bounded AXReader, serialized worker
  - app lifecycle publication/invalidation and optional-dependency fallback
  - hook route gating for all keys; physical hold/repeat continuity
  - arrival-context metadata in replacement queue
  - per-batch synthetic tags; no stale completion of a newer batch
  - pending physical-event recovery on tap disable / next event after timeout
  - requirements.txt including optional ApplicationServices dependency
  - production-policy diagnostic script (no keyboard hook)
  - bounded transition guard for verified control-context text fields
  - urgent asynchronous AX refresh after potential focus-changing input
  - modeless Keyboard Access panel; explicit Retry/Close; reuse retained window
automated_validation:
  suite: python3 -m unittest discover -s tests -q
  last_result: 105 tests passed
  wasd_sequences: 2920 legal down/up interleavings
  modifier_matrix: 15 nonempty subsets x 16 masks, with interleaved repeats
timing:
  worker_poll_interval_seconds: 0.1
  main_publication_timer_seconds: 0.05
  AX_per_call_timeout_seconds: 0.05
  AX_sample_budget_seconds: 0.25
  maximum_snapshot_age_seconds: 0.5
  replacement_recovery_seconds: 0.5
  transition_guard_max_seconds: 0.5
  text_reconfirmation_min_interval_seconds: 0.08
native_validation:
  local_AX_trusted: false
  production_game_surface_parent_window_relation: verified_by_user_RAW_surface_logs_at_15_03
  latest_transition_guard_gameplay_verification: pending
  keyboard_access_menu_and_terminal_SIGINT: pending_native_validation
  PyInstaller_build: not_run_PyInstaller_not_installed
residual_limits:
  - surface learning is a scoped heuristic; never a blanket AXGroup rule
  - surface without observed text ancestry/window remains legacy
  - async focus publication has a transition race window
  - already_posted_events cannot be retracted
  - late synthetic events after timeout recovery can still affect held keys
  - Unicode keycode_0 insertion remains in text/unknown contexts
  - no native zero-latency or universal game guarantee
```

The checklists below retain the original detailed acceptance plan. Do not infer
that every unchecked native requirement is complete from the automated suite.
Validate production routing with `python3 samples/focus_probe/production.py`:
surface → descendant input → same surface must yield RAW on return. The earlier
`probe.py` showing AXGroup/AXTextField alone does not verify this relationship.

Follow-up regression fix: learning must also work when monitoring starts with
chat already focused. Text ancestry is now queried independently of previous
surface samples; ancestor role, non-writable value/selection, enabled status and
same-window identity are checked before establishing evidence. The end-to-end
AX-reader → snapshot → hook test covers chat-first startup and every ordered pair
of WASD. Actual app diagnostics: `VIETELEX_DEBUG_FOCUS=1 python3 app.py`.

Further user evidence: repeated `TEXT -> RAW/SURFACE` production logs with
`returned_text_container` confirm structural recognition, but movement remained
intermittent. A deterministic test reproduced Enter -> A/W while the latest AX
snapshot was still TEXT, before the next worker publication. The bounded guard
now starts when Enter/keypad Enter/Esc/Tab or a mouse click is delivered in a
verified control-context text field (including delivery from the replacement
queue). It requests an urgent sample; raw/secure evidence ends the guard, while
text requires two distinct post-boundary samples at least 80 ms apart. UNKNOWN
does not extend the 500 ms maximum. Ordinary text fields and steady UNKNOWN do
not arm this guard. This is a scoped freshness policy, not an Enter-based chat
toggle. Tradeoff: very fast typing after a newline inside a supported game chat
may initially pass without Telex until text is reconfirmed. Logs add `transition`.

### Required

- [ ] Keep `VIE` enabled while supported gameplay controls pass through unchanged.
- [ ] Continue normal Vietnamese composition in recognized chat/text fields.
- [ ] Route by actual focus/context; apply to all physical keys, not only `A+W`.
- [ ] Preserve down/up, autorepeat, modifier flags, keycodes, Unicode payload, event order.
- [ ] On missing AX support, stale results, unsupported attributes, or exceptions: use legacy flow.
- [ ] Preserve Terminal/editor usability even if their AX capabilities are incomplete.
- [ ] Keep `ENG`, Ctrl+Shift toggle, reset preferences, retry-access UI, and existing Telex semantics.
- [ ] Keep diagnostics quiet: emit only on meaningful attribute/policy changes.
- [ ] Keep all AX IPC and slow work out of the keyboard callback.
- [ ] Preserve standalone focus sample for manual verification.

### Excluded

- No requirement to switch manually to ENG before playing.
- No new Game Mode menu or Enter/Escape-driven chat state machine.
- No game-name, bundle-ID, or PID allowlist/denylist for routing policy.
- No WASD-specific bypass condition in production code.
- No assumption that held/overlapping keys always mean gameplay; normal typing overlaps too.
- No assumption that every `AXGroup`, `AXWebArea`, window, canvas, or failed query is non-text.
- No requirement to fix Chrome or every custom renderer before shipping supported cases.
- No engine tone-rule rewrite.
- No migration to InputMethodKit in this change.
- No blanket suppression of all externally injected events.
- No global automatic writes to `AXEnhancedUserInterface` in production.
- No keyboard/text-content logging.
- No app restart, build installation, deployment, or commit implied by this document.

## 1. Repository map and starting state

| Path | Current responsibility | Implementation target |
|---|---|---|
| `hook.py` | Global Quartz event tap, replacement injection, pending-event queue | Policy integration and event integrity |
| `engine.py` | Stateful Telex conversion | Preserve rules; use existing `clear()` at boundaries |
| `shortcut.py` | Modifier-only Ctrl+Shift gesture | Preserve cancellation/toggle behavior |
| `app.py` | rumps UI, dependencies, workspace observers, hook lifecycle | Focus-service lifecycle and context invalidation |
| `data.py`, `validator.py` | Character mappings and phonology | Normally unchanged |
| `vietelex.spec` | PyInstaller bundle | Verify new AX dependency inclusion |
| `tests/test_regressions.py` | Fake Quartz, engine/hook/shortcut tests | Extend event-stream model and routing coverage |
| `tests/test_app.py` | Mocked app integration | Focus lifecycle, missing-dependency fallback |
| `samples/focus_probe/probe.py` | Independent AX observer/classifier CLI | Evidence/reference; not production service |
| `samples/focus_probe/cases.html` | HTML inputs, controls, canvas/chat focus fixture | Manual checks |
| `samples/focus_probe/README.md` | Probe usage/limitations | Keep synchronized with sample changes |
| `tests/test_focus_probe.py` | Mock AX/classifier/output tests | Reference; extend only when sample changes |
| `focus.py` | Not present at handoff | Proposed production adapter/service/policy module |
| `TODO.md` | This handoff | Update completed items with evidence |

Starting-state notes:

- Production `hook.py` / `app.py` do not yet contain focus-aware routing.
- A previous Enter-based Game Mode experiment was fully reverted. Do not resurrect it.
- At handoff, `samples/` and `tests/test_focus_probe.py` exist as untracked work. Preserve them.
- Re-run `git status --short` before editing; do not reset unrelated user changes.
- Latest reported sample suite: 29 passing tests. Prior production suite: 15 tests.
- Mock tests do not validate native AX availability or actual game input delivery.

## 2. Defect model

### Current input pipeline

```text
keyboard_callback
  tap-disabled notification -> clear _replacing/_pending -> recovery
  event tag == _EVENT_TAG   -> return generated event
  event tag == _END_TAG     -> finish replacement + drain pending events
  _replacing == True        -> copy physical event into _pending; return None
  otherwise                -> _handle_event

_handle_event
  flagsChanged             -> update Ctrl+Shift shortcut
  mouseDown                -> cancel shortcut; optionally clear buffer
  non-keyDown              -> return event
  keyDown                  -> cancel shortcut
  Cmd/Ctrl/Alt              -> clear engine; return event
  Backspace                -> engine.backspace(); return event
  reset key                -> engine.clear(); return event
  non-single-printable-ASCII -> engine.clear(); return event
  !enabled                 -> return event
  engine.process(ch)
    unchanged              -> return original event
    changed                -> send_replacement(); return None
```

### Confirmed mechanism

```yaml
keycodes:
  A: 0
  S: 1
  D: 2
  W: 13
  Enter: 36
  Backspace: 51
  Escape: 53
  KeypadEnter: 76
replacement:
  output_location: kCGHIDEventTap
  delete: synthetic Backspace down/up
  text: synthetic keycode_0 down/up with Unicode payload
  generated_flags: 0
  completion: _END_TAG on final inserted character keyup
```

Trace reproduced using the repository's fake Quartz harness:

```text
physical A down                    -> delivered; held={A}
physical W down, A still held       -> engine converts aw to ă; W swallowed
generated Backspace down/up         -> delivered
generated keycode 0 down/up ('ă')    -> receiver may treat this as A release
simulated receiver held state      -> {} despite user holding A+W
```

Other demonstrated conversion triggers: `as -> á`, `aa -> â`, `dd -> đ`.

### Why intermittent / after Enter

```text
Enter -> engine.clear()
      -> empty buffer
      -> temp_viet_off=False
next A,W -> valid fresh Telex context -> conversion
subsequent undo sequence (e.g. another W)
      -> aww -> aw
      -> temp_viet_off=True
subsequent letters -> passthrough until reset/end-of-word
invalid phonological buffer -> conversion may also be skipped
```

Evidence level:

- Code and fake-event reproduction confirm swallowing/replacement behavior.
- User reports match Enter/chat followed by movement failure.
- Exact physical/autorepeat sequence in a real game has not been captured.
- Chat is not required for the engine mechanism; Enter is one reset trigger.
- Do not claim every intermittent failure has this single cause.

## 3. Native AX observations from user testing

| App/context | Role/subrole | AXValue writable | Selection writable | Probe result |
|---|---|---:|---:|---|
| Terminal | `AXTextArea` | false | true | UNKNOWN |
| Tested game surface (Sky 2) | `AXGroup` / `iOSContentGroup` | false | false | UNKNOWN |
| Same game's input | `AXTextField` | true | true | TEXT |
| Chrome text input | `AXTextField` | true | true | TEXT |
| Chrome search | `AXTextField` / `AXSearchField` | true | true | TEXT |
| Chrome textarea/contenteditable candidates | `AXTextArea` | true | true | TEXT |
| Chrome password | `AXTextField` / `AXSecureTextField` | not queried | not queried | SECURE |
| Chrome readonly candidate | `AXTextField` | false | true | UNKNOWN |
| Chrome datalist candidate | `AXComboBox` | true | true | TEXT |
| Chrome select | `AXPopUpButton` | true | true | NON_TEXT |
| Chrome button/menu | `AXButton` / `AXMenuItem` | false | false | NON_TEXT |
| Chrome static text | `AXStaticText` | sometimes true | sometimes true | NON_TEXT |
| Chrome canvas fixture | `AXImage` | false | false | NON_TEXT |
| Chrome page background | `AXWebArea` | false | false | UNKNOWN |

Observed transitions:

```text
game:   AXGroup/iOSContentGroup -> AXTextField -> AXGroup/iOSContentGroup
fixture: AXImage -> AXTextField -> AXImage
```

Interpretation constraints:

- Game focus detection was confirmed by the user as matching their actions.
- Game surface currently remains UNKNOWN in the sample; copying its classifier alone will NOT fix this happy case.
- Parent/ancestor/window relationships of the game text field and surface have NOT been measured.
- `AXGroup/iOSContentGroup` is not a universal gameplay classification.
- `value_settable=False` does not prove readonly or absence of typing support.
- Writable `AXSelectedTextRange` alone does not prove editable text.
- Writable `AXValue` alone does not prove text input (sliders/select controls).
- `AXSubrole: no_value` / unsupported optional `AXEnabled` is normal for some controls.
- UNKNOWN during a focus change is an intentionally discarded inconsistent sample.

## 4. Probe learnings; production constraints

### Focus acquisition

- Initial `NSWorkspace.frontmostApplication()` + `time.sleep()` loop could remain on Terminal.
- Cocoa run-loop servicing was added; app changes then appeared correctly.
- System-wide `AXFocusedUIElement` produced repeated `cannot_complete` in user testing.
- Current successful default: frontmost app -> `AXUIElementCreateApplication(pid)` -> app's focused element.
- Keep production app acquisition on the running Cocoa main loop; no nested CLI-style sleep loop in rumps.
- Use `CFEqual` / AX element identity, not Python wrapper `id()`, to compare AX elements.
- Current CLI polls every 250 ms with 1 s timeout per AX call. These are diagnostic settings, not production latency targets.

### Chrome (deprioritized)

- Initially returned `AXFocusedUIElement: no_value`.
- Latest sample reads application `AXRole` once per PID before focus queries.
- Optional `--enable-accessibility` writes `AXEnhancedUserInterface=True` once per PID.
- User subsequently obtained Chrome focus, despite activation returning `not_implemented`.
- Attribution unresolved: root role read, setter side effect, previous browser state, or combination.
- Do not equate a setter error with absence of side effects; do not claim flag causality as proven.
- Chromium source documents delayed enhanced activation; repeated requests may postpone it.
- Do not block the core fix on isolating Chrome behavior or force activation by default.

### Logging

- Default: first sample + attribute/policy changes only.
- No heartbeat.
- Do not emit just because temporary `focus_id`, timestamp, or sample duration changed.
- Internal focus identity/context generation must still update even when logging is suppressed.
- `--all` is sample-only verbose debug behavior; not production default.

## 5. Routing contract

Separate raw AX classification from effective routing policy.

```python
class FocusKind(Enum):
    TEXT = ...
    SECURE = ...
    NON_TEXT_CONTROL = ...
    CONFIRMED_CONTROL_SURFACE = ...
    UNKNOWN = ...

class Route(Enum):
    LEGACY = ...          # existing handler, including enabled=False behavior
    RAW = ...             # preserve physical event; no engine/replacement work
```

| Snapshot | Effective route | Required behavior |
|---|---|---|
| `enabled=False` | RAW / existing ENG semantics | Never compose |
| Fresh TEXT | LEGACY | Existing Telex behavior |
| Fresh SECURE | RAW | No Telex injection |
| Fresh NON_TEXT_CONTROL | RAW | Preserve events |
| Fresh CONFIRMED_CONTROL_SURFACE | RAW | Preserve events, all keys |
| UNKNOWN | LEGACY | Compatibility fallback |
| No snapshot / unavailable service | LEGACY | Compatibility fallback |
| Expired snapshot | LEGACY | No stale bypass |
| Snapshot belongs to previous app/context | LEGACY | Invalidate immediately |
| Query error or classification exception | LEGACY | No crash, no stale success |

Priority rules:

1. Synthetic-event tagging/completion protocol is separate from physical-event routing.
2. Explicit ENG disables new composition regardless of focus result.
3. Current secure-field evidence overrides general text heuristics.
4. Positive control-role evidence overrides generic writable-value heuristics.
5. Uncertain text/editability stays UNKNOWN, not RAW.
6. Existing physical gesture continuity may retain RAW until release; it must not start a new conversion mid-hold.
7. UNKNOWN fallback may still exhibit the original bug; report this scope honestly.

## 6. Supported surface recognition — evidence gate

### Problem

```text
Observed game surface = AXGroup/iOSContentGroup = currently UNKNOWN
UNKNOWN -> LEGACY by requirement
Therefore: generic group handling must be resolved before claiming game fix complete.
```

### Investigation/implementation tasks

- [ ] Extend sample metadata collection only as needed to inspect `AXParent` / `AXWindow` identity.
- [ ] Bound ancestry traversal (proposed max 8 ancestors, visited-element cycle check, per-sample time budget).
- [ ] Read metadata/identity only; no `AXValue`, `AXSelectedText`, window titles, screenshots, or arbitrary tree dumps.
- [ ] Capture the actual relation between focused game input and returned control surface.
- [ ] Verify transitions opened/closed with mouse as well as keyboard; do not use Enter as a state signal.
- [ ] Verify app/window switches and another unrelated group cannot inherit bypass state.
- [ ] Prefer generic control-role evidence when already sufficient (`AXImage` canvas fixture, explicit control).
- [ ] For opaque groups, implement a narrowly evidenced structural/transition rule only after validating the relation.

Candidate learning model, NOT yet validated:

```text
scope = app process instance + workspace/session epoch + window AX identity
observe supported control surface identity S
observe positively identified text descendant T with bounded ancestor chain containing S
observe actual focus return to the same S
verify S still exposes non-editable surface metadata
=> candidate CONFIRMED_CONTROL_SURFACE for this exact scoped identity
```

Mandatory caveats:

- Ancestor relationship alone is not proof of gameplay; editors also contain text descendants.
- Require negative/counterexample checks against ordinary editors, terminal containers, and contenteditable wrappers.
- A learned route must not be persisted across processes, windows, app activation epochs, or restarts.
- Invalid elements, incomplete ancestry, conflicting capabilities, or ambiguous evidence -> UNKNOWN.
- Do not classify all `iOSContentGroup` elements RAW solely to make the game example pass.
- If reliable generic evidence cannot be established, keep fallback and explicitly mark this happy case unresolved.
- No game allowlist, manual Game Mode, or silent UNKNOWN->RAW substitution as a shortcut.

## 7. Focus service design

### Proposed module/API

```python
@dataclass(frozen=True)
class FocusSnapshot:
    context_epoch: int
    process_token: object | None  # include process-instance/activation identity, not PID alone
    pid: int | None
    window_token: object | None
    element_token: object | None
    observed_at: float            # monotonic; conservative acquisition timestamp
    kind: FocusKind
    reason: str
    role: str | None
    subrole: str | None
    value_settable: bool | None
    selection_settable: bool | None
    errors: tuple

class FocusService:
    def start(self, publish): ...
    def invalidate(self, context_epoch): ...
    def request_refresh(self): ...  # non-blocking/coalesced
    def stop(self): ...

def route(snapshot, current_epoch, now, enabled) -> Route: ...
```

API names are illustrative; preserve invariants rather than exact naming.

### Scheduling and ownership

- [ ] Main Cocoa loop owns current app/context epoch and publication into hook state.
- [ ] AX reads run on one serialized worker or another demonstrably non-blocking design.
- [ ] No blocking AX reads in event callback OR on the main loop hosting the event tap.
- [ ] Do not copy sample's 1 s AX calls into a rumps timer callback on the tap thread.
- [ ] Optional AX observers: actual focus/window changes request refresh; unsupported observer registration falls back to polling.
- [ ] Keep at most one acquisition in flight; coalesce refresh requests.
- [ ] Bound polling, per-call timeout, total sample work, ancestry depth, and pending work.
- [ ] Suggested starting values to measure, not platform guarantees: poll 50–100 ms, snapshot max age 250 ms, per-call budget 50–100 ms.
- [ ] Publish UNKNOWN if collection exceeds freshness budget; do not stamp slow data fresh at completion.
- [ ] Reject results whose captured context epoch no longer matches current epoch.
- [ ] Worker never mutates engine, shortcut, hook queue, or menu objects.
- [ ] Use immutable snapshots + main-thread publication; no callback waiting on a worker-held mutex.
- [ ] Stop/restart does not leak worker threads, timers, AX observers, run-loop sources, or retained elements.
- [ ] Use autorelease pools for worker/native polling allocations.

### Error handling

| Condition | Action |
|---|---|
| No Accessibility trust | Disable focus enrichment; legacy routing; keep keyboard tap status independent |
| `no_value` for focused element | UNKNOWN; allow later samples |
| `cannot_complete` | UNKNOWN; bounded retry on future poll; no busy retry loop |
| Invalid AX element | Invalidate element/window evidence; reacquire later |
| Unsupported optional attribute | Record missing evidence; do not automatically fail whole sample |
| Unsupported role/focus API | UNKNOWN |
| Focus changes during sample | Discard inconsistent success |
| App changes during sample | Reject by epoch/PID/window checks |
| PyObjC exception | Catch at AX boundary, publish UNKNOWN with diagnostic; do not swallow arbitrary programming errors silently |
| App terminates | Invalidate all scoped evidence |

## 8. Hook integration and state transitions

### Integration points

- [ ] Inject/read an in-memory routing provider; hook tests must not import native AX.
- [ ] Gate before Unicode conversion, `engine.process()`, and `send_replacement()`.
- [ ] Also account for `keyboard_callback` queuing, which currently happens before `_handle_event`.
- [ ] Preserve modifier-only shortcut processing even while bypassing Telex.
- [ ] Physical input still cancels a pending Ctrl+Shift toggle gesture.
- [ ] Context-boundary engine clearing is independent of `reset_on_mouse_click` preference.
- [ ] Existing mouse reset preference continues to govern ordinary same-context clicks.
- [ ] Preserve reset keys, backspace, command shortcuts, and non-ASCII handling in LEGACY.
- [ ] Keep user-visible VIE/ENG preference distinct from temporary focus routing.

### Composition invalidation

Clear composition when:

- entering or leaving a positively identified raw context;
- switching positively identified text fields, including identical role/capability fields;
- active app/window/session changes;
- current context is invalidated after having had reliable evidence;
- explicit existing Reset Buffer/toggle operation requires it.

Do NOT:

- clear on every poll of the same UNKNOWN state;
- clear on every event merely because AX is unavailable;
- clear repeatedly in Terminal and thereby disable all Telex composition under fallback;
- couple buffer reset to diagnostic logging suppression;
- reset shortcut state on every focus sample, breaking Ctrl+Shift release detection.

### Physical key continuity

Consider a small gesture ledger if required by transition tests:

```text
keycode -> physical-down state + initial route + context epoch
```

- [ ] Track only untagged physical events; synthetic Unicode A/Backspace events must not affect ledger.
- [ ] Repeats do not create new key presses.
- [ ] A key pressed under RAW stays RAW for repeats/release through a focus transition.
- [ ] Transition RAW->TEXT must not treat a held movement key's repeat as fresh chat text.
- [ ] Transition TEXT->RAW must not start further composition from repeats.
- [ ] Never invent movement down/up events to compensate for presumed loss.
- [ ] Orphan keyups pass through; do not require a previously observed down to forward them.
- [ ] Recover from missing releases on tap/session interruption without leaving permanent raw/composition lockout.
- [ ] Unknown-context new presses follow fallback; a gesture latch is not a permanent app mode.

### Freshness limitation

Focus is asynchronous. Even a recent snapshot can become stale immediately after sampling.

- Use notifications/epoch invalidation to reduce the interval.
- Do not synchronously wait for AX in the tap to eliminate the interval.
- Do not claim zero race window from a polling-only design.
- Test immediate chat-close + movement at multiple offsets relative to publication.
- Document observed supported latency and remaining UNKNOWN/transition gaps.

## 9. Replacement queue and in-flight events

### Existing hazards to audit

```text
_pending stores only (event_type, copied_event)
  => replay currently has no arrival-context metadata
_replacing waits for _END_TAG
  => missing completion can strand all physical events
tap-disabled handler clears _pending
  => queued physical transitions may be lost
generated Unicode uses keycode 0
  => synthetic A keyup can affect a held physical A
```

These are audit findings; missing completion/tap-disable loss has not been confirmed
as the user's real-game root cause.

### Required transition behavior

- [ ] Preserve existing replacement ordering for stable TEXT and LEGACY contexts.
- [ ] Do not reprocess an event captured in a known raw surface as Telex because focus changed before dequeue.
- [ ] Do not apply queued old text composition against a new field/surface/app.
- [ ] Associate queued events with arrival epoch/route when needed.
- [ ] On epoch mismatch, invalidate composition; avoid generating replacements for stale queued events.
- [ ] Do not drop physical keyup or clear all queued events as the transition solution.
- [ ] Do not let a new raw keyup overtake its already-queued keydown.
- [ ] Do not bypass the queue indiscriminately: movement A down must not be followed by a prior replacement's synthetic A up.
- [ ] `_END_TAG` must complete the correct replacement batch; stale completion must not complete a newer batch.
- [ ] Tagged events must never re-enter Telex or physical key tracking.
- [ ] Keep physical event forwarding ordered and exactly once during deferred replay.
- [ ] Consider a bounded completion recovery only if queue failure tests expose a new/required gap; test late tags and duplicate forwarding.

### External delivery boundary

`CGEventPost()` has already submitted events to macOS. Clearing Python state cannot
retract those events, and replaying a captured event through a tap proxy may target
the currently active UI rather than its original recipient.

- Define what can still be cancelled before posting versus only drained afterward.
- Do not claim previously submitted text can always be cancelled on app switch.
- Test observable physical-event ordering under injected old-batch completion.
- If full in-flight transition guarantees cannot be achieved without changing injection,
  document that limitation separately from stable-context passthrough success.
- Do not silently weaken the stable RAW event-integrity guarantee.

### Synthetic keycode collision: separate issue

- Focus gating prevents initiating replacements in recognized raw contexts.
- It does not remove keycode-0 injection in legitimate text/fallback contexts.
- Do not substitute an arbitrary unused keycode and declare the collision solved.
- Any insertion-transport change needs native macOS/editor/game verification plus existing HID tests.
- If deferred, list residual collision risk for unidentified contexts and already-posted replacements.

## 10. Test harness requirements

- [ ] Extend fake Quartz with correct per-field access, especially `kCGKeyboardEventAutorepeat`.
- [ ] Existing fake getter treats every non-user-data field as keycode; fix before testing repeats.
- [ ] Use real WASD keycodes; existing `HookTests.key()` defaults every character to code 0 and is insufficient.
- [ ] Capture both returned events and `CGEventTapPostEvent` deliveries in one ordered trace.
- [ ] Capture `CGEventPost` injections separately and pump tagged events deterministically.
- [ ] Model held keys from down/up; repeats retain held state rather than adding presses.
- [ ] Inject focus snapshots/epoch changes/fake monotonic time without live AX or sleeps.
- [ ] Preserve existing simulated-text assertions for Telex regressions.
- [ ] Assert no AX calls occur from keyboard callbacks using a failing stub/spying adapter.
- [ ] Distinguish pass-through original events from copied/replayed events while asserting preserved fields.

Oracle for a stable, recognized raw context with no prior replacement in flight:

```python
assert physical_output_trace == physical_input_trace  # normalized full fields + order
assert generated_hid_events == []
assert engine_process_call_count == 0
assert receiver_held_keys == expected_physical_held_keys  # after EACH event
assert replacement_pending is False
```

Queue transition tests need a separate oracle accounting for already-posted old-batch events;
do not require their nonexistence retroactively.

## 11. Exhaustive WASD matrix

### Key sets: all 15 nonempty subsets

```text
size 1: W A S D
size 2: WA WS WD AS AD SD
size 3: WAS WAD WSD ASD
size 4: WASD
```

Production routing is key-agnostic; this enumeration is for tests only.

### Ordering coverage

- [ ] For each subset: all down-order permutations × all up-order permutations.
- [ ] Counts: 4 + 24 + 144 + 576 = 748 basic all-down-then-all-up sequences.
- [ ] Also enumerate all legal interleavings with exactly one down and up per selected key,
  enforcing each key's down precedes its up.
- [ ] Counts by size: 4×1 + 6×6 + 4×90 + 1×2520 = 2920 sequences total.
- [ ] Legal-interleaving suite includes all-down-then-all-up cases; avoid redundant large suites if unnecessary.
- [ ] Verify held-state equality after every event, not merely final empty state.
- [ ] Include opposed directions (W+S, A+D); preserving input is required even if game movement cancels.
- [ ] Include release/repress cycles while other keys remain held.

Suggested generator:

```python
def legal_events(unpressed, held):
    if not unpressed and not held:
        yield []
    for key in sorted(unpressed):
        for suffix in legal_events(unpressed - {key}, held | {key}):
            yield [(DOWN, key)] + suffix
    for key in sorted(held):
        for suffix in legal_events(unpressed, held - {key}):
            yield [(UP, key)] + suffix
```

### Repeats / modifiers / sequences

- [ ] Every single key held with autorepeat down events before release.
- [ ] Repeats for each held key in 2/3/4-key chords.
- [ ] Interleave repeats with another key's down/up; release/repress an existing key.
- [ ] Sequential Telex triggers: `aw`, `as`, `aa`, `dd`, `aww`, `ass`, `aaa`.
- [ ] Mixed movement sequences: `wasd`, `asdw`, reverse order, repeated rounds.
- [ ] Each subset under none/Shift/Ctrl/Alt/Cmd and representative combined masks.
- [ ] Modifier changes while movement keys remain held; preserve flag payloads.
- [ ] Ctrl+Shift plus movement cancels toggle; bare Ctrl+Shift release still toggles once.
- [ ] Uppercase character payloads, autorepeat flags, empty Unicode payloads, non-US-layout payloads.
- [ ] Representative non-WASD keys: Space, arrows, Enter, keypad Enter, Escape, Backspace, Q/E/R/F, digits.
- [ ] RAW handling must not depend on ASCII text extraction.

## 12. Context and queue regression matrix

| Scenario | Assertions |
|---|---|
| TEXT -> recognized surface -> every WASD subset | Physical trace intact; no new replacement |
| Surface -> TEXT | Fresh Telex composition works |
| Enter in TEXT without actual focus change | Remains text route; no inferred gameplay mode |
| Mouse opens/closes text input | Same routing as actual focus changes via keyboard |
| Esc does not change focus | No inferred chat-state change |
| Two text fields with same attributes | Buffer reset by identity; logs may remain silent |
| RAW key held across TEXT transition | Repeat/up remain raw for that gesture |
| TEXT key held across RAW transition | No new composition from later repeat events |
| UNKNOWN remains UNKNOWN across polls | Existing Telex composes normally; no repeated resets |
| RAW snapshot becomes stale | New gestures use fallback; no indefinite stale bypass |
| AX exception in TEXT/RAW acquisition | UNKNOWN published; keyboard handler survives |
| Delayed worker result after app switch | Rejected by epoch |
| App/window/session switch | Invalidate scoped surface evidence and composition |
| ENG in any focus state | No new composition |
| Replacement pending + Enter + surface focus + movement | Ordered delivery; no stale-event recomposition |
| Pending down then raw up | No reordering or dropped keyup |
| Old end tag after invalidation/new batch | Cannot finish wrong batch |
| Missing completion | No silent permanent event loss; scoped recovery/limitation documented |
| Tap disabled during queued input | Recovery and physical state behavior explicitly tested |
| Mouse reset preference off | Context changes still reset, same-context preference preserved |
| Focus service absent/fails startup | Existing app/hook continues functioning |
| Secure text field | No new text substitution |
| Browser unsupported | Fallback, no production dependency on enhanced AX |

## 13. App lifecycle / dependencies / packaging

- [ ] Add `ApplicationServices` support with an optional-service boundary.
- [ ] Existing Cocoa/Quartz/rumps dependency behavior remains intact.
- [ ] Missing AX dependency must not prevent legacy typing or crash module import.
- [ ] If adding auto-install dependency handling, follow existing source/frozen distinctions; no runtime install in frozen bundle.
- [ ] Verify imports and PyInstaller collection; update `vietelex.spec` only if required.
- [ ] Start focus service once; retries must not duplicate observers/workers.
- [ ] Existing workspace notifications invalidate focus cache as well as engine/shortcut context.
- [ ] Handle session resign/resume and application termination.
- [ ] Stop focus service before quitting; do not leave callbacks mutating torn-down hook state.
- [ ] Report keyboard access failure separately from optional focus-service availability.
- [ ] No additional toggle or persistent game preference required.

## 14. Implementation sequence

1. [ ] Record clean baseline tests and current diff; preserve sample work.
2. [ ] Extend sample only enough to validate supported opaque-surface evidence (§6).
3. [ ] Implement pure classification/routing functions and evidence-state tests.
4. [ ] Implement AX adapter + bounded service + stale/epoch invalidation tests.
5. [ ] Implement physical event trace harness and WASD matrix.
6. [ ] Integrate routing into hook with no AX IPC in callback.
7. [ ] Resolve gesture continuity and replacement queue transitions using deterministic tests.
8. [ ] Integrate app lifecycle/dependency fallback.
9. [ ] Run full regression suite once after changes; investigate actual failures.
10. [ ] Perform native smoke tests on supported game + ordinary text editor + Terminal fallback.
11. [ ] Document supported behavior, measured limitations, and deferred injection issues.

## 15. Verification commands

```sh
git status --short
python3 -m unittest discover -s tests -v
python3 samples/focus_probe/probe.py
python3 samples/focus_probe/probe.py --duration 60 --json
git diff --check
```

Optional diagnostic only:

```sh
python3 samples/focus_probe/probe.py --enable-accessibility
python3 samples/focus_probe/probe.py --source system
```

Native verification protocol:

- [ ] Keep VIE enabled.
- [ ] Open supported game's chat; type `tieengs Vieetj` -> expected Vietnamese.
- [ ] Close chat through actual UI; exercise singles, pairs, triples, all four keys, holds, modifiers.
- [ ] Repeat opening/closing via mouse and keyboard where supported.
- [ ] Repeat immediately after chat close and after short delays; record timing limitation if any.
- [ ] Return to chat and verify composition still works.
- [ ] Switch to ordinary editor and Terminal; verify fallback preserves typing.
- [ ] Repeat with missing/unsupported focus metadata via test double or unsupported app.
- [ ] Stop probe while testing production integration to avoid confusing diagnostic AX activation with production behavior.
- [ ] Browser activation state may persist in app process; restart browser for isolated activation experiments only if needed.

## 16. Completion criteria

- [ ] Supported raw-context routing protects all keys; no WASD allowlist in implementation.
- [ ] Exhaustive WASD held-set/order tests and targeted modifier/repeat tests pass.
- [ ] Text Telex, tone correction, undo, rapid typing, mouse/backspace ordering tests remain passing.
- [ ] Positive game surface/input transition has actual evidence beyond raw `AXGroup` role.
- [ ] Unsupported/ambiguous contexts use legacy behavior without repeated composition reset.
- [ ] Event callback contains no synchronous AX calls, sleeps introduced by focus detection, or worker waits.
- [ ] Old async focus results cannot affect new app/window/session context.
- [ ] Known queued-event ordering/gesture transition cases are covered; unresolved OS delivery limits stated explicitly.
- [ ] Default logs emit only meaningful changes and contain no typed text.
- [ ] No forced Chrome compatibility work or global enhanced-AX activation.
- [ ] Production integration is distinct from sample; prototype passing alone is not completion.
- [ ] Final report separates: automated evidence, native user verification, unverified behavior, deferred risks.

## 17. Reference APIs / sources

- [AXUIElementCopyAttributeValue](https://developer.apple.com/documentation/applicationservices/1462085-axuielementcopyattributevalue)
- [AXUIElementIsAttributeSettable](https://developer.apple.com/documentation/applicationservices/axuielementisattributesettable(_:_:_:))
- [AXUIElementSetMessagingTimeout](https://developer.apple.com/documentation/applicationservices/1459345-axuielementsetmessagingtimeout)
- [NSRunningApplication run-loop/cache semantics](https://developer.apple.com/documentation/appkit/nsrunningapplication)
- [AX roles](https://developer.apple.com/documentation/applicationservices/carbon_accessibility/roles)
- [Secure text field subrole](https://developer.apple.com/documentation/applicationservices/kaxsecuretextfieldsubrole)
- [PyObjC ApplicationServices](https://pyobjc.readthedocs.io/en/latest/apinotes/ApplicationServices.html)
- [Chromium AX role activation / enhanced activation delay](https://chromium.googlesource.com/chromium/src/+/master/chrome/browser/chrome_browser_application_mac.mm)

Use current API documentation/local PyObjC signatures when implementing. Samples and
mock tests are implementation aids, not evidence of universal platform behavior.
