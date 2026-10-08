"""
Test harness for agent-driven testing via FreeCAD MCP.

The agent sends test functions via MCP execute_code.
Each test returns a dict {"pass": bool, "errors": [str, ...], "checks": [...]}.
The harness collects results and prints a JSON summary line the agent can parse.
"""

import FreeCAD
import json
import sys


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


def run_tests(*test_funcs, verbose=True):
    """Run test functions, return JSON summary.

    Each test_func must accept a document and return a dict:
        {"pass": bool, "errors": [str, ...], "checks": [...]}

    Prints a single JSON line "RESULT:<json>" at the end for agent parsing.
    """
    results = []
    saved = _patch_dialogs()
    try:
        for func in test_funcs:
            doc = None
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
                if doc is not None:
                    try:
                        FreeCAD.closeDocument(doc.Name)
                    except Exception:
                        pass
    finally:
        _restore_dialogs(saved)

    passed = sum(1 for r in results if r.get("pass"))
    failed = len(results) - passed

    summary = {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": results
    }

    if verbose:
        for r in results:
            status = "PASS" if r.get("pass") else "FAIL"
            print(f"  [{status}] {r['name']}")
            for err in r.get("errors", []):
                print(f"    ERROR: {err}")

        print(f"\n{passed}/{len(results)} passed, {failed} failed")

    # Machine-parseable line
    print("RESULT:" + json.dumps(summary))
    return summary
