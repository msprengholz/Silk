"""The corner's interior step: a 6x6 that folds is re-solved as the
transfinite (Coons) fill of its own boundary loop.

WHAT THIS PINS, AND WHY IT IS UNIT-LEVEL

`SilkMachinery.smooth_folding_interior` is the corner stage's step after the
assembly (and after `smooth_degenerate_cap`, which owns the collapsed-side
case).  It is gated on the net ITSELF, so every claim below is a claim about
the net, not about a document: this module builds none, reads none, and
touches no path.  That keeps it in the fast tier, where a regression in the
step is seen in seconds.

THE INSTRUMENT AND ITS KNOWN ANSWERS.  `net_fold_count` is the number of
adjacent sample pairs of the exact rational net whose normals point apart --
the same reading `SilkChecks._normal_field_flips` takes on a Part surface,
taken on the net so the corner stage can act on it without FreeCAD.  Its
calibration is here, on nets whose answer is known:

  * a FLAT net (a plane, sampled at the clamped cubic's Greville abscissae,
    so the net represents the plane EXACTLY) -- fold count 0, and
    `coons_fill_interior` reproduces it pole for pole at the float floor.
    That is the known-good control: the refill is exact where the interior
    already is the transfinite fill;
  * the SAME net with one interior pole pushed through the surface -- a
    known fold, count > 0, and the refill takes it back to 0;
  * a net with a collapsed side (in the SHIPPED construction, the triangular
    member's junction row on a point) -- the step
    must NOT touch it, because `smooth_degenerate_cap` owns that case and
    the shipped construction is byte-identical through it.

WHAT IT DOES NOT DO.  It asserts no continuity label and no threshold on
geometry: the numbers it checks are identities (the same list returned), a
boundary that is not moved, and an exactness residual at the float floor.
"""

import FreeCAD

import SilkMachinery as SM

# The clamped cubic knots `_basis6` reads, and the six Greville abscissae
# that come with them -- the parameter values at which a bicubic net
# represents a LINEAR surface exactly (the average of each basis function's
# knot span).  A net whose poles are a plane evaluated at these sites IS
# that plane, which is what makes the flat test a known answer rather than
# a tolerance.
GREVILLE6 = (0.0, 1.0 / 9.0, 1.0 / 3.0, 2.0 / 3.0, 8.0 / 9.0, 1.0)


def _flat_net(tilt=(1.0, 0.5, 0.25)):
    """A 6x6 net that IS a plane: poles at the Greville sites of the plane
    z = tilt . (u, v, 1), flat v-major (`v * 6 + u`), all weights 1."""
    poles = []
    for v in range(6):
        for u in range(6):
            x, y = GREVILLE6[u], GREVILLE6[v]
            poles.append(FreeCAD.Vector(x, y,
                                        tilt[0] * x + tilt[1] * y
                                        + tilt[2]))
    return poles, [1.0] * 36


def _folded_net():
    """The flat net with ONE interior pole pushed through the surface.

    Pole (row 2, col 2) is a flat net's own value; driving it far BELOW the
    plane (through it) makes the normal field reverse around that cell --
    the smallest, most legible known fold this construction has, and an
    INTERIOR pole, so the boundary stays the plane and the refill has an
    exact answer to recover (measured: the fold appears at a displacement of
    -3 and is stable from there; -1 does not fold, which is why this is a
    reading and not a guess)."""
    poles, weights = _flat_net()
    k = 2 * 6 + 2
    pole = poles[k]
    poles[k] = FreeCAD.Vector(pole.x, pole.y, pole.z - 3.0)
    return poles, weights


def _collapsed_net():
    """The flat net with its last ROW collapsed onto one point -- the shape
    every corner built before #119 carries on one side."""
    poles, weights = _flat_net()
    apex = poles[5 * 6 + 0]
    for u in range(6):
        poles[5 * 6 + u] = FreeCAD.Vector(apex.x, apex.y, apex.z)
    return poles, weights


def _boundary(poles):
    return [k for k in range(36) if k // 6 in (0, 5) or k % 6 in (0, 5)]


# ---------------------------------------------------------------------------
# the instrument's calibration
# ---------------------------------------------------------------------------

def test_the_fold_count_reads_zero_flat_and_rises_on_a_known_fold(doc):
    """The known-good / known-fold control for `net_fold_count`."""
    errors, checks = [], []
    flat_p, flat_w = _flat_net()
    folded_p, folded_w = _folded_net()
    flat = SM.net_fold_count(flat_p, flat_w)
    folded = SM.net_fold_count(folded_p, folded_w)
    checks.append("fold count: flat net %d, the same net with one interior "
                  "pole pushed through the surface %d (n=12)"
                  % (flat, folded))
    if flat != 0:
        errors.append("a plane reads %d folds -- the instrument's floor is "
                      "not zero on a known-good net" % flat)
    if folded <= 0:
        errors.append("a net with an interior pole driven through the "
                      "surface reads %d folds -- the reading cannot see a "
                      "known fold" % folded)
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_coons_refill_is_exact_where_the_interior_already_is_the_fill(doc):
    """The known answer: on a planar net the refill reproduces every pole.

    A plane's transfinite fill IS the plane, so the least squares has an
    exact solution and the residual is the float floor -- the refill is not
    a smoothing operator that would blur an interior that is already right.
    """
    errors, checks = [], []
    poles, weights = _flat_net()
    out_p, out_w = SM.coons_fill_interior(poles, weights)
    dev = max((a - b).Length for a, b in zip(out_p, poles))
    checks.append("the flat net re-solved: max pole deviation %.3e mm"
                  % dev)
    if dev > 1e-9:
        errors.append("the refill moved a planar net by %.3e mm -- it is "
                      "not the transfinite fill" % dev)
    if out_w != weights:
        errors.append("the refill changed the weights (it must hold them "
                      "fixed)")
    return {"pass": not errors, "errors": errors, "checks": checks}


# ---------------------------------------------------------------------------
# the step's three gates
# ---------------------------------------------------------------------------

def test_a_fold_free_net_is_returned_as_the_same_lists(doc):
    """No fold -> the corner stage keeps the poles upstream gave it.

    Identity, not equality: the cube fixture's two-patch corner goes through
    this step on every build, so "unchanged" has to mean the same objects.
    """
    errors, checks = [], []
    poles, weights = _flat_net()
    out_p, out_w = SM.smooth_folding_interior(poles, weights)
    checks.append("a flat net: the step returned the SAME pole list %r and "
                  "the same weight list %r"
                  % (out_p is poles, out_w is weights))
    if out_p is not poles or out_w is not weights:
        errors.append("the step rebuilt a fold-free net -- every corner that "
                      "does not fold must take the byte-identical path")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_collapsed_net_is_left_to_the_cap_smoothing(doc):
    """A collapsed side is `smooth_degenerate_cap`'s case, not this step's.

    The collapsed net below ALSO folds (the apex row drags the interior), so
    the fold gate alone would fire: the collapsed-side gate is what keeps the
    shipped construction byte-identical, and this is the assertion that it
    is a gate and not a coincidence.
    """
    errors, checks = [], []
    poles, weights = _collapsed_net()
    folds = SM.net_fold_count(poles, weights)
    out_p, out_w = SM.smooth_folding_interior(poles, weights)
    checks.append("the collapsed net: fold count %d (so the fold gate alone "
                  "would fire %r); the step returned the same lists %r"
                  % (folds, folds > 0, out_p is poles and out_w is weights))
    if SM._collapsed_side(poles, 1e-6) is None:
        errors.append("the fixture does not collapse a side -- the check "
                      "below would prove nothing")
    if out_p is not poles or out_w is not weights:
        errors.append("the step re-solved a net with a collapsed side: that "
                      "corner belongs to `smooth_degenerate_cap`, and the "
                      "shipped construction is byte-identical through it")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_folding_net_is_re_solved_and_its_boundary_is_untouched(doc):
    """The repair itself: fewer folds, the SAME boundary, weights held.

    The boundary is the geometry the ring supplies, so it must not move -- a
    re-solve that touched it would break C0 at the seams it is supposed to
    meet.
    """
    errors, checks = [], []
    poles, weights = _folded_net()
    before = SM.net_fold_count(poles, weights)
    out_p, out_w = SM.smooth_folding_interior(poles, weights)
    after = SM.net_fold_count(out_p, out_w)
    bnd = _boundary(poles)
    moved_bnd = max((out_p[k] - poles[k]).Length for k in bnd)
    moved_in = max((out_p[k] - poles[k]).Length for k in range(36)
                   if k not in bnd)
    checks.append("the folding net: fold count %d -> %d; the boundary moved "
                  "%.3e mm, the interior up to %.6f mm"
                  % (before, after, moved_bnd, moved_in))
    if before <= 0:
        errors.append("the fixture does not fold -- nothing is proved")
    if out_p is poles:
        errors.append("the step did not re-solve a folding net")
    if after >= before:
        errors.append("the re-solved net folds %d times, the assembled one %d "
                      "-- the repair must fold LESS" % (after, before))
    if moved_bnd > 1e-12:
        errors.append("the re-solve moved a boundary pole by %.3e mm"
                      % moved_bnd)
    if out_w != weights:
        errors.append("the re-solve changed the weights")
    if moved_in <= 0.0:
        errors.append("no interior pole moved -- the net cannot have "
                      "changed")
    return {"pass": not errors, "errors": errors, "checks": checks}
