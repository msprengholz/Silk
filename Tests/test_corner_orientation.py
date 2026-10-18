"""Corner orientation robustness (#107): a 3-valent junction fills whatever
parameterization the faces and blends were built with.

The owner built the Demo 01 shape by hand in the wizard and EVERY one of its
four junctions refused:

    Silk: cannot create a corner blend from these 3 blends -- blend Blend003:
    its two patches disagree about which end is the junction (twisted input).
    Nothing was created.

The ring was not broken: the same three seams build green from
`Tests/demo01_fixture_model.py`'s documented order on
`SketchOnly_Demo01Subset.FCStd`. The refusal was order-dependent, and it came
from two assumptions in `SilkCorner.corner_inputs` that hold only for the
fixture's own parameterization:

  * a patch that parameterizes a shared seam the other way round (its stored
    edge cycle rotated) names the SAME junction at the MIRRORED row of its
    seam-parallel axis, and the junction-end agreement was compared RAW -- so
    a legitimately reversed seam read as "twisted input";
  * a strip's 6-pole axis puts whichever patch was handed `create_blend`
    FIRST at column 0, but `corner_grid` reads the ring's shared corner from
    a fixed column, so a ring whose blends do not run as a directed cycle
    (PatchB of one strip IS PatchA of the next) could not assemble.

Both are fixed in `SilkCorner`; both are no-ops on the documented fixture, so
the legacy pole parity is untouched (`Tests/test_corner_blend.py`'s
`test_corner_blend_pole_parity_with_legacy_chain` and the `test_chain.py`
ground truth keep running unchanged).

No continuity label is asserted anywhere in this module.
"""

# --- manual tier ------------------------------------------------------
# This module's subject is an end-to-end rebuild / GUI drive /
# measurement sweep, so it is NOT in the default (fast) tier. Run it
# with `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable. See suite.py.
MANUAL = True

import itertools
import os

import FreeCAD

import SilkChecks
import SilkWorkflowOps as OPS
import Tests.demo01_fixture_model as MODEL

_SILK_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNER_PATH = os.path.join(_SILK_DIR, "Resources", "Test_files",
                          "SketchOnly_Demo01Subset_withPatches.FCStd")


class CaptureConsole:
    """Capture the corner-stage refusal text for one block."""

    def __enter__(self):
        self._orig = FreeCAD.Console.PrintError
        self.errors = []
        FreeCAD.Console.PrintError = lambda msg: (
            self.errors.append(msg), self._orig(msg))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig


def _failed(results):
    return [(n, d) for (n, ok, d) in results if not ok]


def _report(lines):
    for line in lines:
        print("[orientation] %s" % line)


# ---- finding the rings ---------------------------------------------------

def _triangle_rings(doc):
    """The 3-blend rings of `doc`: one per PATCH triple that shares a seam
    pairwise (that is exactly a 3-valent junction).  Returns a list of
    (label, [3 blends]); the label is the sorted patch-name triple, so the
    test never depends on the blend objects' auto-generated names."""
    patches = [o for o in doc.Objects
               if getattr(o, "object_type", None) == "Patch"]
    by_pair = {}
    for entry in OPS.seam_inventory(doc):
        if entry["blend"] is not None:
            by_pair[frozenset((id(entry["patch_a"]),
                               id(entry["patch_b"])))] = entry["blend"]
    rings = []
    for a, b, c in itertools.combinations(patches, 3):
        keys = [frozenset((id(x), id(y))) for x, y in ((a, b), (a, c), (b, c))]
        if all(k in by_pair for k in keys):
            rings.append((tuple(sorted((a.Name, b.Name, c.Name))),
                          [by_pair[k] for k in keys]))
    return rings


def _fill_and_check(doc, ring, corner_name):
    """create_corner_blend over `ring` -> (corner, problems, check_line)."""
    with CaptureConsole() as cap:
        corner = OPS.create_corner_blend(ring, name=corner_name)
    if corner is None:
        return None, ["refused: %s" % " ".join(cap.errors).strip()], None
    problems = []
    if len(corner.Poles or []) != 36:
        problems.append("%d poles, want 36" % len(corner.Poles or []))
    if not corner.Shape or corner.Shape.isNull():
        problems.append("null Shape")
    else:
        if len(corner.Shape.Faces) < 1:
            problems.append("no face")
        if not corner.Shape.isValid():
            problems.append("invalid Shape")
    bad = _failed(SilkChecks.check_corner_blend(corner, *list(corner.Strips)))
    if bad:
        problems.append("check_corner_blend: %s" % bad)
    line = ("%-40s 36 poles, %s face(s), valid=%s, oracle=%s"
            % (corner.Name, len(corner.Shape.Faces) if corner.Shape
               and not corner.Shape.isNull() else 0,
               corner.Shape.isValid() if corner.Shape
               and not corner.Shape.isNull() else None,
               "GREEN" if not bad else "RED %s" % bad))
    return corner, problems, line


# ---- 1. the owner's own model: all four rings ----------------------------

def test_owner_model_three_valent_rings_build(doc):
    """The owner's committed model
    (`Resources/Test_files/SketchOnly_Demo01Subset_withPatches.FCStd`, 12
    Edges / 5 Patches / 8 Blends / 0 corners) fills all four 3-valent
    junctions: 36 poles, one valid face, oracle-green, nothing refused.  This
    is the case that must never regress again -- the exact shape that refused
    every ring with "twisted input"."""
    errors, checks, report = [], [], []
    source, opened_dir = MODEL.open_fresh(OWNER_PATH)
    try:
        rings = _triangle_rings(source)
        if len(rings) != 4:
            errors.append("the owner's model has %d three-valent junctions, "
                          "want 4" % len(rings))
        FreeCAD.setActiveDocument(source.Name)
        for i, (label, ring) in enumerate(sorted(rings)):
            corner, problems, line = _fill_and_check(
                source, ring, "CB_owner_%d" % (i + 1))
            if problems:
                errors.append("owner ring %s: %s"
                              % ("+".join(label), "; ".join(problems)))
            else:
                checks.append("owner ring %s -> %s" % ("+".join(label),
                                                       line.strip()))
            if line:
                report.append("owner ring %-34s %s"
                              % ("+".join(label), line.split(None, 1)[1]))
    finally:
        FreeCAD.setActiveDocument(doc.Name)
        MODEL.close_fresh(source, opened_dir)
    if not errors:
        checks.append("all 4 owner junctions filled: 36 poles, valid, "
                      "oracle-green")
    _report(report)
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---- 2. the minimal reproduction: one face's cycle rotated ----------------

def _build_fixture(doc, source):
    """Build the documented fixture into `doc` from an already-open
    `source` (the sketch-only fixture): 12 Edges, 5 Patches and 8 Blends in
    the documented order, NO corners.  Returns (edges, patches, blends).

    #116: the two sweeps build this ONCE and then move the one parameter
    they vary, in place.  Building it again per iteration cost ~25 s an
    iteration (20 objects, each with a full-document recompute) for a
    model whose every other object is byte-identical to the baseline.
    """
    FreeCAD.setActiveDocument(doc.Name)
    for name in MODEL.used_sketch_names():
        MODEL._copy_sketch(doc, source, name)
    doc.recompute()
    edges = {}
    for name, sketches, _legacy in MODEL.EDGES:
        edges[name] = OPS.create_edge(
            [doc.getObject(s) for s in sketches], name=name)
    patches = {}
    for name, order, _grid in MODEL.PATCHES:
        patches[name] = OPS.create_patch([edges[k] for k in order],
                                         name=name)
    blends = {}
    for name, pa, pb, _edge in MODEL.BLENDS:
        blends[name] = OPS.create_blend(patches[pa], patches[pb], name=name)
    return edges, patches, blends


# The documented click order per patch, so a sweep can put the cycle back.
_PATCH_ORDER = {name: tuple(order) for name, order, _grid in MODEL.PATCHES}


def _set_cycle(doc, patch, order):
    """Write `order` (edge objects, in order) onto `patch.Edges` and settle
    it.

    `Edges` is a link list, not one of the recompute-trigger properties
    (onChanged watches the split lists and the display toggles), so the
    write needs the explicit touch a data-tab edit needs (#67).  The fill
    re-derives from the stored list on that recompute, so this is the same
    patch `create_patch([...that order])` builds -- `patch.Edges[k]` is
    boundary side k either way (#66/#67).
    """
    patch.Edges = list(order)
    patch.touch()
    doc.recompute()


def _swap_pair(doc, blend):
    """Hand `blend` its two patches in the other order.

    `run_blend` reads `PatchA`/`PatchB` and re-derives the seam from them
    on every execute, so this is the strip `create_blend(pb, pa)` builds --
    reversed columns, same seam.  The write itself recomputes the strip
    (onChanged watches `Patch*`); the explicit recompute settles the rest
    of the chain.
    """
    a, b = blend.PatchA, blend.PatchB
    blend.PatchA = b
    blend.PatchB = a
    doc.recompute()


def _strip_corners(doc):
    """Drop every CornerBlend in `doc`.

    Each iteration must fill a junction that has NO corner yet: a second
    ask for a junction that already has one is an idempotent no-op, so a
    leftover corner would make the next iteration assert nothing.
    """
    for obj in [o for o in doc.Objects
                if getattr(o, "object_type", "") == "CornerBlend"]:
        doc.removeObject(obj.Name)


# Which patches a ring's seams belong to, from the documented tables (no
# second list to keep in step).
def _ring_patches(ring):
    patches = set()
    for name, pa, pb, _edge in MODEL.BLENDS:
        if name in ring:
            patches.update((pa, pb))
    return patches


_RING_PATCHES = {name: _ring_patches(ring)
                 for name, ring, _point in MODEL.CORNERS}


def _corners_touched(rotate=(), swap=()):
    """The junctions a mutation can reach.

    A face's cycle rotation only reparameterizes that face, and a blend's
    swapped pair order only reverses that strip, so a junction whose ring
    touches NEITHER is built from byte-identical inputs and cannot change
    -- filling it again would re-assert the unmutated baseline, not the
    mutation.  Each case fills exactly the junctions it moves.
    """
    out = []
    for name, ring, point in MODEL.CORNERS:
        if (_RING_PATCHES[name] & set(rotate)) or (set(ring) & set(swap)):
            out.append((name, ring, point))
    return out


def _assert_junctions_build(doc, blends, corners):
    errors, checks = [], []
    for name, ring, _point in corners:
        strips = [blends[b] for b in ring]
        corner, problems, line = _fill_and_check(doc, strips, name)
        if problems:
            errors.append("corner %s: %s" % (name, "; ".join(problems)))
        else:
            checks.append("%s %s" % (name, line.strip()))
    return errors, checks


def test_rotated_patch_cycle_still_fills_every_junction(doc):
    """Rotating ONE face's stored edge cycle by one edge flips the direction
    of the two seams on that face -- the parameterization the owner's hand
    build produced.  Before #107 that made the two affected junctions refuse
    with "twisted input" (`li_map` compared raw); now every junction the
    rotated face touches fills, and the fill is the same one the documented
    order gives.

    #116: ONE fixture build for the whole sweep.  Each iteration rotates
    one face's stored cycle in place -- the data-tab path, an `Edges` write
    plus a touch, from which the fill re-derives -- and puts it back
    afterwards.  Nothing else in the model differs from the baseline.
    """
    errors, checks, report = [], [], []
    source, opened_dir = MODEL.open_fresh(MODEL.FIXTURE_PATH)
    sub = FreeCAD.newDocument("_rotate_sweep")
    try:
        FreeCAD.setActiveDocument(sub.Name)
        edges, patches, blends = _build_fixture(sub, source)
        for rotated in ("P_Right", "P_Top", "P_Front", "P_Bottom",
                        "P_Back"):
            order = _PATCH_ORDER[rotated]
            _set_cycle(sub, patches[rotated],
                       [edges[k] for k in order[1:] + order[:1]])
            touched = _corners_touched(rotate=(rotated,))
            errs, _chks = _assert_junctions_build(sub, blends, touched)
            errors.extend("%s rotated: %s" % (rotated, e) for e in errs)
            if not errs:
                checks.append("cycle of %s rotated one edge: all %d "
                              "junctions it touches fill (36 poles, "
                              "valid, oracle-green)"
                              % (rotated, len(touched)))
                report.append("rotated %s -> %d/%d corners"
                              % (rotated, len(touched), len(touched)))
            _strip_corners(sub)
            _set_cycle(sub, patches[rotated], [edges[k] for k in order])
    finally:
        FreeCAD.closeDocument(sub.Name)
        FreeCAD.setActiveDocument(doc.Name)
        MODEL.close_fresh(source, opened_dir)
    _report(report)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_swapped_blend_direction_still_fills_every_junction(doc):
    """Handing `create_blend` the two patches in the other order reverses the
    strip's column orientation (PatchA's outer sits at column 0).  Before
    #107 a ring whose blends did not run as a directed cycle could not
    assemble ("could not build triangular 4th member"); now every junction
    the reversed strip belongs to fills.

    #116: ONE fixture build for the whole sweep.  Each iteration hands one
    strip its two patches in the other order (the toolbar's selection
    order, reversed) and puts it back afterwards.  Nothing else in the
    model differs from the baseline.
    """
    errors, checks, report = [], [], []
    source, opened_dir = MODEL.open_fresh(MODEL.FIXTURE_PATH)
    sub = FreeCAD.newDocument("_swap_sweep")
    try:
        FreeCAD.setActiveDocument(sub.Name)
        _edges, _patches, blends = _build_fixture(sub, source)
        for swapped, _pa, _pb, _e in MODEL.BLENDS:
            _swap_pair(sub, blends[swapped])
            touched = _corners_touched(swap=(swapped,))
            errs, _chks = _assert_junctions_build(sub, blends, touched)
            errors.extend("%s swapped: %s" % (swapped, e) for e in errs)
            if not errs:
                checks.append("blend %s reversed: all %d junctions it "
                              "belongs to fill (36 poles, valid, "
                              "oracle-green)" % (swapped, len(touched)))
                report.append("swapped %s -> %d corners"
                              % (swapped, len(touched)))
            _strip_corners(sub)
            _swap_pair(sub, blends[swapped])
    finally:
        FreeCAD.closeDocument(sub.Name)
        FreeCAD.setActiveDocument(doc.Name)
        MODEL.close_fresh(source, opened_dir)
    _report(report)
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_owner_model_three_valent_rings_build,
    test_rotated_patch_cycle_still_fills_every_junction,
    test_swapped_blend_direction_still_fills_every_junction,
]
