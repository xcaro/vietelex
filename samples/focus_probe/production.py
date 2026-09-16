#!/usr/bin/env python3
"""Observe the production focus service without installing a keyboard hook."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from focus import FocusService, Snapshot, RAW_KINDS, current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=0, help="seconds; 0 runs until Ctrl+C")
    args = parser.parse_args()
    if args.duration < 0:
        parser.error("duration must be nonnegative")
    if sys.platform != "darwin":
        parser.exit(2, "macOS required\n")
    from Cocoa import NSDate, NSRunLoop, NSWorkspace
    from objc import autorelease_pool
    import ApplicationServices as AX

    if not AX.AXIsProcessTrusted():
        parser.exit(2, "Accessibility permission unavailable for this launcher.\n")
    workspace = NSWorkspace.sharedWorkspace()
    service = FocusService()
    service.start()
    epoch = 0
    pid = None
    previous = None
    started = time.monotonic()
    print("Production policy only; no event tap. Logs on attribute changes. Ctrl+C stops.", flush=True)
    try:
        while not args.duration or time.monotonic() - started < args.duration:
            with autorelease_pool():
                NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))
                app = workspace.frontmostApplication()
                active = int(app.processIdentifier()) if app is not None else None
                if active != pid:
                    pid = active
                    epoch += 1
                service.request(pid, epoch)
                sample = service.latest() or Snapshot(epoch=epoch, pid=pid)
                usable = current(sample, epoch, time.monotonic())
                state = asdict(sample)
                state.pop("observed_at")
                state.pop("element")
                state.update(app=str(app.localizedName()) if app is not None else "",
                             fresh=usable, route="RAW" if usable and sample.kind in RAW_KINDS else "LEGACY")
                if state != previous:
                    print(json.dumps(state, ensure_ascii=False), flush=True)
                    previous = state
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()


if __name__ == "__main__":
    main()
