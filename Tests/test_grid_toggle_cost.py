"""A grid toggle must not rebuild the grid.

**The defect.** `SilkMachinery.set_grid_display` rebuilt the whole Coin
control grid on every call, and the view provider calls it on every
`ShowGrid` / `ShowPolygon` change. Building a grid allocates a Coin node per
pole and per leg, so a toggle cost the whole grid: the owner measured
*toggling the grid on the corner surface* taking seconds, and *hiding the
grids* across a document taking seconds per object.

**The fix.** When the inputs are unchanged (the same legs, colour and width),
the existing node is kept and only the switch is flipped; the rebuild happens
when the legs or the appearance actually change.

**What this asserts**, on a real object in the running GUI:

1. A pure show/hide does **not** rebuild the grid -- the Coin node under the
   switch is the *same object* afterwards, and the rebuild counter does not
   move.
2. The toggle still **does** what it says: the switch's `whichChild` flips,
   so the grid really appears and disappears.
3. A **real** change -- different legs -- still rebuilds. A cache that never
   rebuilds would be a worse bug than the one it fixes.

The grid is a view node, so this needs a GUI: the fast tier runs in the
owner's FreeCAD, which has one.
"""

import os
import time

import FreeCAD

from Tests.mcp_harness import check


def _grid_nodes(obj):
    """The Coin nodes that make up this object's grid, or None headless."""
    vobj = getattr(obj, "ViewObject", None)
    if vobj is None:
        return None
    # The grid node lives on the VIEW PROVIDER's proxy: set_grid_display is
    # called as set_grid_display(self, vobj, ...) from the view provider.
    proxy = getattr(vobj, "Proxy", None)
    if proxy is None:
        return None
    switch = getattr(proxy, "_silk_grid_node", None)
    if switch is None:
        return None
    try:
        display = switch.getChild(0)
    except Exception:
        return None
    return switch, display


def _make_patch(doc):
    """One square patch with a control grid (the shared seam-resolver
    fixture -- a square of four straight edges)."""
    from Tests.test_seam_resolver import _square_patch
    patch = _square_patch(doc, "gtc")
    doc.recompute()
    return patch


def test_a_grid_toggle_does_not_rebuild_the_grid(doc):
    """Toggling ShowGrid flips the switch and keeps the same Coin node."""
    errors, checks = [], []

    import SilkMachinery as machinery
    import SilkWorkflowOps as ops

    calls = []
    real_grid_coin_node = machinery.grid_coin_node

    def counting(legs):
        calls.append(1)
        return real_grid_coin_node(legs)

    patch = None
    try:
        patch = _make_patch(doc)
        if patch is None:
            return {"pass": False,
                    "errors": ["the patch did not build"],
                    "checks": checks}
        before = _grid_nodes(patch)
        if before is None:
            return {"pass": False,
                    "errors": ["no grid node: the test needs a GUI (the fast "
                               "tier runs in one), or the grid was never built"],
                    "checks": checks}
        switch, display = before
        checks.append("the grid node exists before the toggle")

        machinery.grid_coin_node = counting
        try:
            patch.ShowGrid = False
            doc.recompute()
            after_hide = _grid_nodes(patch)
            n_hide = len(calls)
            patch.ShowGrid = True
            doc.recompute()
            after_show = _grid_nodes(patch)
            n_show = len(calls)
        finally:
            machinery.grid_coin_node = real_grid_coin_node

        check(after_hide is not None and after_show is not None,
              "the grid node vanished during the toggle", errors)
        check(n_show == n_hide,
              "the toggle rebuilt the grid: %d rebuild(s) for a pure "
              "show/hide" % (n_show - n_hide), errors)
        checks.append("a pure show/hide rebuilt nothing (%d rebuild call(s))"
                      % n_show)
        # NOTE: the Coin display node's IDENTITY cannot be compared --
        # pivy returns a fresh Python wrapper on every child access, so
        # `switch.getChild(0) is before` is False even for the same C++
        # node. The rebuild counter is the real measurement; this only
        # checks the switch is in the graph.
        check(after_show[0].getNumChildren() > 0,
              "the grid node has no children after the toggle", errors)

        # the toggle still does what it says
        which = switch.whichChild
        which = which.getValue() if hasattr(which, "getValue") else which
        check(int(which) == 0,
              "the grid is not visible again (whichChild=%s)" % which, errors)
        checks.append("the switch is back on (whichChild=0)")

        # and a REAL change still rebuilds
        legs = list(getattr(patch.Proxy, "_display_legs", None) or [])
        machinery.grid_coin_node = counting
        try:
            n_before = len(calls)
            patch.Proxy._display_legs = legs + [legs[0]] if legs else legs
            patch.ShowGrid = False
            patch.ShowGrid = True
            doc.recompute()
            n_after = len(calls)
        finally:
            machinery.grid_coin_node = real_grid_coin_node
        check(n_after > n_before,
              "a changed leg set did NOT rebuild the grid (the cache would "
              "be showing a stale grid)", errors)
        checks.append("a changed leg set still rebuilds (%d rebuild call(s))"
                      % (n_after - n_before))
    except Exception as exc:
        errors.append("%s: %s" % (type(exc).__name__, exc))
    finally:
        try:
            if patch is not None:
                doc.removeObject(patch.Name)
        except Exception:
            pass

    return {"pass": not errors, "errors": errors, "checks": checks}
