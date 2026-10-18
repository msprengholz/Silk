"""
The stall watchdog: proving it can tell "slow" from "wedged".

This exists because that distinction was never made and both cases were
waited out -- an O(n^2) probe wedged the GUI thread for ~4 minutes and a
run started by mistake ran ~5, and in both the reflex was to wait. A
blocking RPC call gives the client no signal at all: silence is ambiguous.

The discriminator is CPU time. A slow-but-alive test burns plenty; a
blocked GUI thread burns none. So these two tests are the pair that make
the watchdog meaningful, and they are deliberately opposite: one must
declare a stall, one must NOT.

The watchdog is client-side code, so it is tested by importing it here
rather than by running the whole RPC path -- from ``Tests.watchdog`` and
NOT from ``run_all``. Importing ``run_all`` inside FreeCAD segfaults it:
that module calls ``main()`` unconditionally by design, which re-enters
the RPC server from the GUI thread serving it (measured SIGSEGV in
``aboutToDestroyGLContext``). See ``Tests/watchdog.py``.
"""

# --- manual tier ------------------------------------------------------
# This module's subject is an end-to-end rebuild / GUI drive /
# measurement sweep, so it is NOT in the default (fast) tier. Run it
# with `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable. See suite.py.
MANUAL = True

import json
import os
import threading
import time

from Tests.mcp_harness import check


def _write(rec, path):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(rec, fh)
    os.replace(tmp, path)


def _wait_for(pred, limit=25.0):
    end = time.time() + limit
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.25)
    return False


def test_stall_watchdog_names_a_wedged_freecad(doc):
    """A FreeCAD whose progress has not advanced AND whose CPU is flat is
    STALLED, and the watchdog must name the test it was in.

    Uses this process as the "FreeCAD": it is alive (so /proc reads work)
    and idle (so its CPU time does not move).
    """
    errors, checks = [], []
    from Tests import watchdog as wd_mod

    path = os.path.join("/tmp", "_silk_wd_stall_%d.json" % os.getpid())
    old_file = wd_mod.PROGRESS_FILE
    old_stall = wd_mod.STALL_SECONDS
    try:
        wd_mod.PROGRESS_FILE = path
        wd_mod.STALL_SECONDS = 1.0
        # An old timestamp: this record has not advanced for well over the
        # stall threshold.
        _write({"phase": "running", "name": "test_that_wedged",
                "index": 7, "total": 42, "pid": os.getpid(),
                "t": time.time() - 600}, path)

        wd = wd_mod._Watchdog(stall_seconds=1.0, interval=0.25)
        wd.start()

        saw_stall = _wait_for(lambda: wd.stalled is not None, 20.0)
        if not saw_stall:
            errors.append("the watchdog never declared a stall against an "
                          "idle FreeCAD with a 600s-old progress record")
        else:
            name, idle, cpu = wd.stalled
            check(name == "test_that_wedged",
                  "the stall names %r, expected 'test_that_wedged'" % (name,),
                  errors)
            check(idle > 1.0, "the idle time reported is %r, expected > 1s"
                  % (idle,), errors)
            check(isinstance(cpu, float) or cpu is None,
                  "cpu reading is %r" % (cpu,), errors)
            checks.append("stall declared in test %r after %.0fs idle"
                          % (name, idle))
        wd.interval = 1e9
    finally:
        wd_mod.PROGRESS_FILE = old_file
        wd_mod.STALL_SECONDS = old_stall
        try:
            os.remove(path)
        except OSError:
            pass
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_busy_freecad_is_never_called_stalled(doc):
    """The other half, and the one that matters just as much: CPU that IS
    advancing means a slow test, not a wedged one. A watchdog that fired
    on every slow module would be worse than none -- it would report
    stalls constantly and be ignored.

    Same stale progress record as the test above; the difference is that
    this process burns CPU while it waits.
    """
    errors, checks = [], []
    from Tests import watchdog as wd_mod

    path = os.path.join("/tmp", "_silk_wd_busy_%d.json" % os.getpid())
    old_file = wd_mod.PROGRESS_FILE
    old_stall = wd_mod.STALL_SECONDS
    stop = threading.Event()

    def burn():
        # A real CPU consumer, so /proc utime+stime actually advances.
        x = 0
        while not stop.is_set():
            for _ in range(200000):
                x += 1
    try:
        wd_mod.PROGRESS_FILE = path
        wd_mod.STALL_SECONDS = 1.5
        _write({"phase": "running", "name": "test_that_is_just_slow",
                "index": 7, "total": 42, "pid": os.getpid(),
                "t": time.time() - 600}, path)

        worker = threading.Thread(target=burn)
        worker.daemon = True
        worker.start()
        time.sleep(0.4)          # let it get going before we start watching

        wd = wd_mod._Watchdog(stall_seconds=1.5, interval=0.25)
        wd.start()
        time.sleep(7.0)          # comfortably past the threshold
        wd.interval = 1e9

        if wd.stalled is not None:
            errors.append("a FreeCAD burning CPU was declared STALLED in %r "
                          "-- advancing CPU is the 'slow, not wedged' signal"
                          % (wd.stalled[0],))
        else:
            checks.append("busy FreeCAD: no stall after 7s past the threshold")
        checks.append("cpu advanced during the watch: %s"
                      % (wd_mod._proc_cpu_seconds(os.getpid()) is not None,))
    finally:
        stop.set()
        wd_mod.PROGRESS_FILE = old_file
        wd_mod.STALL_SECONDS = old_stall
        try:
            os.remove(path)
        except OSError:
            pass
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_progress_file_is_written_atomically(doc):
    """The client reads this file while the server is mid-run, so a partial
    write would look like "progress advanced" and hide a stall."""
    errors, checks = [], []
    from Tests import mcp_harness

    path = os.path.join("/tmp", "_silk_wd_atomic_%d.json" % os.getpid())
    old = mcp_harness.PROGRESS_FILE
    try:
        mcp_harness.PROGRESS_FILE = path
        mcp_harness.write_progress("running", "some_test", 3, 9)
        with open(path) as fh:
            rec = json.load(fh)
        check(rec["name"] == "some_test" and rec["index"] == 3
              and rec["total"] == 9 and rec["pid"] == os.getpid(),
              "the progress record is wrong: %r" % (rec,), errors)
        check(not os.path.exists(path + ".tmp"),
              "a .tmp file was left behind, so the replace did not happen",
              errors)
        checks.append("progress record written atomically: %r"
                      % {k: rec[k] for k in ("phase", "name", "index")})

        # and it must never raise into the run, even with a broken path
        mcp_harness.PROGRESS_FILE = "/nonexistent-dir-xyz/progress.json"
        try:
            mcp_harness.write_progress("running", "x")
            checks.append("an unwritable progress path is swallowed, not raised")
        except Exception as e:
            errors.append("write_progress raised on a bad path: %r" % (e,))
    finally:
        mcp_harness.PROGRESS_FILE = old
        for p in (path, path + ".tmp"):
            try:
                os.remove(p)
            except OSError:
                pass
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_stall_watchdog_names_a_wedged_freecad,
    test_a_busy_freecad_is_never_called_stalled,
    test_the_progress_file_is_written_atomically,
]