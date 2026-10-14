"""Ending a long test dispatch: stall detection and a bounded wait.

Split out of ``run_all.py`` deliberately, and the split is load-bearing:
**``run_all.py`` cannot be imported inside FreeCAD.** It calls ``main()``
unconditionally (with a comment explaining why -- FreeCAD runs startup
scripts with ``__name__ != "__main__"``, so an ``if``-guard would skip
everything), so importing it from within FreeCAD re-enters the RPC server
from the very GUI thread that is serving it. Measured: SIGSEGV inside
``View3DInventorViewer::aboutToDestroyGLContext``, i.e. the GUI thread dies
partway through the nested dispatch.

So this module lives here: pure standard library, no import-time side
effects, importable from either side. That is what makes it testable at all
-- a test that imported the runner to reach it would crash the process it
is trying to test.

Why it exists: one blocking RPC call lasting minutes gives the client no
signal. Silence is ambiguous -- a slow suite and a wedged FreeCAD look
identical -- and this project waited out both (an O(n^2) probe wedged the
GUI thread for ~4 minutes; a run started by accident ran ~5). CPU time is
the discriminator: a slow-but-alive test burns plenty, a blocked GUI thread
burnes none.

Detecting that was never enough, though: the watchdog only SET
``self.stalled`` while ``proxy.execute_code`` blocked on the same thread
that would have to read it -- so the detector was effectively dead code
during the wait, and the worst case was a 30-minute silent hang the human
had to abort by hand. This module therefore owns the whole mechanism:

* ``_Watchdog`` -- decides slow-vs-wedged (progress file + CPU);
* ``wait_for_call`` -- runs the call on a daemon worker thread and waits
  BOUNDED, so a declared stall *ends* the wait and a generous wall-clock
  ceiling backstops everything else;
* ``report_timeout`` -- says what the suite was doing when the ceiling hit.

``run_all.py`` stays a thin consumer of these three.
"""

import json
import os
import threading
import time
from collections import namedtuple

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

# How often the watchdog thread samples the progress file + CPU (seconds).
# Injectable because a test that proves "the stall ENDS the run" would
# otherwise wait two 5s ticks before it can even declare one.
WATCHDOG_INTERVAL_SECONDS = float(os.environ.get("SILK_WATCHDOG_INTERVAL", "5.0"))

# The wall-clock backstop for a run that keeps making progress (or whose
# progress file never appears): generous -- the full suite takes ~11 min
# in a busy FreeCAD -- but finite, so no run can block a terminal forever.
# Deliberately BELOW the RPC server's own 1800s cap (and the socket
# timeout derived from it, ceiling+120): the client must be the one that
# reports the end, with a progress record, rather than losing the race to
# an anonymous socket error.
RUN_CEILING_SECONDS = float(os.environ.get("SILK_RUN_CEILING", "1740"))

# Exit codes, the contract stated in run_all.py's docstring. 0-3 are the
# pre-existing codes; 4 is new.
#
# Why timeout is 4 and NOT 3: 3 means "stalled", which is a DIAGNOSIS --
# progress flat AND FreeCAD's CPU flat, so the GUI thread is wedged.
# Hitting the ceiling without that diagnosis is a different statement:
# "we waited out the generous bound and cannot prove why". Collapsing the
# two would re-import exactly the ambiguity (slow vs wedged) this module
# exists to remove, and it would lie in the direction of claiming a wedge
# we never observed.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_ERROR = 2
EXIT_STALLED = 3
EXIT_TIMED_OUT = 4


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

    def __init__(self, stall_seconds=STALL_SECONDS,
                 interval=WATCHDOG_INTERVAL_SECONDS):
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


# ---- bounded wait: making the watchdog able to END the run ---------------
#
# The defect this replaces: `res = proxy.execute_code(...)` blocked the
# only thread that could read `wd.stalled`, so the stall detector recorded
# a wedge and nobody acted on it until the (up to 30-minute) call returned
# on its own. The worker thread below owns the blocking call; the calling
# (main) thread owns the deadline. Three outcomes, one wait:
#
#   fn finishes            -> "returned"  (value or error carries the outcome)
#   watchdog says stalled  -> "stalled"   (ends within one poll, NOT at 30 min)
#   ceiling expires        -> "timed-out" (backstop; report what was happening)
#
# The worker is a daemon on purpose: after an early exit nothing joins it,
# and a non-daemon worker would keep the process -- and the human's
# terminal -- alive until the abandoned socket call unwound.

_WaitResult = namedtuple(
    "_WaitResult", ["reason", "value", "error", "elapsed", "worker"])
# reason: "returned" | "stalled" | "timed-out"


def wait_for_call(fn, watchdog=None, ceiling=RUN_CEILING_SECONDS, poll=0.25):
    """Run ``fn()`` on a daemon worker thread; wait for it BOUNDED.

    Returns a ``_WaitResult``:

    * ``reason == "returned"`` -- fn finished; ``value`` or ``error`` holds
      the outcome. A result that exists is never discarded: completion is
      checked first, so a stall declared in the same poll window cannot
      throw away an outcome that already arrived.
    * ``reason == "stalled"`` -- the watchdog declared a stall while fn was
      still running. The watchdog has already printed its STALLED banner;
      the caller should stop waiting (exit EXIT_STALLED), not wait out the
      ceiling.
    * ``reason == "timed-out"`` -- ``ceiling`` seconds passed with neither.
      The caller should report what the suite was doing
      (``report_timeout``) and exit EXIT_TIMED_OUT.

    ``error`` re-raises with its original traceback when the caller wants
    exception semantics (run_all re-raises, as the blocking call did).
    ``elapsed`` is the wall clock actually spent waiting, and ``worker`` is
    the (possibly still-running, always-daemon) thread that owns ``fn``.

    ``ceiling=None`` disables the deadline (watchdog can still end it).
    ``poll`` is both the completion granularity and the reaction time to a
    declared stall -- 0.25s makes "end immediately" mean a quarter second.
    """
    box = {}

    def _worker():
        try:
            box["value"] = fn()
        except BaseException as exc:      # re-raised by the caller, below
            box["error"] = exc

    worker = threading.Thread(target=_worker, name="silk-bounded-call",
                              daemon=True)
    started = time.monotonic()
    worker.start()
    reason = "returned"
    while worker.is_alive():
        # join() returns the moment fn finishes, so a completed run is
        # picked up within `poll` -- promptly, not at the next ceiling.
        worker.join(poll)
        if not worker.is_alive():
            reason = "returned"
            break
        if watchdog is not None and getattr(watchdog, "stalled", None) is not None:
            reason = "stalled"
            break
        if ceiling is not None and time.monotonic() - started >= ceiling:
            reason = "timed-out"
            break
    return _WaitResult(reason, box.get("value"), box.get("error"),
                       time.monotonic() - started, worker)


def report_timeout(elapsed, ceiling, watchdog=None, out=None):
    """Say what the suite was doing when the wall-clock ceiling hit.

    Everything printed here is knowledge the client already has: the last
    progress record (phase, test name, index/total), how long the run has
    been going, FreeCAD's CPU time, and how long progress had been flat.
    Printed, not just stored -- the original defect was that all of this
    was computed and then read by nobody, while the human watched silence.
    """
    if out is None:
        def out(line):
            print(line, flush=True)
    rec = _read_progress()
    now = time.time()
    out("=" * 72)
    out("TIMED OUT -- the suite did not finish within the %.0f s wall-clock "
        "ceiling" % ceiling)
    out("=" * 72)
    out("  elapsed       : %.1f s of %.0f s allowed" % (elapsed, ceiling))
    if rec:
        out("  in test/phase : %s (%s)"
            % (rec.get("name") or "?", rec.get("phase") or "?"))
        out("  position      : %s of %s" % (rec.get("index"), rec.get("total")))
        t = rec.get("t")
        if t:
            out("  progress flat : %.0f s (last progress record written "
                "%.0f s ago)" % (now - t, now - t))
        pid = rec.get("pid")
        cpu = _proc_cpu_seconds(pid) if pid else None
        if cpu is not None:
            last = getattr(watchdog, "_last_cpu", None)
            if last is not None and cpu == last:
                state = ("FLAT since the watchdog's last reading -- that IS "
                         "the stall signature (which would be exit %d)"
                         % EXIT_STALLED)
            else:
                state = ("advancing, so it may be slow rather than wedged "
                         "(slow: raise SILK_RUN_CEILING; wedged: restart "
                         "FreeCAD, do not wait)")
            out("  FreeCAD pid   : %s, CPU %.1f s total -- %s"
                % (pid, cpu, state))
        else:
            out("  FreeCAD pid   : %s, CPU unreadable" % (pid,))
    elif watchdog is not None and getattr(watchdog, "phase", "starting") != "starting":
        out("  in phase      : %s (no progress record on disk any more)"
            % watchdog.phase)
    else:
        out("  no progress record: the suite never reached a test (or the "
            "record file was removed)")
    out("  exit code     : %d = timed out (this run); %d = stall confirmed "
        "by the watchdog" % (EXIT_TIMED_OUT, EXIT_STALLED))
    out("  ceiling       : raise with SILK_RUN_CEILING=<seconds> if the "
        "suite legitimately needs longer")
    out("=" * 72)
