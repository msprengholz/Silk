"""KNOWN-ANSWER CALIBRATION: the triangular 4th member vs upstream.

QUESTION (measurement, not a build): is our ported triangular member
(`SilkMachinery.control_grid64_3_1`) faithful to upstream's
`ArachNURBS.ControlGrid64_3_1Grid44` as it is ACTUALLY STORED in
`Resources/Demo_files/Silk_Demo_01.FCStd`?

METHOD. The demo's zip is read directly, read-only -- `Document.xml` for
the objects and the binary `Poles*` / `Weights*` blobs for the numbers --
so nothing is opened, recomputed or re-saved:

  * four `ControlGrid64_3_1Grid44` members are stored in Demo_01
    (`ControlGrid64_3_Grid44`, `...001`, `...002`, `...003`), each linked
    to one `ControlGrid44_2EdgeSegments*` carrier that holds the 4x4
    input grid (16 poles + 16 weights) and each carrying a `Corner` value
    (3, 0, 1, 3 respectively);
  * the built member is stored beside its input: 24 poles + 24 weights.
    That stored 24 is the known answer;
  * the upstream side is re-run LIVE in the same test document -- the real
    `AN.ControlGrid64_3_1Grid44` class on a carrier object, the same
    parity-oracle pattern `Tests/test_corner_blend.py` uses for the
    legacy subgrid chain -- and compared with the stored 24 as well. That
    check is the instrument's known-answer calibration: the stored member
    IS upstream's own output, so a deviation can only be our port's.

MEASURED (raw numbers, `docs/research/silk-member-calibration.md`; the
deviation is the repo's convention, the Euclidean pole distance in mm):

  * upstream's own class reproduces every stored member EXACTLY
    (max |dPole| = max |dWeight| = 0.0 for all four objects);
  * our port does not. The divergence is confined to THREE flat slots of
    the 24-pole output -- 8 (row 1 col 2, p12), 15 (row 2 col 3, p23) and
    16 (row 2 col 4, p24) -- and every other slot matches exactly; the
    weight channel is exact on the demo only because the demo's inputs
    carry unit weights;
  * max |dPole| per member: 2.3824 mm (`...44`, corner 3), 1.2721 mm
    (`...001`, corner 0), 6.3310 mm (`...002`, corner 1), 7.6036 mm
    (`...003`, corner 3) -- of the order of one whole input cell edge
    (0.9-1.2 x the mean cell edge), not a rounding difference. Slot 16's
    deviation is exactly twice slot 15's on every object, which is the
    signature of a single wrong source pole fed through the halving
    chain;
  * with NON-UNIT weights our port's output differs from upstream at two
    weight slots as well -- flat 8 and 9, i.e. w12 and w13 -- evidence
    that the demo (unit weights) cannot carry and the third test records
    on a synthetic input (max |dWeight| 1.875 there, per-corner pairs in
    the checks and the finding).

The three divergent slots are exactly upstream's "tiny spacing" points of
the third strategy (p12, p23, p24): the 0-curvature trims that un-collapse
the two interior rows near the collapsed end row. Upstream's own comment
says that spacing "will break G1 slightly. The goal is to balance G1 loss
versus folding over." This matters for the cube-corner apex reading
(`Tests/test_cube_corner_3valent.py`): the degenerate boundary normals and
the 16/1521 fold are read off a member that is NOT upstream's. On that
fixture the slips move the member by 3.333e-2 mm (one corner-cell pole
step) and the 36-pole corner net by 5.556e-3 mm at slots 25/26, while the
collapsed apex row is byte-identical -- so the degenerate apex normal is
not the port's doing (fourth test; full reading in the finding).

The pins in this module are calibration records, not pass/fail thresholds
for surface quality: no continuity label is asserted anywhere here. A pin
that fails means the maths changed -- update both the pin and the finding.
"""

import os
import re
import struct
import sys
import zipfile

import FreeCAD

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import silk_reload  # noqa: E402  (repo layout: MOD_DIR)

from SilkMachinery import control_grid64_3_1  # noqa: E402

MOD_DIR = silk_reload.MOD_DIR
DEMO = os.path.join(MOD_DIR, "Resources", "Demo_files", "Silk_Demo_01.FCStd")
MEMBER_CLASS = "ControlGrid64_3_1Grid44"

# The flat slots of the 24-pole output (4 rows x 6 columns) where our port
# and upstream disagree. Slot 8 = p12 / w12 (row 1 col 2); slot 15 = p23;
# slot 16 = p24; slot 9 = w13 (row 1 col 3).
DIVERGENT_SLOTS = (8, 15, 16)
DIVERGENT_WEIGHT_SLOTS = (8, 9)
# The synthetic non-unit-weight input of the third test: its max |dWeight|
# (flat slots 8 and 9; the pins are that number and the two w12/w13 pairs
# the checks print).
SYNTH_MAX_DWEIGHT = 1.875

# Measured on Demo_01 (see the finding): max |dPole| per stored member,
# the Euclidean pole distance in mm between our port and the stored
# member. `rel` in the checks is that deviation over the stored net's
# bounding-box diagonal (20-24 % of it).
MEASURED_MAX_DPOLE = {
    "ControlGrid64_3_Grid44": 2.3823927790370045,
    "ControlGrid64_3_Grid44001": 1.2720659601562707,
    "ControlGrid64_3_Grid44002": 6.3309534363346289,
    "ControlGrid64_3_Grid44003": 7.6035673075488015,
}
# max |dWeight| on the demo: 0.0, for all four -- the demo's input weights
# are all 1.0, so no weight can deviate. The weight channel's divergence
# is only observable with non-unit weights (third test, same magnitude is
# a property of the input, not of the demo).
MEASURED_MAX_DWEIGHT = {
    "ControlGrid64_3_Grid44": 0.0,
    "ControlGrid64_3_Grid44001": 0.0,
    "ControlGrid64_3_Grid44002": 0.0,
    "ControlGrid64_3_Grid44003": 0.0,
}
TOL_EXACT = 1e-9


# ---------------------------------------------------------------------------
# reading the demo, read-only: Document.xml + the binary property blobs
# ---------------------------------------------------------------------------

def _vec_list(z, fname):
    raw = z.read(fname)
    n = struct.unpack("<I", raw[:4])[0]
    if len(raw) != 4 + n * 24:
        raise ValueError("%s: %d bytes, expected %d for %d poles"
                         % (fname, len(raw), 4 + n * 24, n))
    flat = struct.unpack("<%dd" % (n * 3), raw[4:])
    return [FreeCAD.Vector(flat[3 * i], flat[3 * i + 1], flat[3 * i + 2])
            for i in range(n)]


def _float_list(z, fname):
    raw = z.read(fname)
    n = struct.unpack("<I", raw[:4])[0]
    if len(raw) != 4 + n * 8:
        raise ValueError("%s: %d bytes, expected %d for %d weights"
                         % (fname, len(raw), 4 + n * 8, n))
    return list(struct.unpack("<%dd" % n, raw[4:]))


def _prop(body, name):
    """The first value/file attribute of the property `name`.

    FreeCAD writes a scalar as `<Float value="..."/>` and a link as
    `<Link value="..."/>`, but a list property as `<VectorList
    file="Poles42"/>` when it is big enough to spill into its own zip
    entry."""
    m = re.search(r'<Property name="%s"[^>]*>\s*<[A-Za-z:]+ '
                  r'(?:value|file)="([^"]*)"' % name, body)
    return m.group(1) if m else None


def _parse_objects(doc):
    """{name: body} for every top-level object in Document.xml.

    A raw split, not an XML parse: the demo's Document.xml is 2 MB and the
    only nesting that matters (`<Object>` inside `<Object>`) does not
    occur -- verified by the object count of the parsed blocks.
    """
    out = {}
    for chunk in doc.split('<Object name="')[1:]:
        name, _, body = chunk.partition('"')
        out[name] = body.split("</Object>")[0]
    return out


def read_demo_members():
    """The four stored triangular members of Demo_01, with their stored
    input grid (16 poles/weights), `Corner`, and stored output (24/24).

    Returns [dict(name, link, corner, in_poles, in_weights, poles,
    weights)] in document order.
    """
    if not os.path.isfile(DEMO):
        raise IOError("demo not found: %s" % DEMO)
    z = zipfile.ZipFile(DEMO)
    try:
        objs = _parse_objects(z.read("Document.xml").decode("utf-8",
                                                           "replace"))
        members = []
        for name, body in objs.items():
            if ('module="ArachNURBS" class="%s"' % MEMBER_CLASS) not in body:
                continue
            link = _prop(body, "ControlGrid44")
            corner = _prop(body, "Corner")
            poles_file = _prop(body, "Poles")
            weights_file = _prop(body, "Weights")
            if not all((link, corner, poles_file, weights_file)):
                raise ValueError("%s: incomplete stored member (link=%r "
                                 "corner=%r poles=%r weights=%r)"
                                 % (name, link, corner, poles_file,
                                    weights_file))
            src = objs.get(link)
            if src is None:
                raise ValueError("%s: linked input %s not in the document"
                                 % (name, link))
            members.append(dict(
                name=name, link=link, corner=int(round(float(corner))),
                corner_stored=float(corner),
                in_poles=_vec_list(z, _prop(src, "Poles")),
                in_weights=_float_list(z, _prop(src, "Weights")),
                poles=_vec_list(z, poles_file),
                weights=_float_list(z, weights_file),
            ))
        return members
    finally:
        z.close()


# ---------------------------------------------------------------------------
# the upstream side, run live: the real legacy class on a carrier object
# ---------------------------------------------------------------------------

def upstream_member(doc, in_poles, in_weights, corner):
    """Upstream's `AN.ControlGrid64_3_1Grid44` executed on `in_poles` /
    `in_weights`: (24 poles, 24 weights). The two temp objects are
    removed before returning (the parity pattern of
    Tests/test_corner_blend.py::_legacy_corner_chain)."""
    import ArachNURBS as AN
    carrier = member = None
    try:
        carrier = doc.addObject("Part::FeaturePython", "_cal_grid44")
        carrier.addProperty("App::PropertyVectorList", "Poles", "X", "p")
        carrier.addProperty("App::PropertyFloatList", "Weights", "X", "w")
        carrier.Poles = list(in_poles)
        carrier.Weights = list(in_weights)
        member = doc.addObject("Part::FeaturePython", "_cal_grid64")
        AN.ControlGrid64_3_1Grid44(member, carrier, corner)
        member.recompute()
        return list(member.Poles), list(member.Weights)
    finally:
        for o in (member, carrier):
            if o is not None and doc.getObject(o.Name) is not None:
                try:
                    doc.removeObject(o.Name)
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# the measurements
# ---------------------------------------------------------------------------

def _deviations(our_poles, our_weights, ref_poles, ref_weights):
    dp = [(a - b).Length for a, b in zip(our_poles, ref_poles)]
    dw = [abs(a - b) for a, b in zip(our_weights, ref_weights)]
    return dp, dw


def _mean_cell_edge(poles16):
    """Mean distance between adjacent poles of the 4x4 input net
    (row-major). Invariant under the port's rot90, so it is the same
    number in the port's own (rotated) frame -- the natural scale of a
    deviation in the member's interior."""
    edges = []
    for i in range(4):
        for j in range(4):
            k = i * 4 + j
            if j < 3:
                edges.append((poles16[k] - poles16[k + 1]).Length)
            if i < 3:
                edges.append((poles16[k] - poles16[k + 4]).Length)
    return sum(edges) / len(edges)


def test_demo_stored_member_is_upstream_class_output(doc):
    """The instrument's known-answer calibration: upstream's own class,
    re-run on the demo's stored input grid, reproduces the demo's stored
    24-pole member exactly. If THIS fails the demo is not a valid oracle
    and nothing below it can be read as our port's deviation."""
    errors, checks = [], []
    members = read_demo_members()
    if len(members) != 4:
        errors.append("expected 4 stored members in the demo, found %d"
                      % len(members))
        return {"pass": not errors, "errors": errors, "checks": checks}
    for m in members:
        rp, rw = upstream_member(doc, m["in_poles"], m["in_weights"],
                                 m["corner"])
        dp, dw = _deviations(rp, rw, m["poles"], m["weights"])
        md, mw = max(dp), max(dw)
        ok = len(rp) == 24 and md <= TOL_EXACT and mw <= TOL_EXACT
        line = ("%s (corner %.0f <- %s): upstream re-run vs stored 24: "
                "max|dPole| %.3e mm, max|dWeight| %.3e, slots differing: %s"
                % (m["name"], m["corner_stored"], m["link"], md, mw,
                   [i for i, d in enumerate(dp) if d > TOL_EXACT]))
        checks.append(line)
        if not ok:
            errors.append(line + "  (EXPECTED exact)")
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_our_port_measured_against_demo_stored_member(doc):
    """Our `control_grid64_3_1` on the demo's stored input grid vs the
    demo's stored 24-pole member.

    The measured deviation is PINNED (MEASURED_MAX_DPOLE) and the
    divergent slots are asserted to be exactly DIVERGENT_SLOTS: the port
    is upstream's construction with three slots reconstructed from the
    wrong source pole, not a different construction. A failing pin means
    the maths changed -- update it together with
    docs/research/silk-member-calibration.md."""
    errors, checks = [], []
    members = read_demo_members()
    if not members:
        errors.append("no stored members found in the demo")
        return {"pass": not errors, "errors": errors, "checks": checks}
    for m in members:
        op, ow = control_grid64_3_1(m["in_poles"], m["in_weights"],
                                    m["corner"])
        if op is None:
            errors.append("%s: control_grid64_3_1 returned None"
                          % m["name"])
            continue
        dp, dw = _deviations(op, ow, m["poles"], m["weights"])
        md, mw = max(dp), max(dw)
        slots = tuple(i for i, d in enumerate(dp) if d > TOL_EXACT)
        wslots = tuple(i for i, d in enumerate(dw) if d > TOL_EXACT)
        pin = MEASURED_MAX_DPOLE[m["name"]]
        # scale: the diagonal of the stored net and the input cell edge,
        # for relative readings
        xs = [p.x for p in m["poles"]]
        ys = [p.y for p in m["poles"]]
        zs = [p.z for p in m["poles"]]
        diag = ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2
                + (max(zs) - min(zs)) ** 2) ** 0.5
        edge = _mean_cell_edge(m["in_poles"])
        checks.append("%s (corner %.0f): our port vs stored 24: "
                      "max|dPole| %.3e mm (net diagonal %.1f mm, rel %.2e; "
                      "mean input cell edge %.3f mm, %.3f cell edges), "
                      "max|dWeight| %.3e; pole slots differing %s; weight "
                      "slots differing %s"
                      % (m["name"], m["corner_stored"], md, diag,
                         md / diag if diag else 0.0, edge, md / edge,
                         mw, list(slots), list(wslots)))
        # structural signature of the wrong source pole: p24 carries the
        # error and p23 halves it on the way back to sp[10]
        checks.append("%s: slot 16 / slot 15 deviation = %.9f "
                      "(the halving-chain signature, expected 2)"
                      % (m["name"], dp[16] / dp[15] if dp[15] else 0.0))
        if dp[15] and abs(dp[16] / dp[15] - 2.0) > 1e-6:
            errors.append("%s: dp[16]/dp[15] = %.9f, expected 2"
                          % (m["name"], dp[16] / dp[15]))
        if slots != DIVERGENT_SLOTS:
            errors.append("%s: divergent slots %s, expected %s"
                          % (m["name"], list(slots), list(DIVERGENT_SLOTS)))
        if wslots:
            errors.append("%s: the demo's unit weights should give an "
                          "exact weight channel, got slots %s"
                          % (m["name"], list(wslots)))
        wp = MEASURED_MAX_DWEIGHT[m["name"]]
        if abs(mw - wp) > TOL_EXACT:
            errors.append("%s: max|dWeight| %.3e is not the recorded %.3e"
                          % (m["name"], mw, wp))
        if abs(md - pin) > TOL_EXACT:
            errors.append("%s: max|dPole| %.6e mm is not the recorded "
                          "%.6e mm; if the port was fixed, re-pin and "
                          "update docs/research/silk-member-calibration.md"
                          % (m["name"], md, pin))
        if mw > TOL_EXACT:
            errors.append("%s: max|dWeight| %.3e on unit-weight input"
                          % (m["name"], mw))
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_weight_channel_diverges_on_non_unit_weights(doc):
    """The demo carries unit weights in and out, so it cannot say anything
    about the weight channel. This feeds BOTH sides a synthetic 4x4 grid
    with non-unit weights (the poles are just a generic curved net, so the
    pole signature is expected to be the same three slots) and records
    where the weights part company: output flat slots 8 and 9, i.e. w12
    and w13, which upstream builds from input weights 4/10 and 1/10 while
    our port builds them from 5/11 and 5/6. This is a source-level
    difference demonstrated on a synthetic input, not demo evidence -- and
    it is the reason the demo's weight comparison cannot be read as a
    match.
    """
    errors, checks = [], []
    poles = [FreeCAD.Vector(10.0 * j + 0.7 * i, 10.0 * i - 0.3 * j,
                            0.31 * ((i * j + 2 * i + 3 * j) % 7))
             for i in range(4) for j in range(4)]
    weights = [1.0, 1.5, 2.0, 3.0, 0.5, 1.25, 2.5, 4.0,
               0.75, 1.75, 3.5, 0.25, 2.25, 5.0, 1.1, 0.9]
    dmax_w = 0.0
    dmax_p = 0.0
    for corner in range(4):
        rp, rw = upstream_member(doc, poles, weights, corner)
        op, ow = control_grid64_3_1(poles, weights, corner)
        dp, dw = _deviations(op, ow, rp, rw)
        slots = tuple(i for i, d in enumerate(dp) if d > TOL_EXACT)
        wslots = tuple(i for i, d in enumerate(dw) if d > TOL_EXACT)
        dmax_w = max(dmax_w, max(dw))
        dmax_p = max(dmax_p, max(dp))
        checks.append("corner %d: our w12(slot 8)=%.6f vs upstream %.6f, "
                      "our w13(slot 9)=%.6f vs upstream %.6f; pole slots "
                      "differing %s; weight slots differing %s"
                      % (corner, ow[8], rw[8], ow[9], rw[9],
                         list(slots), list(wslots)))
        if wslots != DIVERGENT_WEIGHT_SLOTS:
            errors.append("corner %d: weight slots differing %s, expected "
                          "%s" % (corner, list(wslots),
                                  list(DIVERGENT_WEIGHT_SLOTS)))
        if slots != DIVERGENT_SLOTS:
            errors.append("corner %d: pole slots differing %s, expected %s"
                          % (corner, list(slots), list(DIVERGENT_SLOTS)))
        if len(op) != 24 or len(ow) != 24:
            errors.append("corner %d: our port returned %d poles / %d "
                          "weights" % (corner, len(op), len(ow)))
    checks.append("synthetic non-unit-weight input: max|dPole| %.3e mm, "
                  "max|dWeight| %.3e (weights in [0.25, 5.0])"
                  % (dmax_p, dmax_w))
    if dmax_w <= 1e-2:
        errors.append("expected a weight divergence on non-unit input, "
                      "measured %.3e" % dmax_w)
    if abs(dmax_w - SYNTH_MAX_DWEIGHT) > TOL_EXACT:
        errors.append("max|dWeight| %.6e is not the recorded %.6e; if the "
                      "port was fixed, re-pin and update "
                      "docs/research/silk-member-calibration.md"
                      % (dmax_w, SYNTH_MAX_DWEIGHT))
    return {"pass": not errors, "errors": errors, "checks": checks}


def _grid_max_dev(a, b):
    return max((x - y).Length for x, y in zip(a, b))


def test_cube_corner_member_divergence_scale(doc):
    """What the divergence above means for the cube-corner apex reading.

    `Tests/test_cube_corner_3valent.py` measures the shipped 3-valent
    corner on the cube-corner fixture -- degenerate normals at apex-side
    stations and a 16/1521 fold in the tight apex band. That corner is
    built from OUR member. This test takes the fixture's own member INPUT
    (identified by value against the ring `SilkCorner.corner_inputs`
    builds), runs upstream's member on it too, and measures both the
    member-level and the resulting 36-pole corner-level difference. If
    upstream's member does not close the ring, that is recorded as such --
    it would mean the divergence is functional for the shipped build, not
    cosmetic."""
    import Tests.cube_corner_model as ccm
    import SilkCorner
    from SilkMachinery import corner_grid, reverse_grid_rows

    errors, checks = [], []
    model = ccm.build_cube_corner_model(doc)
    strips = [doc.getObject(n) for n in ("B_AB", "B_BC", "B_CA")]
    grids, corner_cells, why = SilkCorner.corner_inputs(strips)
    if grids is None:
        return {"pass": False,
                "errors": ["corner_inputs refused the fixture: %s" % why],
                "checks": checks}

    # which patch/corner/rev the build's member comes from: match our
    # candidates against the ring member BY VALUE
    matches = []
    for pth in model["patches"].values():
        cell = corner_cells.get(pth.Name)
        poles_c, weights_c = SilkCorner._corner_cell_net(pth, cell)
        if poles_c is None:
            continue
        for corner in range(4):
            mp, mw = control_grid64_3_1(poles_c, weights_c, corner)
            if mp is None:
                continue
            for rev in (False, True):
                cand = reverse_grid_rows(mp, mw) if rev else (list(mp),
                                                              list(mw))
                if any(_grid_max_dev(cand[0], g[0]) <= TOL_EXACT
                       for g in grids):
                    matches.append((pth.Name, corner, rev, poles_c,
                                    weights_c, cand))
    if not matches:
        return {"pass": False,
                "errors": ["the ring's member is not any candidate our port "
                           "builds from the fixture's corner cells"],
                "checks": checks}
    # congruent corner cells make several candidates produce the SAME
    # member; different inputs would make the identity ambiguous
    inputs_same = all(_grid_max_dev(m[3], matches[0][3]) <= TOL_EXACT
                      for m in matches[1:])
    checks.append("member input identified: %d candidate match(es) for "
                  "patch %s, corner %d, reversed=%s; all candidate inputs "
                  "identical: %s"
                  % (len(matches), matches[0][0], matches[0][1],
                     matches[0][2], inputs_same))
    if not inputs_same:
        errors.append("ambiguous member input: %d candidates with "
                      "different input nets" % len(matches))
    pth, corner, rev, poles_c, weights_c, our_member = matches[0]

    up_poles, up_w = upstream_member(doc, poles_c, weights_c, corner)
    if rev:
        up_poles, up_w = reverse_grid_rows(up_poles, up_w)
    dev = _grid_max_dev(our_member[0], up_poles)
    slots = [i for i in range(24)
             if (our_member[0][i] - up_poles[i]).Length > TOL_EXACT]
    edge = _mean_cell_edge(poles_c)
    checks.append("fixture member input (patch %s, corner %d, reversed=%s): "
                  "our member vs upstream member: max|dPole| %.6e mm "
                  "(corner-cell edge %.4f mm, %.3f cell edges); slots %s"
                  % (pth, corner, rev, dev, edge, dev / edge, slots))
    # the apex itself: the collapsed end row is slots 18..23 (V3 row) and
    # it sits on the ring's shared corner. Both members collapse it onto
    # the same pole (row 2's far end of the rotated cell), so the
    # degenerate boundary normal at the apex is NOT the port's doing.
    row_dev = _grid_max_dev(our_member[0][18:24], up_poles[18:24])
    checks.append("collapsed apex row (slots 18-23): our member vs "
                  "upstream member: max|dPole| %.3e mm (both collapse onto "
                  "the same cell pole: %s)"
                  % (row_dev, row_dev <= TOL_EXACT))

    # consequence at the corner net: substitute upstream's member into the
    # ring and re-solve the 36-pole corner
    up_ring = []
    for g in grids:
        if _grid_max_dev(g[0], our_member[0]) <= TOL_EXACT:
            up_ring.append((up_poles, up_w))
        else:
            up_ring.append(g)
    p36_ours, _w1, why1 = corner_grid(list(grids), SilkCorner.CORNER_TOL)
    p36_up, _w2, why2 = corner_grid(up_ring, SilkCorner.CORNER_TOL)
    if p36_ours is None or p36_up is None:
        checks.append("corner grid: ours -> %r, upstream member -> %r"
                      % (why1, why2))
        if p36_ours is None:
            errors.append("the fixture ring does not close with OUR member: "
                          "%s" % why1)
    else:
        cdev = max((a - b).Length for a, b in zip(p36_ours, p36_up))
        cslots = [i for i in range(36)
                  if (p36_ours[i] - p36_up[i]).Length > TOL_EXACT]
        checks.append("36-pole corner net: ours vs upstream's member -> "
                      "max|dPole| %.6e mm; slots differing %s"
                      % (cdev, cslots))
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_demo_stored_member_is_upstream_class_output,
    test_our_port_measured_against_demo_stored_member,
    test_weight_channel_diverges_on_non_unit_weights,
    test_cube_corner_member_divergence_scale,
]
