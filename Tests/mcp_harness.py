"""
Test harness for agent-driven testing via FreeCAD MCP.

The agent sends test functions via MCP execute_code.
Each test returns a dict {"pass": bool, "errors": [str, ...], "checks": [...]}.
The harness collects results and prints a JSON summary line the agent can parse.
"""

import FreeCAD
import json
import os
import sys
import time

# ---- run progress, so a CLIENT can see a stall and name the test ------
#
# Why this exists: the runner used to block silently on one long RPC call.
# A wedged FreeCAD looked exactly like a slow suite, so both were waited out
# (this project lost ~4 minutes to an O(n^2) probe and ~5 to a run started by
# accident, both times by "waiting it out"). The client cannot ask the server
# anything while the server is busy -- it is single-threaded on the GUI
# thread -- so the server has to TELL it, out of band, before it blocks.
#
# The record is written atomically (tmp + os.replace) so a reader can never
# catch it half-written and think the run advanced when it did not.
PROGRESS_FILE = os.environ.get("SILK_PROGRESS_FILE", "/tmp/silk_progress.json")


def write_progress(phase, name="", index=None, total=None):
    """Record what the remote side is doing RIGHT NOW, for the client's
    stall watchdog. Best effort: never let progress reporting fail a run."""
    try:
        rec = {"phase": phase, "name": name, "index": index, "total": total,
               "pid": os.getpid(), "t": time.time()}
        tmp = PROGRESS_FILE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(rec, fh)
        os.replace(tmp, PROGRESS_FILE)
    except Exception:
        pass


def _quiet_dialog(label, msg):
    FreeCAD.Console.PrintMessage(
        "[test] dialog suppressed: %s - %s\n" % (label, msg)
    )


def _patch_dialogs():
    """Swap the modal popup.tipsDialog for a console stub for the duration
    of a test run, so unattended runs never block on a popup.
    Returns the (module, original) pairs to restore."""
    try:
        import popup
    except ImportError:
        return []
    orig = getattr(popup, "tipsDialog", None)
    if orig is None:
        return []
    saved = []
    for mod in list(sys.modules.values()):
        if mod is None:
            continue
        if getattr(mod, "tipsDialog", None) is orig:
            saved.append((mod, orig))
            mod.tipsDialog = _quiet_dialog
    return saved


def _restore_dialogs(saved):
    for mod, orig in saved:
        mod.tipsDialog = orig


def run_tests(*test_funcs, verbose=True, close_docs=True):
    """Run test functions, return JSON summary.

    Each test_func must accept a document and return a dict:
        {"pass": bool, "errors": [str, ...], "checks": [...]}

    close_docs=False leaves each test's document open (stage-2 visual
    inspection) and prints the list of open documents at the end.

    Prints a single JSON line "RESULT:<json>" at the end for agent parsing.

    Each test is TIMED, and the slowest are reported at the end (#72).
    "The suite is slow" is otherwise unanswerable without a module-level
    guess, and the guess was wrong: the reload machinery everyone
    suspected cost 4.6s, while a four-test module cost 22s.

    #72: this frame can outlive the run -- FreeCAD keeps the traceback of
    an exception raised inside a document-closing slot, and a traceback
    keeps every frame. A retained run_tests frame holds test_funcs (so
    the whole Tests module generation) and _patch_dialogs' `saved` list
    of (module, popup.tipsDialog) pairs, which pins every Silk module it
    ran against. Purging sys.modules cannot free any of that, which is
    how whole module generations stayed alive as orphans. Dropping the
    references when the work is done costs nothing and keeps the
    generation collectable no matter who holds the frame.
    """
    results = []
    open_docs = []
    timings = []
    saved = _patch_dialogs()
    func = doc = outcome = None
    try:
        for _i, func in enumerate(test_funcs):
            doc = None
            _t0 = time.time()
            # Announce BEFORE the test runs, flushed: a test that wedges
            # must still be attributable, and an unflushed print that sits
            # in a buffer tells the client nothing.
            write_progress("running", func.__name__, _i + 1, len(test_funcs))
            print("  [..] %d/%d %s" % (_i + 1, len(test_funcs), func.__name__),
                  flush=True)
            try:
                doc_name = "_mcp_test_" + func.__name__
                doc = FreeCAD.newDocument(doc_name)
                outcome = func(doc)
                if not isinstance(outcome, dict):
                    outcome = {"pass": False, "errors": ["Test returned non-dict: " + str(type(outcome))], "checks": []}
                else:
                    outcome.setdefault("checks", [])
                    outcome.setdefault("errors", [])
                outcome["name"] = func.__name__
                results.append(outcome)
            except Exception as e:
                import traceback
                results.append({
                    "name": func.__name__,
                    "pass": False,
                    "errors": [str(e)],
                    "checks": [],
                    "traceback": traceback.format_exc()
                })
            finally:
                write_progress("done", func.__name__, _i + 1, len(test_funcs))
                timings.append((func.__name__, time.time() - _t0))
                if doc is not None:
                    if close_docs:
                        try:
                            FreeCAD.closeDocument(doc.Name)
                        except Exception:
                            pass
                    else:
                        try:
                            open_docs.append(doc.Name)
                        except Exception:
                            pass  # the test closed its own document
    finally:
        try:
            _restore_dialogs(saved)
        finally:
            # Nothing below may reference the modules this run loaded.
            saved = None
            func = None
            doc = None
            outcome = None
            test_funcs = ()
            del saved, func, doc, outcome, test_funcs

    passed = sum(1 for r in results if r.get("pass"))
    failed = len(results) - passed

    summary = {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
        # names + seconds only: no module references, so this cannot pin a
        # generation the way a traceback frame does (#72).
        "timings": [{"name": n, "seconds": round(s, 3)} for n, s in timings],
    }

    if verbose:
        for r in results:
            status = "PASS" if r.get("pass") else "FAIL"
            print(f"  [{status}] {r['name']}")
            for err in r.get("errors", []):
                print(f"    ERROR: {err}")

        print(f"\n{passed}/{len(results)} passed, {failed} failed")

        # Slowest tests, so "the suite is slow" has an answer (#72).
        # Module totals were the wrong unit: a 7-test module everyone
        # suspected cost 4.6s, and a 4-test module nobody suspected cost
        # 22s. Per test is where the cost actually is.
        ranked = sorted(timings, key=lambda kv: -kv[1])
        total_s = sum(s for _, s in timings)
        if ranked and total_s >= 5.0:
            top = [t for t in ranked[:10] if t[1] >= 0.2]
            if top:
                print("\n[slowest] (total %.1fs across %d tests)"
                      % (total_s, len(timings)))
                for name, secs in top:
                    print("   %6.2fs  %s" % (secs, name))
                share = sum(s for _, s in top) / total_s * 100
                print("   -> these %d tests are %.0f%% of the run"
                      % (len(top), share))

        if not close_docs:
            print("\n[inspect] documents left open for manual inspection:")
            if open_docs:
                for n in open_docs:
                    print("  - " + n)
            else:
                print("  (none)")

    # Machine-parseable line
    print("RESULT:" + json.dumps(summary))
    return summary
