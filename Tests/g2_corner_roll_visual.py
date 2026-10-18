"""
MANUAL VISUAL RENDER -- what does the shipped 3-valent corner LOOK like
when its setbacks are asymmetric? (ticket #118, part of #1 the map).

WHY THIS EXISTS.  `Tests/g2_corner_roll_measure.py` measured the corner's
anisotropy as a NUMBER: on the cube-corner fixture the junction's curvature
ratio k_max/k_min moves from 1.04 (symmetric setbacks, 0.1 / 0.1) to 2.29
(asymmetric, 0.25 / 0.125), and the asymmetric corner develops a saddle
(k1 = +1.70, k2 = -2.46 /mm) near the junction.  That number is compatible
with two very different visual readings:

  * TWO ZONES of different fillet size, one rolling around the other (the
    maintainer's rolling fillet), or
  * a TWISTED / kinked corner.

Nobody has LOOKED.  The judgement is the owner's; this module only makes it
possible.  It writes PNGs to a directory the owner can open and prints the
numbers beside them.  It asserts NOTHING about which reading is right --
there is no threshold, no label, and no continuity claim anywhere here.

WHAT IT RENDERS, per config (symmetric, asymmetric -- the two setback
settings of #118), all from the SAME camera:

  (a) shaded, corner surface alone .......... <cfg>_1_shaded.png
      shaded, corner + its three strips ..... <cfg>_2_shaded_with_strips.png
  (b) curvature ratio k_max/k_min .......... <cfg>_3_ratio.png
      Gaussian curvature k_max*k_min ....... <cfg>_4_gauss.png
  (c) zebra stripes (if the tool exists) ... <cfg>_5_zebra.png

plus the two shared colour legends:
      corner_roll_legend_ratio.png / corner_roll_legend_gauss.png

THE CAMERA (identical for every image and both configs).  Orthographic
(no perspective distortion), looking down the cube's body diagonal at the
rounded vertex from OUTSIDE the corner:

  target   (0.05, 0.05, 0.05) mm -- the junction
  direction (1, 1, 1) / sqrt(3)
  position target - 0.9 * direction = (-0.4696, -0.4696, -0.4696) mm
  orientation quaternion (0.70710677, -0.70710677, 0, 2.186276)
  focalDistance 0.9 mm, nearDistance 0.0, farDistance 3.0 mm
  orthographic view height 0.42 mm  (4.2 x the symmetric corner's 0.1 mm
  extent, so both corners fit; the asymmetric corner is 2.5 x bigger)

The two configs' corners are NOT the same size -- the setback IS their size:
the symmetric corner's bounding box is 0.10 mm cubed, the asymmetric one
0.25 mm cubed.  So at one camera the asymmetric corner fills more of the
frame.  That is reported, not corrected: a fitting zoom per config would
destroy the comparison the same camera exists to make.

WHAT THE RENDERER ACTUALLY SUPPORTS (investigated on this build, FreeCAD
1.1.3; `report_renderer()` prints this too):

  * FreeCAD core has NO zebra and NO reflection-analysis display mode.  A
    `Part::Feature` ViewObject offers DisplayMode Shaded / Flat Lines /
    Wireframe / Points, ShapeColor / ShapeAppearance / Transparency -- no
    stripe, environment, zebra or curvature colouring.
  * The Curves workbench addon (installed here, NOT core FreeCAD) ships
    `ZebraTool`: a real zebra -- a `SoTexture2` stripe image transformed by
    `SoTexture2Transform` and projected with `SoTextureCoordinateEnvironment`
    (a genuine environment/reflection mapping, not a DIY shader).  It inserts
    those nodes into the ACTIVE VIEW's scene graph, so it is a GLOBAL effect
    on the whole view, and its stripe settings are its own UI sliders; this
    module drives those sliders (StripeWidth / Scale / Rotation) rather than
    building stripes itself.  Measured: the stripes DO reach a saved PNG
    (the module reports the fraction of pixels the texture changed).
    The tool's default Scale (=20) puts only ~4 stripes across the symmetric
    corner; this module uses Scale = 22 (~10 stripes), chosen so the stripe
    flow is legible at this feature size, and records the settings used.
  * The Curves addon also ships `ReflectLines` (reflection / silhouette
    lines as real geometry, via `Shape.reflectLines`).  Measured on this
    corner it returns 3 edges -- the outline only -- so it adds nothing to
    this judgement and is not used.
  * There is no curvature display anywhere in FreeCAD (Mesh / Points /
    Surface workbenches included).  So (b) is our own colour map: the
    corner's own B-spline surface is split into N x N EXACT sub-surfaces
    (`BSplineSurface.segment`, not a mesh, no faceting approximation) and
    each sub-face is painted -- through the standard per-face
    `ShapeAppearance` / `Part_ColorPerFace` mechanism -- with the exact
    shape-operator curvature at that cell's centre.  It is a colour map,
    and it is NOT called zebra.

TWO RENDERING FACTS THAT WOULD OTHERWISE MISLEAD (both measured, both
handled below):

  * Silk's control-grid coin nodes hang off the view provider's RootNode
    ABOVE FreeCAD's visibility switch: setting `ViewObject.Visibility =
    False` on every object still leaves the green/cyan/orange control-grid
    lines in the image.  `_quiesce()` therefore also turns the objects' own
    display toggles (ShowGrid / ShowPolygon / ShowCurve) off.
  * `ZebraTool` installs its texture on the ACTIVE document's view.  If a
    different document is active, the render shows no stripes at all.
    `render_zebra()` activates the document being rendered first.

MANUAL-ONLY: the file name is not `test_*.py`, so `Tests/suite.py` does not
discover it.  `Tests/test_continuity_instrument.py` asserts this module
imports, exposes `main`, and carries `MANUAL`; nothing else in the suite runs
it.  Nothing here is a production object or a fix.

Run (live GUI over XML-RPC, or in a GUI FreeCAD):

    import Tests.g2_corner_roll_visual as v; v.main()
"""

import math
import os

import FreeCAD
import Part

import Tests.silk_nurbs as SN
from SilkWorkflowOps import create_corner_blend
from Tests import cube_corner_model as ccm
from Tests.g2_corner_roll_measure import CONFIGS, principal_curvatures

MANUAL = True

# Where the PNGs go.  Gitignored scratch, the same home the runner's
# --save uses: the owner can open them from there.
OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Resources", "Test_files", "_inspect")

IMAGE_SIZE = (1600, 1200)          # (width, height) pixels, every image
BACKGROUND = "White"               # the same background for every image, so
                                   # the plain and zebra renders differ only
                                   # by the stripes

# The two setback settings under the owner's eye, by their `CONFIGS` names in
# the measurement module (one spelling of the setbacks, not two).  The
# measure module's third variant (`asymmetric_axis`) reads "one direction
# large, one small" a different way; it is a robustness variant of the
# NUMBER, not a second picture for this judgement.
RENDER_CONFIGS = ("symmetric", "asymmetric")

# --- the camera (see the module docstring) --------------------------------
CAMERA_TARGET = FreeCAD.Vector(0.05, 0.05, 0.05)
CAMERA_DIRECTION = FreeCAD.Vector(1.0, 1.0, 1.0)
CAMERA_ORIENTATION = (0.70710677, -0.70710677, 0.0, 2.186276)
CAMERA_DISTANCE = 0.9
CAMERA_HEIGHT = 0.42
CAMERA_FAR = 3.0

# The corner is drawn in a colour of its own so it is unmistakable in the
# context render; the three strips keep their default green.  A display
# choice, not data.
CORNER_RGB = (0.92, 0.55, 0.15)

# --- the colour maps ------------------------------------------------------
N_CELLS = 32                       # 32 x 32 = 1024 exact sub-faces per map

# Ratio map: the value is |k1| / |k2| (the anisotropy magnitude, the same
# reading #118 publishes).  The scale is FIXED at [1, 6] for the ratio map of
# BOTH configs so the two images are comparable; cells beyond 6 are clamped
# and counted in the report.
RATIO_LO, RATIO_HI = 1.0, 6.0
RATIO_STOPS = [
    (0.00, (0.10, 0.20, 0.55)),    # 1.0  deep blue   -- isotropic
    (0.25, (0.10, 0.60, 0.70)),    # 2.25 teal
    (0.50, (0.30, 0.75, 0.30)),    # 3.5  green
    (0.75, (0.95, 0.80, 0.20)),    # 4.75 yellow
    (1.00, (0.85, 0.15, 0.10)),    # 6.0  red        -- the most anisotropic
]

# Gaussian-curvature map: the SIGN of k1*k2 is what separates a saddle from a
# dome, so this map is diverging about 0 and its scale is symmetric in log
# space, fixed for both configs:  t = 0.5 * (1 + sign(K) * log10(1 + |K|) /
# log10(1 + 99)).  K = 0 -> white, K > 0 (both directions curve the same way,
# a dome) -> blue, K < 0 (the two directions curve opposite ways, a saddle)
# -> red.  Clamped at |K| = 99 /mm^2.
GAUSS_KMAX = 99.0
GAUSS_STOPS = [
    (0.0, (0.85, 0.20, 0.12)),     # saddle (K <= -99)
    (0.5, (0.97, 0.97, 0.95)),     # flat / K = 0
    (1.0, (0.15, 0.30, 0.75)),     # dome (K >= +99)
]

# --- the zebra settings (the Curves ZebraTool's own sliders) --------------
ZEBRA_STRIPE_WIDTH = 25    # slider 1: black run, in px of the stripe image
ZEBRA_SCALE = 22           # slider 2: stripe frequency (tool default is 20)
ZEBRA_ROTATION = 157       # slider 3: stripe rotation (tool default)


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _gui_view(doc_name):
    """The 3D view of `doc_name`, made active (the zebra tool needs that)."""
    import FreeCADGui as Gui
    FreeCAD.setActiveDocument(doc_name)
    return Gui.getDocument(doc_name).ActiveView


def _unit(vec):
    """A unit copy of `vec` (Base.Vector has no `normalized()` here)."""
    length = vec.Length
    return FreeCAD.Vector(vec.x / length, vec.y / length, vec.z / length)


def _ramp(stops, t):
    """Piecewise-linear RGB from a list of (position, (r, g, b))."""
    t = min(1.0, max(0.0, t))
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        if t <= p1:
            f = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
            return tuple(c0[k] + f * (c1[k] - c0[k]) for k in range(3))
    return stops[-1][1]


def _material(rgb):
    """An `App::Material` for one map cell.

    Diffuse and ambient both take the colour, specular is off.  An unlit
    variant (diffuse and ambient black, emissive = the colour) was measured
    first: FreeCAD's Part view provider does not carry EmissiveColor through
    on this build, so it rendered washed out and is not used.
    """
    m = FreeCAD.Material()
    m.DiffuseColor = (rgb[0], rgb[1], rgb[2], 1.0)
    m.AmbientColor = (rgb[0], rgb[1], rgb[2], 1.0)
    m.SpecularColor = (0.0, 0.0, 0.0, 1.0)
    return m


def _ratio_colour(k1, k2):
    r = abs(k1) / abs(k2) if abs(k2) > 1e-12 else float("inf")
    return _ramp(RATIO_STOPS, (r - RATIO_LO) / (RATIO_HI - RATIO_LO)), r


def _gauss_colour(k1, k2):
    K = k1 * k2
    u = (math.copysign(1.0, K) if K else 0.0) \
        * math.log10(1.0 + abs(K)) / math.log10(1.0 + GAUSS_KMAX)
    return _ramp(GAUSS_STOPS, 0.5 * (u + 1.0)), K


# ---------------------------------------------------------------------------
# the fixture and the two corners
# ---------------------------------------------------------------------------

def _quiesce(doc):
    """Leave nothing but the object a caller then shows.

    `Visibility = False` alone is NOT enough: Silk's control-grid coin nodes
    are appended to the view provider's RootNode, above FreeCAD's visibility
    switch, so the grids keep drawing (measured -- a view with every object
    invisible still renders the green/cyan/orange grid lines).  The objects'
    own display toggles are what actually removes them.
    """
    for o in doc.Objects:
        for prop in ("ShowGrid", "ShowPolygon", "ShowCurve"):
            if getattr(o, prop, None) is not None:
                setattr(o, prop, False)
        if o.ViewObject is not None:
            o.ViewObject.Visibility = False
    doc.recompute()


def _only(doc, *names):
    for o in doc.Objects:
        if o.ViewObject is not None:
            o.ViewObject.Visibility = (o.Name in names)


def set_camera(view):
    """Frame the corner with the module's fixed camera.  Orthographic."""
    from pivy import coin
    view.setCameraType("Orthographic")
    cam = view.getCameraNode()
    d = _unit(CAMERA_DIRECTION)
    p = CAMERA_TARGET - d * CAMERA_DISTANCE
    cam.position.setValue(coin.SbVec3f(p.x, p.y, p.z))
    cam.orientation.setValue(coin.SbRotation(coin.SbVec3f(
        CAMERA_ORIENTATION[0], CAMERA_ORIENTATION[1], CAMERA_ORIENTATION[2]),
        CAMERA_ORIENTATION[3]))
    cam.focalDistance.setValue(CAMERA_DISTANCE)
    cam.nearDistance.setValue(0.0)
    cam.farDistance.setValue(CAMERA_FAR)
    cam.height.setValue(CAMERA_HEIGHT)
    view.redraw()


def build_corner(doc_name, splits):
    """Build the fixture in a fresh scratch document, write `splits`, build
    the corner from the strips as rebuilt.

    `splits` is {patch name: (USplit1, VSplit1)} -- the band widths Silk
    reads off each patch, i.e. the setbacks.  The patches are written FIRST
    and the document recomputes (patches -> auto-updated strips), so the
    corner assembled is the one the widths describe.
    """
    if doc_name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(doc_name)          # only our own scratch doc
    doc = FreeCAD.newDocument(doc_name)
    ccm.build_cube_corner_model(doc)
    for patch_name, (usplit1, vsplit1) in splits.items():
        p = doc.getObject(patch_name)
        p.USplit1 = usplit1
        p.VSplit1 = vsplit1
    doc.recompute()
    FreeCAD.setActiveDocument(doc.Name)
    strips = [doc.getObject(n) for n in ("B_AB", "B_BC", "B_CA")]
    corner = create_corner_blend(*strips)
    doc.recompute()
    return doc, strips, corner


# ---------------------------------------------------------------------------
# the curvature colour map
# ---------------------------------------------------------------------------

def curvature_map(doc, corner, kind, n_cells=N_CELLS):
    """Paint the corner's own surface with `kind` in {"ratio", "gauss"}.

    The corner's B-spline is cut into n_cells x n_cells sub-surfaces with
    `BSplineSurface.segment` (exact -- the same surface, re-parameterised;
    nothing is meshed) and each sub-face takes the colour of the exact
    shape-operator curvature at its centre.  Returns (object, values, stats).
    """
    name = "RollViz_%s" % kind
    if name in [o.Name for o in doc.Objects]:
        doc.removeObject(name)
    net = SN.NurbsSurface.from_flat(list(corner.Poles),
                                    list(corner.Weights) or [1.0] * 36,
                                    6, 6, SN.KNOTS_6, SN.KNOTS_6)
    surf = corner.Shape.Face1.Surface
    faces, colours, ratios, gauss = [], [], [], []
    for i in range(n_cells):
        for j in range(n_cells):
            s = surf.copy()
            s.segment(i / float(n_cells), (i + 1) / float(n_cells),
                      j / float(n_cells), (j + 1) / float(n_cells))
            faces.append(Part.Face(s))
            k1, k2 = principal_curvatures(net, (i + 0.5) / n_cells,
                                          (j + 0.5) / n_cells)
            if kind == "ratio":
                rgb, value = _ratio_colour(k1, k2)
            else:
                rgb, value = _gauss_colour(k1, k2)
            colours.append(rgb)
            (ratios if kind == "ratio" else gauss).append(value)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = Part.Compound(faces)
    doc.recompute()
    obj.ViewObject.ShapeAppearance = [_material(c) for c in colours]
    obj.ViewObject.DisplayMode = "Shaded"        # no facet edge lines
    if kind == "ratio":
        finite = [v for v in ratios if math.isfinite(v)]
        stats = {"cells": len(ratios), "clamped": RATIO_HI,
                 "clamped_cells": sum(1 for v in ratios if v > RATIO_HI),
                 "min": min(finite) if finite else None,
                 "median": sorted(finite)[len(finite) // 2] if finite
                 else None,
                 "max": max(finite) if finite else None}
    else:
        neg = sum(1 for v in gauss if v < 0.0)
        stats = {"cells": len(gauss), "min": min(gauss), "max": max(gauss),
                 "saddle_cells": neg,
                 "saddle_fraction": neg / float(len(gauss))}
    return obj, (ratios if kind == "ratio" else gauss), stats


def draw_legend(path, stops, ticks, title):
    """Write a colour-bar PNG with tick labels, so a colour map can be read.

    Drawn with Qt (available wherever FreeCAD's GUI is), not with a 3D view:
    a 3D render cannot carry its own legend.
    """
    from PySide import QtCore, QtGui
    width, height = 460, 110
    bar_x, bar_y, bar_w, bar_h = 20, 30, 400, 30
    img = QtGui.QImage(width, height, QtGui.QImage.Format_RGB32)
    img.fill(QtGui.QColor(255, 255, 255))
    painter = QtGui.QPainter(img)
    for i in range(bar_w):
        rgb = _ramp(stops, i / float(bar_w - 1))
        painter.setPen(QtGui.QColor(int(255 * rgb[0]), int(255 * rgb[1]),
                                    int(255 * rgb[2])))
        painter.drawLine(bar_x + i, bar_y, bar_x + i, bar_y + bar_h)
    painter.setPen(QtGui.QColor(0, 0, 0))
    painter.drawRect(bar_x, bar_y, bar_w, bar_h)
    painter.drawText(bar_x, 12, title)
    for t, label in ticks:
        x = bar_x + int(round(t * (bar_w - 1)))
        painter.drawLine(x, bar_y + bar_h, x, bar_y + bar_h + 5)
        painter.drawText(x - 30, bar_y + bar_h + 8, 60, 16,
                         QtCore.Qt.AlignHCenter, label)
    painter.end()
    img.save(path)
    return path


def _ratio_ticks():
    out = []
    for t in (0.0, 0.25, 0.5, 0.75, 1.0):
        out.append((t, "%.2f" % (RATIO_LO + t * (RATIO_HI - RATIO_LO))))
    return out


def _gauss_ticks():
    out = []
    for t in (0.0, 0.25, 0.5, 0.75, 1.0):
        u = 2.0 * t - 1.0
        if u == 0.0:
            out.append((t, "0"))
            continue
        magnitude = math.pow(10.0, abs(u) * math.log10(1.0 + GAUSS_KMAX))
        out.append((t, "%s%.4g" % ("-" if u < 0 else "+", magnitude - 1.0)))
    return out


# ---------------------------------------------------------------------------
# the zebra view
# ---------------------------------------------------------------------------

def report_renderer():
    """What this FreeCAD build offers for surface inspection -- measured.

    Returns a dict; the strings are printed by `main()` and are the honest
    answer to "is there a zebra / reflective analysis view here?".
    """
    zebra = None
    try:
        from freecad.Curves import ZebraTool        # noqa: F401
        zebra = "Curves workbench addon: ZebraTool (environment-mapped " \
                "stripe texture on the active view; not core FreeCAD)"
    except Exception as exc:                        # noqa: BLE001
        zebra = "absent (%s: %s)" % (type(exc).__name__, exc)
    reflect = None
    try:
        import freecad.Curves.ReflectLinesFP as _RL    # noqa: F401
        reflect = "Curves workbench addon: ReflectLines (reflection / " \
                  "silhouette lines as geometry; measured 3 edges -- the " \
                  "outline only -- on this corner, so unused)"
    except Exception as exc:                        # noqa: BLE001
        reflect = "absent (%s: %s)" % (type(exc).__name__, exc)
    return {
        "core_zebra": "none: FreeCAD core has no zebra / reflection / "
                      "curvature display mode",
        "zebra_tool": zebra,
        "reflect_lines": reflect,
        "curvature_display": "none anywhere in FreeCAD: the (b) maps are our "
                             "own per-face colouring of exact sub-surfaces",
    }


def render_zebra(doc, corner, path, plain_path):
    """Render the corner with the Curves ZebraTool on, at the module's
    stripe settings, and report whether the texture reached the image.

    Returns {"available": bool, "path": str or None, "stripe_width": ...,
             "scale": ..., "rotation": ..., "pixels_changed": float or None}.
    """
    _only(doc, corner.Name)
    view = _gui_view(doc.Name)
    set_camera(view)
    try:
        from freecad.Curves import ZebraTool
    except Exception as exc:                      # noqa: BLE001
        return {"available": False, "reason": "%s: %s" % (type(exc).__name__,
                                                          exc),
                "path": None, "pixels_changed": None}
    z = ZebraTool.zebra()            # __init__ installs the coin nodes
    try:
        z.changeSlide_1(ZEBRA_STRIPE_WIDTH)
        z.changeSlide_2(ZEBRA_SCALE)
        z.changeSlide_3(ZEBRA_ROTATION)
        view.redraw()
        view.saveImage(path, IMAGE_SIZE[0], IMAGE_SIZE[1], BACKGROUND)
    finally:
        # `quit()` also closes the task panel; we only want the nodes gone.
        z.coinQuit()
        ZebraTool.ZebraTool.active = False
    return {"available": True, "path": path,
            "stripe_width": ZEBRA_STRIPE_WIDTH, "scale": ZEBRA_SCALE,
            "rotation": ZEBRA_ROTATION,
            "pixels_changed": _pixels_differing(plain_path, path)}


def _pixels_differing(path_a, path_b, step=4):
    """Fraction of sampled pixels that differ between two saved PNGs."""
    from PySide import QtGui
    a = QtGui.QImage(path_a)
    b = QtGui.QImage(path_b)
    if a.isNull() or b.isNull() or a.size() != b.size():
        return None
    changed = total = 0
    for y in range(0, a.height(), step):
        for x in range(0, a.width(), step):
            total += 1
            if a.pixel(x, y) != b.pixel(x, y):
                changed += 1
    return changed / float(total)


# ---------------------------------------------------------------------------
# one config
# ---------------------------------------------------------------------------

def render_config(name, splits, out_dir, cells=N_CELLS):
    """Build one config, write its five PNGs, return its record."""
    doc, strips, corner = build_corner("rollviz_" + name, splits)
    rec = {"name": name, "splits": splits, "paths": {}, "stats": {},
           "bbox": None, "centre": None, "zebra": None}
    if corner is None:
        rec["refused"] = True
        return rec
    bb = corner.Shape.BoundBox
    rec["bbox"] = (bb.XLength, bb.YLength, bb.ZLength, bb.ZMin)
    _quiesce(doc)
    corner.ViewObject.ShapeColor = CORNER_RGB
    view = _gui_view(doc.Name)
    set_camera(view)

    def shot(key, target, *names):
        _only(doc, *names)
        view.redraw()
        path = os.path.join(out_dir, "corner_roll_%s_%s.png" % (name, target))
        view.saveImage(path, IMAGE_SIZE[0], IMAGE_SIZE[1], BACKGROUND)
        rec["paths"][key] = path
        return path

    plain = shot("shaded", "1_shaded", corner.Name)
    shot("shaded_strips", "2_shaded_with_strips",
         corner.Name, "B_AB", "B_BC", "B_CA")

    legend_ratio = os.path.join(out_dir, "corner_roll_legend_ratio.png")
    legend_gauss = os.path.join(out_dir, "corner_roll_legend_gauss.png")

    for kind, target in (("ratio", "3_ratio"), ("gauss", "4_gauss")):
        obj, _values, stats = curvature_map(doc, corner, kind, cells)
        rec["stats"][kind] = stats
        shot(kind, target, obj.Name)

    # the #118 reading at the junction, for the pictures to sit beside
    net = SN.NurbsSurface.from_flat(list(corner.Poles),
                                    list(corner.Weights) or [1.0] * 36,
                                    6, 6, SN.KNOTS_6, SN.KNOTS_6)
    k1, k2 = principal_curvatures(net, 0.5, 0.5)
    rec["centre"] = (k1, k2, abs(k1) / abs(k2) if abs(k2) > 1e-12 else None)

    rec["zebra"] = render_zebra(doc, corner, os.path.join(
        out_dir, "corner_roll_%s_5_zebra.png" % name), plain)
    if rec["zebra"].get("path"):
        rec["paths"]["zebra"] = rec["zebra"]["path"]
    rec["legends"] = [legend_ratio, legend_gauss]
    return rec


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def print_renderer(renderer):
    print("WHAT THIS FREECAD OFFERS (measured, FreeCAD %s)"
          % ".".join(FreeCAD.Version()[:3]))
    for key in ("core_zebra", "zebra_tool", "reflect_lines",
                "curvature_display"):
        print("  %-18s %s" % (key + ":", renderer[key]))
    print()


def print_camera():
    print("CAMERA (identical for every image and both configs)")
    p = CAMERA_TARGET - _unit(CAMERA_DIRECTION) * CAMERA_DISTANCE
    print("  orthographic, target (%.2f, %.2f, %.2f) mm, direction (1, 1, 1),"
          % (CAMERA_TARGET.x, CAMERA_TARGET.y, CAMERA_TARGET.z))
    print("  camera position (%.4f, %.4f, %.4f) mm" % (p.x, p.y, p.z))
    print("  orientation quaternion %s, focalDistance %.2f mm, view height "
          "%.2f mm" % (CAMERA_ORIENTATION, CAMERA_DISTANCE, CAMERA_HEIGHT))
    print("  %d x %d px, background %r, per-face colouring of the corner's"
          % (IMAGE_SIZE[0], IMAGE_SIZE[1], BACKGROUND))
    print("  own B-spline surface at %d x %d exact sub-faces"
          % (N_CELLS, N_CELLS))
    print()


def print_config(rec):
    print("=== %s ===" % rec["name"])
    print("  setbacks (patch: USplit1 / VSplit1): %s" % (rec["splits"],))
    if rec.get("refused"):
        print("  CORNER BUILD REFUSED -- nothing rendered")
        print()
        return
    x, y, z, zmin = rec["bbox"]
    print("  corner: 36 poles, 1 face, bounding box %.3f x %.3f x %.3f mm"
          % (x, y, z))
    if zmin < -1e-9:
        print("    (it dips %.4f mm below the z = 0 patch plane)" % zmin)
    print("  IMAGES (the same camera for all of them):")
    for key, label in (("shaded", "a  shaded, corner alone"),
                       ("shaded_strips", "a  shaded, corner + 3 strips"),
                       ("ratio", "b  curvature ratio k_max/k_min"),
                       ("gauss", "b  Gaussian curvature k_max*k_min"),
                       ("zebra", "c  zebra stripes")):
        path = rec["paths"].get(key)
        print("    %-34s %s" % (label, path or "(not written)"))
    for p in rec["legends"]:
        print("    %-34s %s" % ("   colour legend", p))
    print()
    r = rec["stats"]["ratio"]
    print("  numbers behind the colour maps (%d cell centres, %d x %d exact"
          % (r["cells"], N_CELLS, N_CELLS))
    print("  shape-operator curvature; the maps are the picture of these):")
    print("    ratio |k1|/|k2|: min %.3f  median %.3f  max %.3f  (%d cells "
          "off the %.1f end of the scale)"
          % (r["min"], r["median"], r["max"], r["clamped_cells"],
             r["clamped"]))
    g = rec["stats"]["gauss"]
    print("    gaussian k1*k2: min %+.3f  max %+.3f /mm^2" % (g["min"],
                                                             g["max"]))
    print("    cells with k1*k2 < 0 (the two directions curve opposite ways):"
          " %d of %d = %.1f %% of the surface"
          % (g["saddle_cells"], g["cells"], 100.0 * g["saddle_fraction"]))
    k1, k2, ratio = rec["centre"]
    print("    junction centre (uv 0.50, 0.50): k_max %+.4f, k_min %+.4f, "
          "ratio %.3f" % (k1, k2, ratio))
    zb = rec["zebra"]
    if zb.get("available"):
        print("    zebra: StripeWidth %s, Scale %s, Rotation %s; the stripe "
              "texture changed %.1f %% of the sampled pixels"
              % (zb["stripe_width"], zb["scale"], zb["rotation"],
                 100.0 * (zb["pixels_changed"] or 0.0)))
    else:
        print("    zebra: NOT AVAILABLE (%s)" % zb.get("reason"))
    print()


def main(out_dir=None, cells=N_CELLS):
    """Render both setback settings and print where the images are."""
    out_dir = out_dir or OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    print("corner-roll VISUAL check (ticket #118): does the asymmetric "
          "setback LOOK like a roll?")
    print("No reading is asserted here -- the images are the evidence and "
          "the judgement is the owner's.")
    print()
    print_renderer(report_renderer())
    print_camera()
    draw_legend(os.path.join(out_dir, "corner_roll_legend_ratio.png"),
                RATIO_STOPS, _ratio_ticks(),
                "curvature ratio |k_max| / |k_min|  (1 = round)")
    draw_legend(os.path.join(out_dir, "corner_roll_legend_gauss.png"),
                GAUSS_STOPS, _gauss_ticks(),
                "Gaussian curvature k_max * k_min  (/mm^2)")
    results = []
    for name in RENDER_CONFIGS:
        results.append(render_config(name, CONFIGS[name], out_dir, cells))
    for rec in results:
        print_config(rec)
    print("READING")
    print("  symmetric corner bounding box %.3f mm, asymmetric %.3f mm: the"
          % (results[0]["bbox"][0] if results[0]["bbox"] else 0.0,
             results[1]["bbox"][0] if results[1]["bbox"] else 0.0))
    print("  setback IS the corner's size, so at one camera the asymmetric")
    print("  corner fills more of the frame.  Compare shape, not area.")
    for d in list(FreeCAD.listDocuments()):
        if d.startswith("rollviz_"):
            FreeCAD.closeDocument(d)        # our own scratch documents only
    return {"renderer": report_renderer(), "configs": results,
            "out_dir": out_dir}


if __name__ == "__main__":
    main()
