"""Ending the run: the deadline fires, the stall ends the wait, DONE shows.

The defect these tests guard (measured): ``run_all.py`` blocked on ONE
``proxy.execute_code`` call for up to 30 minutes while the stall watchdog --
a thread that only ever SET ``stalled`` -- could do nothing about it, because
the only thread that could read the flag was the blocked one. A wedged run
and a finished run looked identical from outside; the human had to abort by
hand.

So there are two behaviours under test, and they are not the same thing:

1. **A stall must END the wait**, not be recorded for later reading.
2. **A finished run must report promptly and unmistakably** (``[done] ...``).

How this file is allowed to test a runner that cannot be imported
``-- run_all.py`` calls ``sys.exit(main())`` at module level, and importing
it inside FreeCAD re-enters the RPC server from the GUI thread and segfaults
(measured SIGSEGV in ``aboutToDestroyGLContext``; see ``Tests/watchdog.py``):

* the *mechanics* (``wait_for_call``, ``report_timeout``) live in
  ``Tests.watchdog`` and are unit-tested here by import -- never ``run_all``;
* the *wiring + exit codes* are tested by spawning ``run_all.py`` as a
  PLAIN-python subprocess that talks to a **fake in-process XML-RPC
  endpoint**, not to any FreeCAD. Two hard guards make that safe:
  the spawned interpreter must be named ``python*`` (FreeCAD's own
  ``sys.executable`` is ``/usr/bin/FreeCAD`` -- spawning it would launch a
  second GUI), and it must fail ``import FreeCAD`` (otherwise the subprocess
  would take the in-process path and run the whole suite again);
  ``SILK_RPC_PORT`` always points at the fake endpoint, so the human's
  FreeCAD -- one is already running, serving 9875 -- is never touched.

No test here ever manufactures a real 30-minute hang: every deadline is
injected (``SILK_RUN_CEILING=2`` or ``wait_for_call(ceiling=...)``), and the
promptness assertions measure the wall clock.
"""

# --- FAST tier, deliberately ------------------------------------------
# No MANUAL marker: this module's subject is the RUNNER's own plumbing
# (`run_all.py`'s remote-call signature + `Tests/watchdog`'s deadline
# mechanics), i.e. exactly the machinery a tier split has to change to
# exist. Deferring it would hide a broken guard behind the mechanism it
# guards -- measured cost ~1.3 s, so it was never slow enough to defer.
# The reason is recorded in Tests/test_manual_tier.py, which pins the set.

import json
import os
import re
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
from contextlib import contextmanager

import xmlrpc.server

from Tests.mcp_harness import check

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(MOD_DIR, "Tests", "run_all.py")

# Interpreter used to spawn the runner. sys.executable is OFF LIMITS here:
# inside FreeCAD it is /usr/bin/FreeCAD, and running it with a script would
# launch a second GUI FreeCAD that fights over the RPC port (this happened
# once and had to be cleaned up by hand).
_PY3 = None
_PY3_PROBED = False

_SCRATCH_PATHS = []


def _ok(checks, errors):
    return {"pass": not errors, "errors": errors, "checks": checks}


def _scratch_path(tag):
    p = "/tmp/silk_rt_%s_%d_%d.json" % (tag, os.getpid(), len(_SCRATCH_PATHS))
    _SCRATCH_PATHS.append(p)
    return p


def _cleanup_scratch():
    for p in _SCRATCH_PATHS + [x + ".tmp" for x in _SCRATCH_PATHS]:
        try:
            os.remove(p)
        except OSError:
            pass
    del _SCRATCH_PATHS[:]


def _clean_env(extra):
    """The subprocess env: inherit, minus anything that could make plain
    python3 import FreeCAD (PYTHONPATH/PYTHONHOME pointing into a FreeCAD
    bundle) or inherit a SILK_* setting of our own (a stray SILK_RUN_CEILING
    in the human's shell must not turn these assertions into surprises)."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "PYTHONHOME") and not k.startswith("SILK_")}
    env.update(extra)
    return env


def _python3():
    global _PY3, _PY3_PROBED
    if _PY3 is None:
        candidates = ["/usr/bin/python3", "/usr/local/bin/python3",
                      shutil.which("python3") or ""]
        for cand in candidates:
            if (cand and os.path.basename(cand).startswith("python")
                    and os.access(cand, os.X_OK)):
                _PY3 = cand
                break
        if _PY3 is None:
            raise RuntimeError(
                "no safe plain python3 interpreter found (sys.executable is "
                "%r -- spawning THAT would launch a second FreeCAD)"
                % sys.executable)
    if not _PY3_PROBED:
        probe = subprocess.run([_PY3, "-c", "import FreeCAD"],
                               capture_output=True, timeout=30,
                               env=_clean_env({}))
        if probe.returncode == 0:
            raise RuntimeError(
                "%s can import FreeCAD -- spawning it would run the suite "
                "in-process (a second full run); refusing" % _PY3)
        _PY3_PROBED = True
    return _PY3


def _run_runner(args, port, env_extra=None, timeout=60):
    """Run Tests/run_all.py as a plain-python subprocess talking to `port`.

    Returns (returncode, output, wall_seconds); returncode is None when the
    subprocess overran `timeout` -- which for these tests is itself a
    failure signal (a deadline that never fired), asserted by the caller.

    NOTE: capture_output via communicate(), never a shell pipe -- SIGPIPE
    from head/grep closes the RPC client mid-flight (this cost a session
    real time once).
    """
    env = _clean_env(env_extra or {})
    env.setdefault("SILK_PROGRESS_FILE", _scratch_path("progress"))
    env["SILK_RPC_PORT"] = str(port)
    cmd = [_python3(), RUNNER] + list(args)
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=MOD_DIR, env=env,
                              capture_output=True, text=True,
                              timeout=timeout)
        out = proc.stdout + proc.stderr
        return proc.returncode, out, time.time() - t0
    except subprocess.TimeoutExpired:
        return None, "<<runner did not exit within the %ds budget>>" % timeout, \
            time.time() - t0


def _result_message(results, timings=None, before=(), after=()):
    """A fake FreeCAD response body, shaped like the real one."""
    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r.get("pass")),
        "failed": sum(1 for r in results if not r.get("pass")),
        "results": results,
        "timings": timings if timings is not None else
        [{"name": r["name"], "seconds": 0.1} for r in results],
    }
    lines = list(before) + ["RESULT:" + json.dumps(summary)] + list(after)
    return "\n".join(lines) + "\n"


class _ThreadingXMLRPC(socketserver.ThreadingMixIn,
                       xmlrpc.server.SimpleXMLRPCServer):
    daemon_threads = True
    allow_reuse_address = True
    # server_close() would otherwise JOIN the blocked execute_code handler
    # (ThreadingMixIn._threads.join()), so fake.stop() would hang for as
    # long as the handler is blocked -- measured in the 3.14 sources. The
    # handler is a daemon; it unwinds when the test releases it.
    block_on_close = False

    def handle_error(self, request, client_address):
        # A client that exited at its deadline leaves a dead socket when
        # the blocked handler finally unwinds. That is the point of the
        # deadline, not an error worth a traceback in the human's console.
        pass


class _FakeSilkRpc(object):
    """A silk RPC endpoint whose execute_code does whatever the test says.

    The real endpoint runs the real suite; these tests must never do that
    (exactly one FreeCAD exists and it belongs to the human). This one
    answers instantly, blocks until released, or records what it was asked
    -- and every subprocess's SILK_RPC_PORT points HERE.
    """

    def __init__(self, execute):
        self.execute = execute
        self.calls = []
        self.server = None
        self.port = None
        self._thread = None

    def _ping(self):
        return True

    def _execute_code(self, code, rpc_timeout=None):
        self.calls.append({"code": code, "rpc_timeout": rpc_timeout})
        return self.execute(code, rpc_timeout)

    def start(self):
        self.server = _ThreadingXMLRPC(("127.0.0.1", 0), allow_none=True,
                                       logRequests=False)
        self.server.register_function(self._ping, "ping")
        self.server.register_function(self._execute_code, "execute_code")
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever,
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()


@contextmanager
def _fake_rpc(execute):
    fake = _FakeSilkRpc(execute).start()
    try:
        yield fake
    finally:
        fake.stop()


def _instant(message):
    def _impl(code, rpc_timeout):
        return {"success": True, "message": message}
    return _impl


def _blocking(release, message=None):
    """execute_code that never finishes until the test releases it --
    the manufactured 'run that never ends', without any real hang."""
    def _impl(code, rpc_timeout):
        release.wait(300)
        return {"success": True,
                "message": message or _result_message(
                    [{"name": "late", "pass": True}])}
    return _impl


def _write_record(path, rec):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(rec, fh)
    os.replace(tmp, path)


def _progress_writer(path, record, period=0.25):
    """Keep `record` on disk for as long as the subprocess runs.

    run_all.py DELETES the progress file at the start of every run
    ("never trust a previous run's record"), so a single write before
    spawning it would not survive; a writer also keeps the record's
    `t` stable, so it reads as 'flat for (now - t)' both to the watchdog
    and to the timeout report.
    """
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            try:
                _write_record(path, record)
            except OSError:
                pass
            stop.wait(period)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return stop


def _idle_proc():
    """A process whose CPU time is guaranteed FLAT -- unlike this FreeCAD,
    which is busy running the suite, so its CPU would move between
    watchdog ticks and defeat the stall check."""
    return subprocess.Popen(["sleep", "60"])


def _stop_idle_proc(proc):
    try:
        proc.terminate()
        proc.wait(5)
    except Exception:
        pass


def _closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---- unit tests: the mechanics, imported from Tests.watchdog -------------
#
# NOT from run_all: importing run_all inside FreeCAD segfaults it (it calls
# sys.exit(main()) at module level, which re-enters the RPC server from the
# GUI thread serving it).

def test_wait_for_call_returns_the_value_promptly(doc):
    """Failure mode 2 (the human's actual complaint): a DONE run must
    produce its result promptly and unmistakably -- completion picked up
    within the poll interval, outcome intact, exceptions preserved."""
    from Tests import watchdog as wd

    errors, checks = [], []
    t0 = time.time()
    r = wd.wait_for_call(lambda: "payload", ceiling=10.0, poll=0.05)
    wall = time.time() - t0
    check(r.reason == "returned", "reason %r, expected 'returned'"
          % (r.reason,), errors)
    check(r.value == "payload", "value %r, expected 'payload'" % (r.value,),
          errors)
    check(r.error is None, "unexpected error %r" % (r.error,), errors)
    check(wall < 5.0, "a call returning immediately took %.1fs to be seen"
          % wall, errors)
    checks.append("returned value seen in %.3fs" % wall)

    # And the outcome of a call that RAISES must survive the handoff --
    # swallowing it would turn a crash into a silent wait.
    boom = RuntimeError("rpc exploded")

    def _raise():
        raise boom

    r2 = wd.wait_for_call(_raise, ceiling=10.0, poll=0.05)
    check(r2.reason == "returned", "raising call: reason %r"
          % (r2.reason,), errors)
    check(r2.error is boom, "the raised exception did not survive the "
          "worker handoff (got %r)" % (r2.error,), errors)
    check(r2.value is None, "a raising call produced a value: %r"
          % (r2.value,), errors)
    checks.append("exception preserved for the caller to re-raise")
    return _ok(checks, errors)


def test_wait_for_call_deadline_ends_a_never_ending_call(doc):
    """Failure mode 1: a call that never finishes must be abandoned at the
    deadline -- with the wall clock measured, and with the leftover worker
    as a DAEMON so it cannot keep the process (or the human's terminal)
    alive afterwards."""
    from Tests import watchdog as wd

    errors, checks = [], []
    release = threading.Event()

    def never():
        release.wait(30)
        return "late"

    t0 = time.time()
    r = wd.wait_for_call(never, ceiling=1.0, poll=0.05)
    wall = time.time() - t0
    try:
        check(r.reason == "timed-out", "reason %r, expected 'timed-out'"
              % (r.reason,), errors)
        check(wall < 6.0, "the 1.0s deadline took %.1fs of wall clock to "
              "fire -- the deadline is not being enforced" % wall, errors)
        check(r.worker.is_alive(), "the blocked worker vanished instead of "
              "being abandoned (it should still be inside fn)", errors)
        check(r.worker.daemon is True,
              "the orphan worker is NOT a daemon -- the process would wait "
              "for it and keep the terminal blocked", errors)
        checks.append("deadline fired in %.2fs; worker daemon=%s, abandoned "
                      "mid-call" % (wall, r.worker.daemon))
    finally:
        release.set()
        r.worker.join(10.0)
    check(not r.worker.is_alive(), "the released worker never exited",
          errors)
    return _ok(checks, errors)


def test_wait_for_call_stall_ends_the_wait_before_the_ceiling(doc):
    """The watchdog's knowledge must TERMINATE the run. Ceiling is 20s;
    the stall is declared within ~1s -- if the stall cannot end the wait,
    this test sits for the full ceiling and reports reason 'timed-out'."""
    from Tests import watchdog as wd

    errors, checks = [], []
    path = _scratch_path("unit_stall")
    old_file = wd.PROGRESS_FILE
    release = threading.Event()
    idle = _idle_proc()
    watch = None
    r = None
    try:
        wd.PROGRESS_FILE = path
        # t 600s in the past: progress is unambiguously flat, and the pid
        # is `sleep`, so CPU is flat too -- the stall signature.
        _write_record(path, {"phase": "running", "name": "test_that_wedged",
                             "index": 7, "total": 42, "pid": idle.pid,
                             "t": time.time() - 600})
        watch = wd._Watchdog(stall_seconds=0.5, interval=0.1)
        watch.start()

        def never():
            release.wait(30)
            return "late"

        t0 = time.time()
        r = wd.wait_for_call(never, watchdog=watch, ceiling=20.0, poll=0.05)
        wall = time.time() - t0
        check(r.reason == "stalled", "reason %r, expected 'stalled' -- the "
              "watchdog must be able to END the wait" % (r.reason,), errors)
        check(wall < 10.0, "the stall ended the wait only after %.1fs "
              "(ceiling 20s) -- it waited out the ceiling instead of the "
              "stall" % wall, errors)
        check(watch.stalled is not None, "the watchdog never declared the "
              "stall this test set up", errors)
        checks.append("stall declared and honored in %.2fs of a 20s ceiling"
                      % wall)
    finally:
        release.set()
        if r is not None:
            r.worker.join(10.0)
        if watch is not None:
            watch.interval = 1e9
        wd.PROGRESS_FILE = old_file
        _stop_idle_proc(idle)
        _cleanup_scratch()
    return _ok(checks, errors)


def test_timeout_report_names_the_suite_and_the_clock(doc):
    """The timeout report must SURFACE what the watchdog knows: the last
    progress record (phase, test name, index/total), elapsed vs ceiling,
    FreeCAD's CPU, and how long progress had been flat -- plus the missing
    record case, which must speak instead of crashing."""
    from Tests import watchdog as wd

    errors, checks = [], []
    path = _scratch_path("unit_report")
    old_file = wd.PROGRESS_FILE
    try:
        wd.PROGRESS_FILE = path
        _write_record(path, {"phase": "running",
                             "name": "test_that_never_returns",
                             "index": 7, "total": 42, "pid": os.getpid(),
                             "t": time.time() - 300})
        lines = []
        # Unstarted watchdog on purpose: the report must not depend on the
        # watchdog thread having ticked at all.
        watch = wd._Watchdog()
        wd.report_timeout(1740.0, 1740.0, watchdog=watch, out=lines.append)
        text = "\n".join(lines)
        checks.append(text)
        check("TIMED OUT" in text, "no TIMED OUT banner", errors)
        check("test_that_never_returns" in text,
              "the report does not name the test the suite was in: %r"
              % text, errors)
        check("7 of 42" in text, "the report does not give the position "
              "(7 of 42): %r" % text, errors)
        check("1740" in text, "elapsed/ceiling not reported", errors)
        check(re.search(r"progress flat\s*: (29[0-9]|30[0-9]) s", text),
              "how long progress was flat is not reported (~300s expected): "
              "%r" % text, errors)
        check(str(os.getpid()) in text and "CPU" in text,
              "FreeCAD's pid/CPU not reported: %r" % text, errors)

        # No record at all: say so, do not raise.
        os.remove(path)
        lines2 = []
        try:
            wd.report_timeout(5.0, 1740.0, watchdog=watch,
                              out=lines2.append)
        except Exception as exc:
            errors.append("report_timeout raised without a progress "
                          "record: %r" % (exc,))
            text2 = ""
        else:
            text2 = "\n".join(lines2)
            check("TIMED OUT" in text2 and "no progress record" in text2,
                  "the no-record case is silent: %r" % text2, errors)
            checks.append("no-record case reported without crashing")
    finally:
        wd.PROGRESS_FILE = old_file
        _cleanup_scratch()
    return _ok(checks, errors)


# ---- end-to-end: run_all.py as a subprocess, against the fake endpoint ----

def test_runner_reports_a_completed_run_promptly(doc):
    """A run that COMPLETES: exits 0 on success, 1 on failure, both
    promptly, with the [done] banner, the per-test lines, and the
    per-test timings ([slowest]) all intact."""
    errors, checks = [], []
    pass_msg = _result_message(
        [{"name": "t_alpha", "pass": True},
         {"name": "t_beta", "pass": True}],
        timings=[{"name": "t_alpha", "seconds": 3.1},
                 {"name": "t_beta", "seconds": 2.0}],
        before=["[reload] fake reload line"])
    with _fake_rpc(_instant(pass_msg)) as fake:
        rc, out, wall = _run_runner([], fake.port, timeout=45)
    check(rc == 0, "a passing run exited %r (output tail: %r)"
          % (rc, out[-400:]), errors)
    check(wall < 30.0, "a completing run took %.1fs of wall clock" % wall,
          errors)
    check("[done] suite call returned after" in out,
          "no [done] banner: a finished run is indistinguishable from a "
          "wedged one", errors)
    check("[PASS] t_alpha" in out and "[PASS] t_beta" in out,
          "per-test result lines missing", errors)
    check("2/2 passed, 0 failed" in out, "summary line missing", errors)
    check("[slowest]" in out, "per-test timings ([slowest]) no longer "
          "reported", errors)
    check("[reload] fake reload line" in out, "[reload] lines no longer "
          "echoed", errors)
    checks.append("pass run: exit 0 in %.1fs with [done]" % wall)

    fail_msg = _result_message(
        [{"name": "t_bad", "pass": False, "errors": ["boom"]}])
    with _fake_rpc(_instant(fail_msg)) as fake:
        rc2, out2, wall2 = _run_runner([], fake.port, timeout=45)
    check(rc2 == 1, "a run with 1 failure exited %r, expected 1" % (rc2,),
          errors)
    check("[FAIL] t_bad" in out2 and "ERROR: boom" in out2,
          "failure lines missing from a failing run", errors)
    check("0/1 passed, 1 failed" in out2, "failing summary missing",
          errors)
    check(wall2 < 30.0, "a completing run took %.1fs of wall clock"
          % wall2, errors)
    checks.append("fail run: exit 1 in %.1fs" % wall2)
    _cleanup_scratch()
    return _ok(checks, errors)


def test_runner_deadline_expiry_returns_promptly_and_reports(doc):
    """The measured defect, end to end: the call NEVER returns, ceiling=2s.

    Asserts the wall clock (must be seconds, not 30 minutes), exit code 4,
    and that the report prints what the suite was doing -- last progress
    record (name + position), elapsed/ceiling, flatness, CPU. Also asserts
    NO [done] banner: timeout must not look like completion.

    The orphan guarantee is exercised here too: the fake endpoint's
    handler is still blocked when the runner must exit. If the worker were
    not a daemon, the process would wait for it, overrun this test's
    budget, and return rc=None.
    """
    errors, checks = [], []
    path = _scratch_path("deadline")
    release = threading.Event()
    idle = _idle_proc()
    writer_stop = None
    try:
        # t written at spawn time and never refreshed: 'progress flat'
        # grows with the run. run_all.py deletes the file at start, so
        # keep re-asserting it.
        writer_stop = _progress_writer(
            path, {"phase": "running", "name": "test_that_never_returns",
                   "index": 7, "total": 42, "pid": idle.pid,
                   "t": time.time()})
        with _fake_rpc(_blocking(release)) as fake:
            rc, out, wall = _run_runner([], fake.port, timeout=45,
                                        env_extra={
                                            "SILK_PROGRESS_FILE": path,
                                            "SILK_RUN_CEILING": "2"})
        check(rc == 4, "deadline run exited %r, expected 4 (output tail: "
              "%r)" % (rc, out[-500:]), errors)
        check(rc is not None and wall < 30.0,
              "deadline run took %.1fs of wall clock (budget 45s) -- the "
              "deadline did not end the wait promptly" % wall, errors)
        check("TIMED OUT" in out, "no TIMED OUT banner", errors)
        check("test_that_never_returns" in out,
              "the timeout report does not name the test: %r" % out[-800:],
              errors)
        check("7 of 42" in out, "the timeout report has no position "
              "(7 of 42): %r" % out[-800:], errors)
        check(re.search(r"elapsed\s*: [0-9.]+ s of [0-9.]+ s allowed", out),
              "elapsed/ceiling missing from the timeout report", errors)
        check("progress flat" in out, "flat-progress duration missing from "
              "the timeout report", errors)
        check("CPU" in out, "FreeCAD CPU missing from the timeout report",
              errors)
        check("[done]" not in out, "a TIMED OUT run also claimed [done]",
              errors)
        checks.append("deadline 2s -> exit 4 in %.1fs, record surfaced"
                      % wall)
    finally:
        release.set()
        if writer_stop is not None:
            writer_stop.set()
        _stop_idle_proc(idle)
        _cleanup_scratch()
    return _ok(checks, errors)


def test_runner_stall_ends_the_run_before_the_ceiling(doc):
    """The watchdog-detected-stall path must END the run (exit 3), not
    wait out the ceiling: ceiling is 45s, the stall declares within ~1s,
    so the wall clock assertion (< 20s) is what proves the stall -- not
    the ceiling -- ended it."""
    errors, checks = [], []
    path = _scratch_path("stall")
    release = threading.Event()
    idle = _idle_proc()
    writer_stop = None
    try:
        writer_stop = _progress_writer(
            path, {"phase": "running", "name": "test_that_wedged",
                   "index": 7, "total": 42, "pid": idle.pid,
                   "t": time.time() - 600})
        with _fake_rpc(_blocking(release)) as fake:
            rc, out, wall = _run_runner([], fake.port, timeout=75,
                                        env_extra={
                                            "SILK_PROGRESS_FILE": path,
                                            "SILK_STALL_SECONDS": "1",
                                            "SILK_WATCHDOG_INTERVAL": "0.25",
                                            "SILK_RUN_CEILING": "45"})
        check(rc == 3, "stall run exited %r, expected 3 (output tail: %r)"
              % (rc, out[-500:]), errors)
        check(rc is not None and wall < 20.0,
              "stall run took %.1fs -- the ceiling is 45s, so this ended "
              "(if at all) by the ceiling, not by the stall" % wall, errors)
        check("STALLED" in out, "no STALLED banner", errors)
        check("test_that_wedged" in out, "the stall report does not name "
              "the test: %r" % out[-800:], errors)
        checks.append("stall ended the run with exit 3 in %.1fs of a 45s "
                      "ceiling" % wall)
    finally:
        release.set()
        if writer_stop is not None:
            writer_stop.set()
        _stop_idle_proc(idle)
        _cleanup_scratch()
    return _ok(checks, errors)


def test_runner_flags_and_filter_reach_the_remote_call(doc):
    """--inspect / --save / --force-reload / --keep-namespace and the
    filter argument must keep working: echoed to the operator AND passed
    into the remote call in the right slots (close_docs False with
    inspect/save, save_dir set, filter as the filter -- the historical bug
    was a flag VALUE leaking into the filter slot)."""
    errors, checks = [], []
    msg = _result_message(
        [{"name": "t", "pass": True}],
        after=["[saved] /tmp/fake/_mcp_test_x.FCStd"])
    with _fake_rpc(_instant(msg)) as fake:
        rc, out, wall = _run_runner(
            ["--inspect", "--save", "--force-reload", "--keep-namespace",
             "timeout_flag_probe"], fake.port, timeout=45,
            env_extra={"SILK_PROGRESS_FILE": _scratch_path("flags")})
        calls = list(fake.calls)
    check(rc == 0, "flagged run exited %r (tail: %r)" % (rc, out[-400:]),
          errors)
    check(wall < 30.0, "flagged run took %.1fs" % wall, errors)
    for needle in ("--inspect: test documents will be left open",
                   "--save: test geometry will be persisted",
                   "--force-reload: reimporting",
                   "--keep-namespace: leaving stale",
                   "filter: timeout_flag_probe"):
        check(needle in out, "operator echo missing: %r" % needle, errors)
    check("[saved]" in out, "--save lines in the response are not echoed",
          errors)
    check(len(calls) == 1, "%d execute_code calls, expected 1"
          % len(calls), errors)
    if calls:
        code = calls[0]["code"]
        check("_silk_run(True, True, 'timeout_flag_probe', False, " in code,
              "the flags did not reach _silk_run in the right slots "
              "(force, keep_ns, filter, close_docs): ...%r"
              % code[code.find("_silk_run"):code.find("_silk_run") + 120],
              errors)
        check("_inspect" in code, "--save did not pass the save dir", errors)
        # The two trailing slots, in order: test_modules (no --changed, so
        # None -- a filter must not smuggle a module list in) and
        # include_manual (no --manual, so False -- a filter must not widen
        # the tier either, #122). Both are pinned by position because a
        # leaked flag VALUE landing in them is silent: the run merely
        # executes the wrong set.
        check(code.rstrip().endswith("None, False)"),
              "the trailing slots after save_dir must be test_modules=None, "
              "include_manual=False for a plain filter run: %r"
              % code[-60:], errors)
        checks.append("remote call carries force/keep/filter/close_docs/"
                      "save_dir/test_modules/include_manual correctly")
    _cleanup_scratch()
    return _ok(checks, errors)


def test_runner_changed_flag_still_works(doc):
    """--changed [ref]: the ref must be consumed as a ref, never leak into
    the test filter (the bug that once reported 0/0 with no error), and the
    run must still dispatch and exit with a result code."""
    errors, checks = [], []
    msg = _result_message([{"name": "t", "pass": True}])
    with _fake_rpc(_instant(msg)) as fake:
        rc, out, wall = _run_runner(["--changed", "HEAD"], fake.port,
                                    timeout=75)
    check(rc == 0, "--changed run exited %r (tail: %r)"
          % (rc, out[-400:]), errors)
    check("--changed:" in out, "--changed produced no selection report",
          errors)
    check("filter: HEAD" not in out,
          "the --changed ref leaked into the test filter (historical bug)",
          errors)
    check("[done] suite call returned after" in out, "no [done] banner",
          errors)
    check(wall < 60.0, "--changed run took %.1fs" % wall, errors)
    checks.append("--changed HEAD dispatched in %.1fs" % wall)
    _cleanup_scratch()
    return _ok(checks, errors)


def test_runner_unreachable_freecad_still_exits_2(doc):
    """Exit code 2 is contract too: nothing listening on the port must
    still fail fast with the 'not reachable' message, not hang."""
    errors, checks = [], []
    port = _closed_port()
    rc, out, wall = _run_runner([], port, timeout=30)
    check(rc == 2, "unreachable FreeCAD exited %r, expected 2" % (rc,),
          errors)
    check("No running FreeCAD reachable" in out, "no reachability message: "
          "%r" % out[-300:], errors)
    check(wall < 25.0, "the unreachable case took %.1fs" % wall, errors)
    checks.append("unreachable -> exit 2 in %.1fs" % wall)
    _cleanup_scratch()
    return _ok(checks, errors)


ALL_TESTS = [
    test_wait_for_call_returns_the_value_promptly,
    test_wait_for_call_deadline_ends_a_never_ending_call,
    test_wait_for_call_stall_ends_the_wait_before_the_ceiling,
    test_timeout_report_names_the_suite_and_the_clock,
    test_runner_reports_a_completed_run_promptly,
    test_runner_deadline_expiry_returns_promptly_and_reports,
    test_runner_stall_ends_the_run_before_the_ceiling,
    test_runner_flags_and_filter_reach_the_remote_call,
    test_runner_changed_flag_still_works,
    test_runner_unreachable_freecad_still_exits_2,
]
