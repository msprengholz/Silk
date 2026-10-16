"""3-valent hard-corner fixture (cube corner): build contract + refusal record.

`Tests/cube_corner_model.py` builds three planar patches meeting at the
shared origin exactly like a cube corner, joined by three Blend strips
built as the directed cycle A -> B -> C -> A. This module drives the
3-valent CornerBlend ops path (`create_corner_blend` with THREE strips)
on that fixture, which until now no test exercised.

MEASURED STATE (2eda11a, recorded honestly, not a target): the fixture
itself is oracle-green (3 patches pass `check_patch`, 3 strips pass
`check_blend`), the three strips resolve as the 3-cycle ring
`corner_ring_3` requires, and the corner build is REFUSED by name before
anything is constructed:

    Silk: cannot create a corner blend from these 3 blends -- could not
    build triangular 4th member. Nothing was created.

so no CornerBlend object exists and no k_gap measurement is possible (the
g2/continuity instrument needs a corner surface to measure; see
`test_3valent_cornerblend_measurement_unavailable` in
Tests/test_corner_blend_triangular.py). The triangular-member input search
feeds each patch's full 4x4 base control net (`SilkCorner.corner_inputs`
-> `SilkMachinery.control_grid64_3_1`), whose four corners are the patch
VERTICES -- never the point the ring actually needs, the patch's
corner-CELL outer corner (0.1 off the junction on both seams) -- so every
candidate lands its degenerate row where no neighbouring strip grid has a
corner. That is a property of the triangular-member construction, not of
this fixture; the fixture is the honest, oracle-green trigger for it.

`test_3valent_cube_corner_builds_green` therefore asserts the CURRENT
refusal contract (no object created, named console message) instead of
faking the positive assertions. When the triangular member is fixed, this
test MUST fail and be rewritten to the positive contract it documents in
its docstring: 36 poles, 1+ faces, non-empty shape, idempotent second ask.
"""

import FreeCAD

import SilkChecks
import Tests.cube_corner_model as ccm
from SilkMachinery import corner_ring_3
from SilkWorkflowOps import create_corner_blend

STRIP_NAMES = ("B_AB", "B_BC", "B_CA")


class _CaptureConsole:
    def __enter__(self):
        self._orig = FreeCAD.Console.PrintError
        self.errors = []
        FreeCAD.Console.PrintError = lambda msg: (
            self.errors.append(msg), self._orig(msg))
        return self

    def __exit__(self, *args):
        FreeCAD.Console.PrintError = self._orig


def _corner_names(doc):
    return [o.Name for o in doc.Objects
            if getattr(o, "object_type", "") == "CornerBlend"]


def _failed(results):
    return [(n, d) for (n, ok, d) in results if not ok]


def test_cube_corner_fixture_is_oracle_green(doc):
    """The fixture itself is sound: every patch passes `check_patch` on its
    OWN stored `Edges` cycle, every strip passes `check_blend`, the three
    strips resolve as the 3-cycle ring the corner op needs, and the three
    patches share the origin corner of the cube. A refusal from the corner
    build is therefore attributable to the triangular member, not to a bad
    fixture."""
    model = ccm.build_cube_corner_model(doc)
    errors, checks = [], []

    for name, p in model["patches"].items():
        bad = _failed(SilkChecks.check_patch(p, list(p.Edges)))
        if bad:
            errors.append("check_patch %s: %s" % (name, bad))
        else:
            checks.append("check_patch %s: GREEN (16 poles, own Edges "
                          "cycle)" % name)

    for name, s in model["strips"].items():
        bad = _failed(SilkChecks.check_blend(s, s.PatchA, s.PatchB))
        if bad:
            errors.append("check_blend %s: %s" % (name, bad))
        else:
            checks.append("check_blend %s: GREEN (24 poles, seam %s|%s)"
                          % (name, s.PatchA.Name, s.PatchB.Name))

    strips = [doc.getObject(n) for n in STRIP_NAMES]
    ordered, why = corner_ring_3(strips)
    if ordered is None:
        errors.append("the three strips do not resolve as a 3-cycle: %s"
                      % why)
    else:
        checks.append("corner_ring_3 orders the fixture: %s"
                      % [s.Name for s in ordered])

    for name, p in model["patches"].items():
        corners = [p.Poles[i] for i in (0, 3, 15, 12)]
        at_origin = min((c - FreeCAD.Vector(0, 0, 0)).Length for c in corners)
        if at_origin > 1e-9:
            errors.append("%s has no corner at the shared origin "
                          "(closest %.3e mm)" % (name, at_origin))
        else:
            checks.append("%s has a corner at the shared origin" % name)

    return {"pass": not errors, "errors": errors, "checks": checks}


def test_3valent_cube_corner_builds_green(doc):
    """`create_corner_blend(B_AB, B_BC, B_CA)` on the cube corner.

    INTENDED CONTRACT (once the triangular 4th member builds): a
    CornerBlend with 36 poles, 1+ faces, a non-empty Shape, and an
    idempotent second ask returning the same object.

    CURRENT MEASURED STATE: the build is refused by name before anything
    is constructed --

        Silk: cannot create a corner blend from these 3 blends -- could
        not build triangular 4th member. Nothing was created.

    This test asserts THAT record (no object created, named message, the
    documented failure stage) and the second ask repeating it. It will
    fail the moment the machinery starts building, which is the signal to
    rewrite it to the intended positive contract above. No continuity
    label is asserted here or anywhere in this suite.
    """
    model = ccm.build_cube_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    errors, checks = [], []

    ok_fixture = (all(len(p.Poles or []) == 16
                      for p in model["patches"].values())
                  and all(len(s.Poles or []) == 24
                          for s in model["strips"].values()))
    if not ok_fixture:
        errors.append("fixture is not 3 x 16-pole patches + 3 x 24-pole "
                      "strips")
    else:
        checks.append("fixture via ops only: 3 patches x 16 poles, "
                      "3 strips x 24 poles")

    before = _corner_names(doc)
    with _CaptureConsole() as cap:
        cb = create_corner_blend(*strips)  # exactly B_AB, B_BC, B_CA
    after = _corner_names(doc)
    msg = "".join(cap.errors).strip()

    if cb is not None or after != before:
        errors.append("expected the recorded refusal (no object), got "
                      "cb=%r CornerBlend objects %s->%s"
                      % (cb, before, after))
    if not (msg and "Silk:" in msg):
        errors.append("refusal is not a named Silk message: %r" % msg)
    else:
        checks.append("corner build refused by name, nothing created: %s"
                      % msg)
    if "triangular 4th member" not in msg:
        errors.append("failure stage changed (recorded stage is 'could not "
                      "build triangular 4th member'): %r" % msg)
    else:
        checks.append("failure stage: triangular 4th member construction")

    # Second ask (reversed order): the positive idempotency contract cannot
    # be exercised without a built corner; what IS observable -- and what
    # this records -- is that the repeat is refused the same way and still
    # leaves no object behind. The 4-valent idempotency contract is covered
    # by Tests/test_corner_blend.py.
    with _CaptureConsole() as cap2:
        cb2 = create_corner_blend(*list(reversed(strips)))
    if cb2 is not None or _corner_names(doc) != before:
        errors.append("second ask was not a no-op refusal: cb2=%r "
                      "CornerBlend objects %s" % (cb2, _corner_names(doc)))
    else:
        checks.append("second ask repeats the refusal; still zero "
                      "CornerBlend objects")

    return {"pass": not errors, "errors": errors, "checks": checks}


def test_3valent_cube_corner_non_ring_refused(doc):
    """A 3-selection that is not a 3-cycle of strips is refused BY NAME and
    leaves no CornerBlend behind (#80/#83: never park a dead object). Two
    shapes of non-ring input: a Patch in the ring, and the same strip
    handed over twice. The existing contract -- refusal by name, nothing
    created -- must survive whatever happens to the triangular member."""
    ccm.build_cube_corner_model(doc)
    strips = [doc.getObject(n) for n in STRIP_NAMES]
    patch_a = doc.getObject("PatchA")
    cases = [("a patch in place of a strip",
              (strips[0], strips[1], patch_a), "3-cycle"),
             ("the same strip twice",
              (strips[0], strips[1], strips[0]), None)]
    errors, checks = [], []
    for label, args, must_contain in cases:
        before = _corner_names(doc)
        with _CaptureConsole() as cap:
            made = create_corner_blend(*args)
        after = _corner_names(doc)
        msg = "".join(cap.errors).strip()
        named = bool(msg) and "Silk:" in msg
        if made is not None or after != before or not named:
            errors.append("%s: made=%s corners %s->%s msg=%r"
                          % (label, made, before, after, cap.errors))
            continue
        if must_contain and must_contain not in msg:
            errors.append("%s: refused, but not by the ring contract "
                          "(missing %r): %r" % (label, must_contain, msg))
            continue
        checks.append("%s: refused by name, nothing created: %s"
                      % (label, msg))
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_cube_corner_fixture_is_oracle_green,
    test_3valent_cube_corner_builds_green,
    test_3valent_cube_corner_non_ring_refused,
]
