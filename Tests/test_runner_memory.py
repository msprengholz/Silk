"""Runner memory hygiene: the Report View cap and malloc_trim (ticket #79).

The leak this guards: FreeCAD's Report View is a QTextEdit named
"Report view" whose QTextDocument has maximumBlockCount() == 0 --
**uncapped** -- so it retains every console message the process has ever
printed. Measured in #79: 2,293,056 characters across 30,789 blocks after
five runs of one test module, with RSS growing ~20 MB per run, linearly,
no plateau. That is where the memory went.

So the runner caps it (silk_reload.cap_report_view) and, at the end of a
run, asks glibc to return what has been released to the OS
(silk_reload.malloc_trim). Both are test infrastructure on purpose: the
workbench must not go behind a user's back and truncate THEIR Report
View.

These tests assert *what was set* and *what was invoked* -- never how
many megabytes came back, which is machine-dependent.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Tests import silk_reload  # noqa: E402

MOD_DIR = silk_reload.MOD_DIR


def _ok(checks, errors, passed=None):
    """A test fails when it collected errors, unless it says otherwise."""
    return {
        "pass": (not errors) if passed is None else passed,
        "checks": checks,
        "errors": errors,
    }


# ----------------------------------------------------------------------
# fakes -- so the no-GUI / no-widget paths are exercised, not imagined
# ----------------------------------------------------------------------

class FakeDocument(object):
    def __init__(self, block_count=0):
        self._max = block_count

    def maximumBlockCount(self):
        return self._max

    def setMaximumBlockCount(self, n):
        self._max = n


class FakeWidget(object):
    """Stands in for the Report view QTextEdit."""

    def __init__(self, name="Report view", block_count=0):
        self._name = name
        self.doc = FakeDocument(block_count)

    def objectName(self):
        return self._name

    def document(self):
        return self.doc


class FakeWindow(object):
    def __init__(self, children=(), raiser=None):
        self._children = list(children)
        self._raiser = raiser

    def findChildren(self, cls):
        if self._raiser is not None:
            raise self._raiser
        return list(self._children)


class FakeGui(object):
    def __init__(self, main_window):
        self._mw = main_window
        self.raises = False

    def getMainWindow(self):
        if self.raises:
            raise RuntimeError("no main window here")
        return self._mw


# ----------------------------------------------------------------------
# the cap, on the real widget
# ----------------------------------------------------------------------

def test_report_view_cap_is_applied_to_the_real_report_view(doc):
    """The real Report View goes from uncapped to the cap constant.

    Starts by forcing the live widget back to the buggy state
    (maximumBlockCount 0), because that IS the bug: the assertion has to
    be able to see the cap take effect, not merely find it already there
    from an earlier run.
    """
    errors = []
    checks = []
    try:
        import FreeCADGui as Gui
        from PySide import QtWidgets
    except Exception as exc:  # pragma: no cover - headless FreeCADCmd
        return _ok(["no GUI in this FreeCAD (%r) -- the Report View does not "
                    "exist headless; nothing to cap" % (exc,)], errors)
    mw = Gui.getMainWindow()
    if mw is None:
        return _ok(["no main window (headless run); nothing to cap"], errors)
    views = [w for w in mw.findChildren(QtWidgets.QTextEdit)
             if w.objectName() == "Report view"]
    checks.append("%d 'Report view' QTextEdit(s) in the main window" % len(views))
    if not views:
        errors.append("no 'Report view' QTextEdit found in a GUI that has a "
                      "main window -- the widget this caps has moved")
        return _ok(checks, errors)

    # Put the live widget back into the buggy state first: an already
    # capped widget would make this pass whether or not the runner caps
    # anything.
    for w in views:
        w.document().setMaximumBlockCount(0)
    checks.append("forced maximumBlockCount back to 0 (uncapped) on %d "
                  "widget(s)" % len(views))

    report = silk_reload.cap_report_view()
    checks.append("cap_report_view -> status=%s cap=%s changed=%d"
                  % (report["status"], report["cap"], len(report["changed"])))
    if report["status"] not in ("capped", "already-capped"):
        errors.append("cap_report_view did not cap the real Report View: %r"
                      % (report,))
        return _ok(checks, errors)

    cap = silk_reload.REPORT_VIEW_BLOCK_CAP
    if cap != 2000:
        errors.append("REPORT_VIEW_BLOCK_CAP is %r, not the verified 2000" % (cap,))
    for w in views:
        got = w.document().maximumBlockCount()
        checks.append("Report view maximumBlockCount -> %d" % got)
        if not 0 < got <= cap:
            errors.append("Report View is still %d blocks after capping "
                          "(cap constant is %d)" % (got, cap))
    return _ok(checks, errors)


def test_cap_report_view_takes_an_uncapped_widget_to_the_cap(doc):
    """Same transition, on a fake, so it does not depend on the GUI."""
    errors = []
    checks = []
    widget = FakeWidget()  # block_count 0 == uncapped == the bug
    report = silk_reload.cap_report_view(
        gui=FakeGui(FakeWindow([widget, FakeWidget("Python console")])))
    checks.append("status=%s, cap=%s" % (report["status"], report["cap"]))
    if report["status"] != "capped":
        errors.append("status is %r, expected 'capped'" % report["status"])
    if widget.doc.maximumBlockCount() != silk_reload.REPORT_VIEW_BLOCK_CAP:
        errors.append("widget capped to %r, expected %r"
                      % (widget.doc.maximumBlockCount(),
                         silk_reload.REPORT_VIEW_BLOCK_CAP))
    return _ok(checks, errors)


def test_cap_report_view_never_raises_a_smaller_existing_cap(doc):
    """A cap the user set lower stays; a looser one is tightened."""
    errors = []
    checks = []
    tight = FakeWidget(block_count=500)
    loose = FakeWidget(block_count=9999)
    report = silk_reload.cap_report_view(
        gui=FakeGui(FakeWindow([tight, loose])))
    checks.append("status=%s, changed=%d, kept=%d"
                  % (report["status"], len(report["changed"]), len(report["kept"])))
    if tight.doc.maximumBlockCount() != 500:
        errors.append("the runner RAISED a user's smaller cap of 500 to %r"
                      % (tight.doc.maximumBlockCount(),))
    if loose.doc.maximumBlockCount() != silk_reload.REPORT_VIEW_BLOCK_CAP:
        errors.append("a loose cap of 9999 was not tightened (now %r)"
                      % (loose.doc.maximumBlockCount(),))
    # And the all-smaller case is reported as such, not as "capped".
    report2 = silk_reload.cap_report_view(gui=FakeGui(FakeWindow([tight])))
    checks.append("nothing to do -> status=%s" % report2["status"])
    if report2["status"] != "already-capped":
        errors.append("status for an already-smaller cap is %r, expected "
                      "'already-capped'" % report2["status"])
    return _ok(checks, errors)


# ----------------------------------------------------------------------
# the no-GUI / no-widget paths -- a no-op, never a crash
# ----------------------------------------------------------------------

def test_cap_report_view_is_a_no_op_without_a_report_view(doc):
    """No Gui, no main window, no widget, a raising widget: status, no raise."""
    errors = []
    checks = []

    def status_of(label, **kwargs):
        try:
            report = silk_reload.cap_report_view(**kwargs)
        except Exception as exc:
            errors.append("%s: cap_report_view RAISED %r" % (label, exc))
            return None
        checks.append("%s -> %r" % (label, report["status"]))
        return report["status"]

    if status_of("no Gui at all", gui=None) != "no-gui":
        errors.append("gui=None did not report 'no-gui'")
    if status_of("no main window", gui=FakeGui(None)) != "no-main-window":
        errors.append("a Gui whose main window is None did not report "
                      "'no-main-window'")
    if status_of("a main window that raises",
                 gui=FakeGui(FakeWindow(raiser=RuntimeError("boom")))) != "error":
        errors.append("a raising getMainWindow/findChildren did not report 'error'")
    if status_of("main window without a Report view",
                 gui=FakeGui(FakeWindow([FakeWidget("Python console")]))) != "not-found":
        errors.append("a window with only a Python console did not report "
                      "'not-found'")
    if status_of("an empty main window", gui=FakeGui(FakeWindow())) != "not-found":
        errors.append("an empty main window did not report 'not-found'")
    # A deleted C++ widget raises on objectName()/document(); it must not
    # take the run down with it.
    class Exploding(object):
        def objectName(self):
            raise RuntimeError("wrapped C/C++ object has been deleted")

    if status_of("a deleted C++ widget",
                 gui=FakeGui(FakeWindow([Exploding()]))) not in ("error", "not-found"):
        errors.append("a deleted widget was not handled")
    return _ok(checks, errors)


# ----------------------------------------------------------------------
# malloc_trim
# ----------------------------------------------------------------------

def test_malloc_trim_runs_on_glibc_and_reports_what_it_did(doc):
    """On Linux/glibc it actually calls malloc_trim(0), and says so.

    The RSS it reclaimed is NOT asserted: how much comes back depends on
    the machine and on what happened to be freed. Only that the call was
    made, and that the report carries before/after for a human to read.
    """
    errors = []
    checks = []
    called = []

    class FakeLibc(object):
        def malloc_trim(self, pad):
            called.append(pad)
            return 1

    report = silk_reload.malloc_trim(loader=lambda: FakeLibc())
    checks.append("trimmed=%s reason=%r rss_before=%s rss_after=%s"
                  % (report["trimmed"], report.get("reason"),
                     report.get("rss_before"), report.get("rss_after")))
    if not report["trimmed"]:
        errors.append("malloc_trim did not run with a working libc: %r" % (report,))
    if called != [0]:
        errors.append("malloc_trim was called with %r, expected [0]" % (called,))
    for key in ("rss_before", "rss_after"):
        if report.get(key) is not None and not isinstance(report[key], float):
            errors.append("%s is %r, expected an MB float or None"
                          % (key, report[key]))
    return _ok(checks, errors)


def test_malloc_trim_is_a_no_op_off_glibc_or_without_the_symbol(doc):
    """Non-Linux, unimportable ctypes, missing libc, missing symbol: status."""
    errors = []
    checks = []

    def report_of(label, **kwargs):
        try:
            report = silk_reload.malloc_trim(**kwargs)
        except Exception as exc:
            errors.append("%s: malloc_trim RAISED %r" % (label, exc))
            return None
        if report["trimmed"]:
            errors.append("%s: reported a successful trim" % label)
        checks.append("%s -> trimmed=%s reason=%r"
                      % (label, report["trimmed"], report.get("reason")))
        return report

    report_of("darwin", platform="darwin")
    report_of("win32", platform="win32")
    report_of("no libc.so.6", loader=_raise_oserror)
    report_of("libc without malloc_trim", loader=_libc_without_symbol)
    report_of("ctypes missing", loader=_raise_import_error)
    return _ok(checks, errors)


def _raise_oserror():
    raise OSError("libc.so.6: cannot open shared object file")


def _raise_import_error():
    raise ImportError("No module named 'ctypes'")


def _libc_without_symbol():
    class NoTrim(object):
        pass

    return NoTrim()


# ----------------------------------------------------------------------
# reporting -- the fix has to be visible or it gets re-derived
# ----------------------------------------------------------------------

def test_memory_lines_name_the_cap_and_the_trim(doc):
    """describe_memory() says what was capped and what the trim returned."""
    errors = []
    checks = []
    lines = silk_reload.describe_memory(
        report_view={"status": "capped", "cap": 2000,
                     "changed": [1], "kept": []},
        trim={"trimmed": True, "reason": "", "rss_before": 700.0,
              "rss_after": 640.5, "reclaimed_mb": 59.5},
    )
    text = "\n".join(lines)
    checks.append("\n".join(lines))
    if not all(line.startswith("[report]") for line in lines):
        errors.append("not every line is tagged [report]: %r" % (lines,))
    if "2000" not in text:
        errors.append("the [report] lines do not say what the cap is: %r" % text)
    if "Report View" not in text:
        errors.append("the [report] lines do not name the Report View")
    if "malloc_trim" not in text:
        errors.append("the [report] lines do not mention the trim")

    # The nothing-happened cases must also be reported, not silent.
    for rv, label in (
        ({"status": "no-gui"}, "no-gui"),
        ({"status": "not-found"}, "not-found"),
    ):
        line = silk_reload.describe_memory(report_view=rv)
        checks.append("%s -> %s" % (label, line))
        if not line or not line[0].startswith("[report]"):
            errors.append("status %r produced no [report] line: %r" % (label, line))
    skipped = silk_reload.describe_memory(
        trim={"trimmed": False, "reason": "not glibc (darwin)"})
    checks.append("skipped -> %s" % skipped)
    if "not glibc (darwin)" not in skipped[0]:
        errors.append("a skipped trim did not say why: %r" % (skipped,))
    return _ok(checks, errors)


def test_reload_and_leak_reporting_still_works(doc):
    """The existing [reload] / [leak] lines are untouched by #79."""
    errors = []
    checks = []
    lines = silk_reload.describe({
        "reloaded": True, "reason": "sources changed since the last run",
        "removed_count": 57, "namespace_cleared": ["stale_thing"],
        "orphans": 3,
    })
    text = "\n".join(lines)
    checks.append(text)
    if not any(l.startswith("[reload]") for l in lines):
        errors.append("describe() no longer emits a [reload] line")
    if not any(l.startswith("[leak]") for l in lines):
        errors.append("describe() no longer emits a [leak] line")
    if "[leak] 3 orphaned" not in text:
        errors.append("the [leak] orphan count is gone: %r" % text)
    if "stale_thing" not in text:
        errors.append("the dropped-namespace report is gone: %r" % text)
    return _ok(checks, errors)


def test_the_remote_run_caps_the_report_view_and_trims(doc):
    """run_all.py's remote setup must actually call both.

    Reads run_all.py as text (importing it would run the suite: it calls
    sys.exit(main()) at module level). This is the wiring guard -- the
    helpers can be perfect and still never be called.
    """
    errors = []
    checks = []
    path = os.path.join(MOD_DIR, "Tests", "run_all.py")
    with open(path) as fh:
        source = fh.read()
    remote = source[source.index("_REMOTE_CODE = "):source.index("\ndef _save_inspect_docs")]
    checks.append("remote block is %d chars" % len(remote))
    if "cap_report_view" not in remote:
        errors.append("the remote per-run setup never calls cap_report_view -- "
                      "the Report View stays uncapped in the long-lived GUI")
    if "malloc_trim" not in remote:
        errors.append("the remote per-run setup never calls malloc_trim -- "
                      "freed memory is never returned to the OS")
    # The cap must come BEFORE the suite runs, or the run's own output is
    # what fills the buffer.
    i_cap = remote.find("cap_report_view")
    i_run = remote.find("run_tests")
    i_trim = remote.find("malloc_trim")
    i_clear = remote.find("clear_runner_namespace")
    checks.append("positions: cap=%d run_tests=%d trim=%d clear=%d"
                  % (i_cap, i_run, i_trim, i_clear))
    if i_cap >= 0 and i_run >= 0 and i_cap > i_run:
        errors.append("cap_report_view runs AFTER run_tests -- the suite's own "
                      "output has already filled the buffer by then")
    # ...and the trim AFTER something has been released, which is the
    # whole reason the two are paired (#79: the trim alone reclaimed 6 MB
    # because nothing had been released for it to return).
    if i_trim >= 0 and i_clear >= 0 and i_trim < i_clear:
        errors.append("malloc_trim runs BEFORE the run's references are "
                      "cleared -- there is nothing freed for it to return")
    # The runner must echo the new lines instead of swallowing them.
    if "[report]" not in source[source.index("def _run_via_rpc"):]:
        errors.append("_run_via_rpc does not echo the [report] lines")
    return _ok(checks, errors)


ALL_TESTS = [
    test_report_view_cap_is_applied_to_the_real_report_view,
    test_cap_report_view_takes_an_uncapped_widget_to_the_cap,
    test_cap_report_view_never_raises_a_smaller_existing_cap,
    test_cap_report_view_is_a_no_op_without_a_report_view,
    test_malloc_trim_runs_on_glibc_and_reports_what_it_did,
    test_malloc_trim_is_a_no_op_off_glibc_or_without_the_symbol,
    test_memory_lines_name_the_cap_and_the_trim,
    test_reload_and_leak_reporting_still_works,
    test_the_remote_run_caps_the_report_view_and_trims,
]