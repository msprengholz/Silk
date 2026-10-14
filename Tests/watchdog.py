"""Stall detection for a long-running test dispatch.

Split out of ``run_all.py`` deliberately, and the split is load-bearing:
**``run_all.py`` cannot be imported inside FreeCAD.** It calls ``main()``
unconditionally (with a comment explaining why -- FreeCAD runs startup
scripts with ``__name__ != "__main__"``, so an ``if``-guard would skip
everything), so importing it from within FreeCAD re-enters the RPC server
from the very GUI thread that is serving it. Measured: SIGSEGV inside
``View3DInventorViewer::aboutToDestroyGLContext``, i.e. the GUI thread dies
partway through the nested dispatch.

So the watchdog lives here: pure standard library, no import-time side
effects, importable from either side. That is what makes it testable at all
-- a test that imported the runner to reach it would crash the process it
is trying to test.

Why it exists: one blocking RPC call lasting minutes gives the client no
signal. Silence is ambiguous -- a slow suite and a wedged FreeCAD look
identical -- and this project waited out both (an O(n^2) probe wedged the
GUI thread for ~4 minutes; a run started by accident ran ~5). CPU time is
the discriminator: a slow-but-alive test burns plenty, a blocked GUI thread
burnes none.
"""

import json
import os
import threading
import time

# ---- the stall watchdog -------------------------------------------------
#
# The RPC call below is ONE blocking request that lasts minutes. Its
# signature behaviour tells you nothing: a slow suite and a wedged FreeCAD
# both look like silence. That ambiguity has cost this project real time --
# an O(n^2) probe wedged the GUI thread for ~4 minutes and a run started by
# mistake ran ~5, and in both cases the reflex was to wait rather than
# diagnose. So the client now watches the server's progress file AND the
# server process's CPU time, which separates the two cases:
#
#   CPU time advancing + progress advancing  -> working, stay quiet
#   CPU time advancing + no new test         -> working inside one test
#   CPU time flat + no new test              -> STALLED, say so NOW
#
# CPU time is the discriminator because a genuine hang (a blocked GUI
# thread waiting on a mutex, a modal dialog, an exception loop) burns no
# CPU, while a slow-but-alive test burns plenty.

PROGRESS_FILE = os.environ.get("SILK_PROGRESS_FILE", "/tmp/silk_progress.json")
STALL_SECONDS = float(os.environ.get("SILK_STALL_SECONDS", "180"))


def _proc_cpu_seconds(pid):
    """utime+stime of `pid` in seconds, or None if unreadable."""
    try:
        with open("/proc/%d/stat" % pid) as fh:
            fields = fh.read().rsplit(") ", 1)[1].split()
        ticks = int(fields[11]) + int(fields[12])
        return ticks / os.sysconf("SC_CLK_TCK")
    except Exception:
        return None


def _read_progress():
    try:
        with open(PROGRESS_FILE) as fh:
            return json.load(fh)
    except Exception:
        return None


class _Watchdog(threading.Thread):
    """Report progress while the blocking RPC call runs, and declare a
    stall -- naming the test -- instead of waiting silently."""

    def __init__(self, stall_seconds=STALL_SECONDS, interval=5.0):
        threading.Thread.__init__(self)
        self.daemon = True
        self.stall_seconds = stall_seconds
        self.interval = interval
        self.stalled = None
        self.phase = "starting"
        self.advance = None          # last time the progress record changed
        self.saw_any = False

    def run(self):
        last_note = 0.0
        while True:
            time.sleep(self.interval)
            rec = _read_progress()
            now = time.time()
            if rec and rec.get("t") != self.advance:
                self.advance = rec.get("t")
                self.saw_any = True
                self.phase = rec.get("name") or rec.get("phase") or "?"
                self.stalled = None
            if rec:
                pid = rec.get("pid")
                cpu = _proc_cpu_seconds(pid) if pid else None
                if cpu is not None and self.advance is not None:
                    idle = now - self.advance
                    # The record advances only between tests, so a long
                    # single test legitimately shows no change. CPU is what
                    # tells the two apart.
                    if idle > self.stall_seconds and cpu == self._last_cpu:
                        self.stalled = (rec.get("name") or rec.get("phase"),
                                        idle, cpu)
                        self._report_stall(rec, idle, cpu)
                        return
                    self._last_cpu = cpu
            if now - last_note > 30.0:
                last_note = now
                cpu = _proc_cpu_seconds(rec["pid"]) if rec and rec.get("pid") else None
                print("[wait] still in: %s (%.0fs, cpu %.1fs)"
                      % (self.phase, now - (self.advance or now),
                         cpu if cpu is not None else -1), flush=True)

    def _report_stall(self, rec, idle, cpu):
        print("", flush=True)
        print("=" * 72, flush=True)
        print("STALLED -- FreeCAD is not making progress", flush=True)
        print("=" * 72, flush=True)
        print("  in test/phase : %s" % (rec.get("name") or rec.get("phase")),
              flush=True)
        print("  position      : %s of %s" % (rec.get("index"), rec.get("total")),
              flush=True)
        print("  no progress   : %.0f s (threshold %.0f s)"
              % (idle, self.stall_seconds), flush=True)
        print("  FreeCAD pid   : %s, CPU %.1f s total -- FLAT, so it is not"
              % (rec.get("pid"), cpu), flush=True)
        print("                   working, it is blocked.", flush=True)
        print("", flush=True)
        print("  This is the case that used to look like 'slow'. It is not:", flush=True)
        print("  the GUI thread is wedged. Restart FreeCAD; do not wait.", flush=True)
        print("=" * 72, flush=True)

    _last_cpu = None
