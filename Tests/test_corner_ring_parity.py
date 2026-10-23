"""The corner stage's RING NORMALIZER against the reference's own rings.

`SilkMachinery.corner_grid` is the one function that turns a corner's ring of
24-pole member nets into the 6x6 the corner fill is built from, so it is the
first thing the corner stage does that the subgrid algebra does not. It used
to demand ONE corner pattern -- every adjacent pair sharing the slots
`CORNER_COMMON` = (3, 2), or all of them mirrored -- while
`subgrid33_2grid64` underneath takes each pair on whatever corners it finds.
The maintainer's own corners are built the second way: read offline from the
tracked `.FCStd` files (`Tests.reference_corner_diff.Archive`, stdlib only),
his 20 quad corners per file share (0, 1), (0, 2) and (3, 1) as well as
(3, 2), mixed freely round one ring, and the pair path reproduces every one of
them pole for pole. The normalizer refused all 40.

WHAT THIS MODULE PINS, and it is the acceptance for that defect: the parity
table runs THROUGH `corner_grid` (not through the raw pair path), so a
regression of the normalizer cannot hide behind the primitives.

MEASURED (2026-10, FreeCAD 1.1.3 / OCCT 7.9): episode 28 and episode 29, 20
quad corners each, worst pole deviation 0.000e+00 mm and worst weight
deviation 0.000e+00 over all 36 poles of every corner, from the ring grids
the file itself stores.

NOT asserted here: any continuity property, any claim that our corner STAGE
reproduces his corner (it does not -- the ring LOOP is still ours, see
`docs/research/silk-rolling-corner-66.md`), or that a mixed ring should
assemble (it is refused, and the refusal is pinned by name).
"""

# --- manual tier ------------------------------------------------------
# A parity sweep over the maintainer's 40 stored quad corners, read from
# the tracked .FCStd archives: an end-to-end rebuild plus a measurement
# sweep, not a unit invariant.
# So this module is NOT in the default (fast) tier. Run it with
# `python3 Tests/run_all.py --manual` (or by name as a filter);
# Tests/test_manual_tier.py asserts it stays importable and keeps tests.
MANUAL = True


import FreeCAD

import Tests.reference_corner_diff as R
import SilkMachinery as M

TOL = 1e-6

# Which reference files the table runs over. Both are tracked in the repo
# (`Resources/Tutorial_Files/Silk CopyPasta/`), so this needs no GUI and no
# fetch: the nets are read out of the .FCStd zip with the standard library.
EPISODES = ("28", "29")

# Every file carries 20 quad-ring corners (and a separate family of N-star
# corners, which are a different assembly and are counted out by kind).
CORNERS_PER_EPISODE = 20


def _ring(archive, corner):
    """The corner's 4 member nets in ring order, as FreeCAD Vectors."""
    out = []
    for name in corner["members"]:
        node = archive.get(name)
        poles = [FreeCAD.Vector(*p) for p in (node.poles or [])]
        weights = list(node.weights or [1.0] * len(poles))
        out.append((poles, weights))
    return out


def _stored(archive, name):
    node = archive.get(name)
    poles = [FreeCAD.Vector(*p) for p in (node.poles or [])]
    return poles, list(node.weights or [1.0] * len(poles))


def _flip_columns(poles, weights):
    """The 24-pole grid with its U (column) axis reversed, `u -> 5 - u`.

    A reparameterization of the same member (the same surface read the other
    way round the seam), which is all this test needs: it renumbers the
    corner slots (0 <-> 1, 2 <-> 3) and leaves every corner where it is, so
    the ring still shares its corners and only the PAIRING changes."""
    p = [poles[r * 6 + (5 - c)] for r in range(4) for c in range(6)]
    w = [weights[r * 6 + (5 - c)] for r in range(4) for c in range(6)]
    return p, w


def _corners(archive):
    """Every corner of the archive built from four ring members.

    The N-star corners (a three-member assembly, `ControlGridNStar66_NSub`
    over `SubGrid63_2Surf64` pairs) are a DIFFERENT construction that
    SilkMachinery has no port of, so they are counted out by kind rather
    than silently skipped by a filter nobody can see."""
    return [c for c in archive.corners() if c["kind"] == "quad-4sub"]


def test_the_reference_rings_are_reproduced_through_corner_grid(doc):
    """OWNER ACCEPTANCE: the parity table THROUGH the ring normalizer.

    For every quad corner of every tracked reference file: feed the ring the
    file stores to `corner_grid` and compare the 36 poles and 36 weights it
    returns against the 6x6 the file stores. The claim is exact parity, not
    "close", so the check line reports the worst deviation and the failure
    names the corner."""
    errors, checks = [], []
    checked = 0
    for tag in EPISODES:
        path = R.default_reference(tag)
        archive = R.Archive(path)
        corners = _corners(archive)
        if len(corners) != CORNERS_PER_EPISODE:
            errors.append("episode %s: %d quad corners, expected %d"
                          % (tag, len(corners), CORNERS_PER_EPISODE))
            continue
        worst_p = worst_w = 0.0
        patterns = set()
        here = 0
        for corner in corners:
            ring = _ring(archive, corner)
            pairs, why = M._ring_pairs(ring, TOL)
            if pairs is None:
                errors.append("episode %s / %s: %s"
                              % (tag, corner["root"], why))
                continue
            patterns.add(tuple(pairs))
            p36, w36, why = M.corner_grid(ring, TOL)
            if p36 is None:
                errors.append("episode %s / %s: corner_grid refused: %s"
                              % (tag, corner["root"], why))
                continue
            ref_p, ref_w = _stored(archive, corner["grid"])
            if len(ref_p) != len(p36) or len(ref_w) != len(w36):
                errors.append("episode %s / %s: %d/%d poles, %d/%d weights "
                              "against the stored %d/%d"
                              % (tag, corner["root"], len(p36), len(w36),
                                 len(ref_p), len(ref_w), len(ref_p),
                                 len(ref_w)))
                continue
            worst_p = max(worst_p, max((a - b).Length
                                       for a, b in zip(p36, ref_p)))
            worst_w = max(worst_w, max(abs(a - b)
                                       for a, b in zip(w36, ref_w)))
            here += 1
            checked += 1
        checks.append("episode %s: %d quad corners through corner_grid, "
                      "worst pole deviation %.3e mm, worst weight deviation "
                      "%.3e, %d distinct pair patterns: %s"
                      % (tag, here, worst_p, worst_w, len(patterns),
                         sorted(patterns)[:3]))
        if worst_p > 0.0 or worst_w > 0.0:
            errors.append("episode %s: parity is not exact -- worst pole "
                          "%.3e mm, worst weight %.3e" % (tag, worst_p, worst_w))
    if checked != CORNERS_PER_EPISODE * len(EPISODES):
        errors.append("%d corners came through, expected %d"
                      % (checked, CORNERS_PER_EPISODE * len(EPISODES)))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_as_stored_ring_is_the_winding_the_reader_takes(doc):
    """The no-op path: a ring whose four pairs are all read WITHOUT a grid
    swap is handed back AS STORED (the same list object), so the direction
    step can never re-order a ring this workbench builds -- that is what
    keeps the shipped corner byte-identical.

    The reference's rings are exactly that shape, which is why the parity
    above is at 0.000e+00 and not at parity-up-to-a-reversal."""
    archive = R.Archive(R.default_reference("28"))
    errors, checks = [], []
    for corner in _corners(archive)[:4]:
        ring = _ring(archive, corner)
        out, why = M._oriented_ring(ring, TOL)
        if out is None:
            errors.append("%s: refused: %s" % (corner["root"], why))
        elif out is not ring:
            errors.append("%s: the ring was re-ordered on the as-stored path"
                          % corner["root"])
        else:
            pairs, _why = M._ring_pairs(out, TOL)
            checks.append("%s: as stored, pairs %s"
                          % (corner["root"], pairs))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_the_ring_direction_is_normalized_and_not_refused(doc):
    """A ring handed over the other way round (`grids[0]` plus the rest
    reversed) must build the SAME 6x6: the direction is normalized, not
    refused. Measured on the reference's own rings, whose pairs are MIXED --
    so this is also the proof that the reversal rule does not depend on a
    single corner pattern."""
    archive = R.Archive(R.default_reference("29"))
    errors, checks = [], []
    for corner in _corners(archive)[:6]:
        ring = _ring(archive, corner)
        p_can, w_can, why = M.corner_grid(ring, TOL)
        if p_can is None:
            errors.append("%s: as stored refused: %s" % (corner["root"], why))
            continue
        mirrored = [ring[0]] + list(reversed(ring[1:]))
        p_mir, w_mir, why = M.corner_grid(mirrored, TOL)
        if p_mir is None:
            errors.append("%s: mirrored ring refused, not normalized: %s"
                          % (corner["root"], why))
            continue
        dev = max((a - b).Length for a, b in zip(p_can, p_mir))
        wdev = max(abs(a - b) for a, b in zip(w_can, w_mir))
        checks.append("%s: mirrored ring = as-stored ring, 36-pole dev %.3e "
                      "mm / weight dev %.3e" % (corner["root"], dev, wdev))
        if dev > 1e-9 or wdev > 1e-9:
            errors.append("%s: the mirrored ring fills differently (%.3e mm / "
                          "%.3e)" % (corner["root"], dev, wdev))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_a_ring_that_mixes_the_two_readings_is_refused_by_name(doc):
    """The one ring shape that is still refused: three pairs the reader takes
    without swapping its two grids and one that would make it swap. One of
    its four 3x3 subgrids would land transposed against its neighbours, so
    the 6x6's interior rows would not line up -- a silent wrong surface, not
    a corner. The refusal must NAME the patterns it read.

    The case is built from a real reference ring by mirroring the U axis of
    the two members of ONE pair (`u -> 5-u`, a reparameterization that leaves
    every corner where it is and only renumbers the slots), which is the
    cheapest honest way to hand the normalizer a mixed ring."""
    archive = R.Archive(R.default_reference("28"))
    errors, checks = [], []
    corner = None
    for cand in _corners(archive):
        pairs, _why = M._ring_pairs(_ring(archive, cand), TOL)
        if pairs is not None and tuple(pairs) == ((3, 2), (3, 2), (3, 1),
                                                 (0, 2)):
            corner = cand
            break
    if corner is None:
        return {"pass": False,
                "errors": ["no reference ring with the expected pattern"],
                "checks": []}
    ring = _ring(archive, corner)
    flipped = [_flip_columns(p, w) for p, w in ring[:2]] + list(ring[2:])
    pairs, why = M._ring_pairs(flipped, TOL)
    if pairs is None:
        return {"pass": False, "errors": ["the flipped ring lost its shared "
                                          "corners: %s" % why], "checks": []}
    p36, _w36, why = M.corner_grid(flipped, TOL)
    cheap = [M._pair_needs_swap(c) for c in pairs]
    checks.append("%s flipped: pairs %s, needs-swap %s"
                  % (corner["root"], pairs, cheap))
    if p36 is not None:
        errors.append("a mixed ring assembled -- the transposition guard is "
                      "gone (pairs %s)" % (pairs,))
    elif why is None or "%r" % (pairs,) not in why:
        errors.append("refused, but not by name with its pattern: %r" % (why,))
    else:
        checks.append("refused by name: %s" % why)
    return {"pass": not errors, "errors": errors, "checks": checks}
