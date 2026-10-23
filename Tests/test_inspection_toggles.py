"""
The inspection row in the workflow panel (#95, part B).

Two toggles, not one -- the owner's settled answer (#95 Q1): "controlgrids
are most seldomly needed, and would be off most of the time. edges, however
are needed to change the design. so we need two toggles." A row of buttons
in the wizard panel (Q2), each a checkable button whose pressed state means
HIDDEN and whose release is the UNIFORM restore (Q4): everything of that
kind comes back visible rather than replaying what was visible before.

  * `Hide edges` hides every Edge, and through the Edge's OWN visibility
    cascade (#110 `EdgeViewProvider._mirror_sketch_visibility`) the
    sketches that Edge claims. A sketch no Edge claims is NOT touched --
    Q3: "it hides only edges and their associated sketches, not all
    sketches", which in the owner's Demo 01 model leaves 17 of 33
    sketches visible.
  * `Hide grids` hides every control grid / control polygon: the Coin node
    each Silk object draws from its `Legs` (#108) -- `ShowGrid` on a
    Patch / Blend / CornerBlend and `ShowPolygon` on an Edge.

The per-Edge cascade is not re-implemented: the button is its global form,
so exactly one place decides what an Edge hides.

No continuity label is asserted anywhere in this module.
"""

# --- manual tier ------------------------------------------------------
# A GUI drive: it flips the panel's inspection toggles and reads the
# visibility of real view objects.
# So this module is NOT in the default (fast) tier. Run it with
# `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable and keeps tests.
MANUAL = True


import FreeCAD
from FreeCAD import Gui

from Tests.mcp_harness import check


def _visible(obj):
    vobj = getattr(obj, "ViewObject", None)
    if vobj is None:
        return None
    try:
        return bool(vobj.Visibility)
    except Exception:
        return None


def _which_child(obj):
    """The Coin grid switch's whichChild, or None when there is no node."""
    vobj = getattr(obj, "ViewObject", None)
    proxy = getattr(vobj, "Proxy", None) if vobj is not None else None
    node = getattr(proxy, "_silk_grid_node", None)
    return None if node is None else node.whichChild.getValue()


def _fixture(doc):
    """Two quad patches sharing one Edge, blended, plus a sketch no Edge
    claims. Returns (pa, pb, blend, claimed_sketches, loose)."""
    from SilkWorkflowOps import create_blend_by_edge
    from Tests.test_patch_touched import _build_two_patch_pair
    from Tests.test_seam_resolver import _line_sketch

    pa, pb, seam = _build_two_patch_pair(doc)
    blend = create_blend_by_edge(seam, name="Blend")
    doc.recompute()
    claimed = []
    for o in doc.Objects:
        if getattr(o, "object_type", None) == "Edge":
            for sk in list(getattr(o, "Sketches", None) or []):
                if not any(sk is c for c in claimed):
                    claimed.append(sk)
    loose = _line_sketch(doc, "Loose", [(200, 0, 0), (216.7, 0, 0),
                                        (233.3, 0, 0), (250, 0, 0)])
    doc.recompute()
    return pa, pb, blend, claimed, loose


def test_panel_has_two_inspection_toggles(doc):
    """The row exists, in the panel, as TWO separate checkable buttons --
    and it is a row of the wizard panel, not a toolbar command (#95 Q2)."""
    errors, checks = [], []
    from SilkTaskPanel import (HIDE_EDGES_TEXT, HIDE_GRIDS_TEXT,
                               SilkTaskPanel)
    from Tests.test_task_panel import _open_panel, _close_panel

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        for attr in ("hide_edges_btn", "hide_grids_btn"):
            check(hasattr(panel, attr),
                  "the panel has no %s -- the inspection row is missing"
                  % attr, errors)
        if errors:
            return {"pass": False, "errors": errors, "checks": checks}
        check(panel.hide_edges_btn.text() == HIDE_EDGES_TEXT,
              "the edges toggle reads %r, want %r"
              % (panel.hide_edges_btn.text(), HIDE_EDGES_TEXT), errors)
        check(panel.hide_grids_btn.text() == HIDE_GRIDS_TEXT,
              "the grids toggle reads %r, want %r"
              % (panel.hide_grids_btn.text(), HIDE_GRIDS_TEXT), errors)
        for btn, name in ((panel.hide_edges_btn, "edges"),
                          (panel.hide_grids_btn, "grids")):
            check(btn.isCheckable(),
                  "the %s toggle is not checkable -- it cannot be a toggle"
                  % name, errors)
            check(not btn.isChecked(),
                  "the %s toggle starts pressed (hidden)" % name, errors)
            check(bool(btn.toolTip()),
                  "the %s toggle has no tooltip saying what it covers"
                  % name, errors)
        check(panel.hide_edges_btn is not panel.hide_grids_btn,
              "the two toggles are the SAME button -- Q1 asks for two",
              errors)
        check(panel.inspection_row is panel.hide_edges_btn.parentWidget(),
              "the toggles are not in the panel's inspection row", errors)
        checks.append("panel carries two checkable buttons (%r / %r), both "
                      "starting unpressed, each with a tooltip"
                      % (panel.hide_edges_btn.text(),
                         panel.hide_grids_btn.text()))
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_hide_edges_hides_edges_and_only_their_sketches(doc):
    """#95 Q3: the edges toggle hides every Edge AND the sketches those
    Edges claim -- and leaves a sketch no Edge claims alone. Releasing the
    button restores everything of that kind (Q4)."""
    errors, checks = [], []
    from Tests.test_task_panel import _open_panel, _close_panel

    pa, pb, blend, claimed, loose = _fixture(doc)
    edges = [o for o in doc.Objects
             if getattr(o, "object_type", None) == "Edge"]
    check(len(edges) == 7 and len(claimed) == 7,
          "fixture: %d edges claim %d sketches, want 7 / 7"
          % (len(edges), len(claimed)), errors)
    check(all(_visible(sk) for sk in claimed + [loose]),
          "fixture: something starts hidden", errors)

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.hide_edges_btn.click()
        check(panel.hide_edges_btn.isChecked(),
              "clicking the edges toggle did not press it", errors)
        hidden_edges = [o.Name for o in edges if _visible(o)]
        check(not hidden_edges,
              "the edges toggle left %s visible" % hidden_edges, errors)
        shown_sketches = [sk.Name for sk in claimed if _visible(sk)]
        check(not shown_sketches,
              "the claimed sketches %s are still visible -- the Edge's own "
              "cascade did not run" % shown_sketches, errors)
        check(_visible(loose) is True,
              "the unclaimed sketch %s was hidden too -- Q3 hides only the "
              "sketches an Edge claims" % loose.Name, errors)
        checks.append("pressed: %d edges hidden, %d claimed sketches hidden "
                      "(through the Edge cascade), unclaimed %s still visible"
                      % (len(edges), len(claimed), loose.Name))

        panel.hide_edges_btn.click()
        check(not panel.hide_edges_btn.isChecked(),
              "clicking again did not release the edges toggle", errors)
        still_hidden = [o.Name for o in edges + claimed if not _visible(o)]
        check(not still_hidden,
              "releasing the edges toggle left %s hidden -- Q4 is a uniform "
              "restore" % still_hidden, errors)
        checks.append("released: every edge and claimed sketch visible again "
                      "(%d + %d)" % (len(edges), len(claimed)))
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_hide_grids_hides_every_control_grid(doc):
    """#95: one toggle for ALL control grids -- the Patch's, the Blend's and
    the Edge's control polygon -- and the Coin nodes really go away, not
    just the properties. Releasing it restores every one (Q4)."""
    errors, checks = [], []
    from Tests.test_task_panel import _open_panel, _close_panel

    pa, pb, blend, claimed, loose = _fixture(doc)
    doc.recompute()
    targets = [o for o in doc.Objects
               if getattr(o, "object_type", None)
               in ("Patch", "Blend", "BlendStrip", "CornerBlend")]
    edges = [o for o in doc.Objects
             if getattr(o, "object_type", None) == "Edge"]
    check(len(targets) == 3 and len(edges) == 7,
          "fixture: %d surface objects / %d edges, want 3 / 7"
          % (len(targets), len(edges)), errors)
    for o in targets + edges:
        check(_which_child(o) == 0,
              "fixture: %s has no shown grid node (whichChild=%r)"
              % (o.Name, _which_child(o)), errors)

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.hide_grids_btn.click()
        off = [o.Name for o in targets + edges if _which_child(o) != -1]
        check(not off,
              "the grids toggle left these grids drawn: %s" % off, errors)
        still_on = [o.Name for o in targets if o.ShowGrid]
        check(not still_on,
              "the grids toggle left ShowGrid on for %s" % still_on, errors)
        polys = [o.Name for o in edges if o.ShowPolygon]
        check(not polys,
              "the grids toggle left the Edge control polygons on for %s"
              % polys, errors)
        checks.append("pressed: %d surface grids + %d edge polygons hidden, "
                      "every Coin node at whichChild=-1"
                      % (len(targets), len(edges)))

        panel.hide_grids_btn.click()
        on = [o.Name for o in targets + edges if _which_child(o) != 0]
        check(not on,
              "releasing the grids toggle left these grids hidden: %s -- Q4 "
              "is a uniform restore" % on, errors)
        checks.append("released: every grid and polygon drawn again")
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_two_toggles_are_independent(doc):
    """Q1's whole point: edges are needed to change the design while grids
    are rarely wanted, so pressing one must not move the other."""
    errors, checks = [], []
    from Tests.test_task_panel import _open_panel, _close_panel

    pa, pb, blend, claimed, loose = _fixture(doc)
    edges = [o for o in doc.Objects
             if getattr(o, "object_type", None) == "Edge"]

    panel = _open_panel(doc)
    if not check(panel is not None, "Activated left no panel open", errors):
        return {"pass": False, "errors": errors, "checks": checks}
    try:
        panel.hide_edges_btn.click()
        check(all(_visible(o) is False for o in edges),
              "fixture: the edges did not hide", errors)
        check(all(o.ShowGrid for o in (pa, pb)) and blend.ShowGrid,
              "hiding the EDGES also turned the grids off -- one toggle is "
              "doing the other's job (Q1)", errors)
        check(all(_which_child(o) == 0 for o in (pa, pb, blend)),
              "hiding the EDGES hid the patches'/blend's grid NODES",
              errors)

        panel.hide_grids_btn.click()
        check(panel.hide_edges_btn.isChecked(),
              "pressing the grids toggle released the edges toggle", errors)
        check(all(_visible(o) is False for o in edges),
              "pressing the grids toggle showed the edges again", errors)
        checks.append("edges hidden + grids off: the edges stay hidden and "
                      "the grids stay on until their own button is pressed")
    finally:
        _close_panel(panel)
        Gui.Selection.clearSelection()
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_panel_has_two_inspection_toggles,
    test_hide_edges_hides_edges_and_only_their_sketches,
    test_hide_grids_hides_every_control_grid,
    test_the_two_toggles_are_independent,
]
