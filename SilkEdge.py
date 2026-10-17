"""
SilkEdge — single FeaturePython.
Sketch(es) in → 4 poles out → cubic curve + polygon for display.
Sketches linked via Sketches property (a Part::FeaturePython cannot nest at
object level; the GUI tree groups them under the Edge via EdgeViewProvider.claimChildren, #52).
Display toggles: ShowCurve, ShowPolygon
"""

import FreeCAD
import Part
from FreeCAD import Gui
import ArachNURBS as AN
from SilkMachinery import set_grid_display
from popup import tipsDialog
import Silk_tooltips

tooltip = (Silk_tooltips.ControlPoly4_baseTip + Silk_tooltips.standardTipFooter)
moreInfo = (Silk_tooltips.ControlPoly4_baseTip + Silk_tooltips.ControlPoly4_moreInfo)

import os, Silk_dummy
path_Silk = os.path.dirname(Silk_dummy.__file__)
path_Silk_icons = os.path.join(path_Silk, "Resources", "Icons")
iconPath = path_Silk_icons + "/BoundarySpline.svg"


# ---- sketch classification (#90) -----------------------------------------
# One Edge is built three ways, and which way is decided by the SHAPES the
# user selected -- there is no mode property to keep in sync. This one
# classifier answers the panel's mode label, the ops layer's pre-check and
# Edge.execute, so none of them can disagree about what a selection means:
#   1 sketch, 3 visible lines      -> "3L"
#   1 sketch, one supported curve  -> "FirstElement"
#   2 sketches, both node          -> "2N"   (a circle + line, connected)
#   2 sketches, two profiles       -> "plan_elevation" (plan then elevation)
# Anything else is REFUSED by name, before anything is built. A node is
# the FIRST TWO elements = one circle + one line CONNECTED at a shared
# endpoint (sketch-local, the core's own tolerance); a circle + line pair
# that is not connected is refused for what it is, never read as 2N.
#
# The plan + elevation pair is the ControlPoly4_2X4P composition: the plan
# sketch (Sketches[0]) supplies the floor footprint, the elevation
# (Sketches[1]) supplies each pole's height along the plan plane's normal.

# The element types ControlPoly4_FirstElement can consume (ArachNURBS.py
# :2306-2344): a line, a circular arc, an elliptic arc, or a cubic
# B-spline with 4 poles. A full circle is deliberately NOT among them.
_VIEW_ELEMENT_TYPES = (
    "Part::GeomLineSegment",
    "Part::GeomArcOfCircle",
    "Part::GeomArcOfEllipse",
)

# The plan and elevation planes must be perpendicular: the elevation's
# height is the distance of its poles ALONG the plan plane's normal, which
# reads as a clean height only when the two planes meet at a right angle.
_PLANE_PERP_TOL = 1e-6


def _visible_geometry(sketch):
    """[(index, geometry)] of a sketch's visible (non-construction)
    elements -- exactly what ControlPoly4_3L / _FirstElement read."""
    return [(i, g) for i, g in enumerate(sketch.Geometry)
            if not sketch.getConstruction(i)]


def _is_bspline_view(geom):
    return (geom.TypeId == "Part::GeomBSplineCurve"
            and getattr(geom, "Degree", 0) == 3
            and getattr(geom, "NbPoles", 0) == 4)


def _is_view_element(geom):
    return geom.TypeId in _VIEW_ELEMENT_TYPES or _is_bspline_view(geom)


def _is_3l_sketch(sketch):
    """Exactly 3 visible lines -- the ControlPoly4_3L precondition."""
    vis = _visible_geometry(sketch)
    return len(vis) == 3 and all(
        g.TypeId == "Part::GeomLineSegment" for _i, g in vis)


def _is_first_element_sketch(sketch):
    """Exactly one visible element, of a type FirstElement can read."""
    vis = _visible_geometry(sketch)
    return len(vis) == 1 and _is_view_element(vis[0][1])


def _node_circle_and_line(sketch):
    """(circle, line) when the FIRST TWO elements are one part circle +
    one part line -- exactly the two elements ControlPoly4_2N reads
    (ArachNURBS.py:1994-1995, :2017-2018). Elements AFTER the first two
    are ignored by the core, so they are allowed here; None when the
    first two are not that pair."""
    if len(sketch.Geometry) < 2:
        return None
    g0, g1 = sketch.Geometry[0], sketch.Geometry[1]
    if {g0.TypeId, g1.TypeId} != {
            "Part::GeomCircle", "Part::GeomLineSegment"}:
        return None
    circle = g0 if g0.TypeId == "Part::GeomCircle" else g1
    line = g0 if g0.TypeId == "Part::GeomLineSegment" else g1
    return circle, line


def _node_is_connected(sketch):
    """Whether the first two elements are a circle + line pair whose
    circle centre sits on one of the line's endpoints -- the connection
    ControlPoly4_2N verifies in sketch-LOCAL coordinates with the core's
    own tolerance (ArachNURBS.py:2004-2008, :2027-2031)."""
    pair = _node_circle_and_line(sketch)
    if pair is None:
        return False
    circle, line = pair
    return bool(
        AN.equalVectors(line.StartPoint, circle.Center, AN.default_tol)
        or AN.equalVectors(line.EndPoint, circle.Center, AN.default_tol))


def _is_node_sketch(sketch):
    """A usable node: the first two elements are one circle + one line,
    CONNECTED at a shared endpoint. The core reads only Geometry[0] and
    Geometry[1], so extra elements after them do not disqualify the sketch
    (#90 review)."""
    return _node_is_connected(sketch)


def _unconnected_node(sketch):
    """True when the first two elements are a circle + line pair that is
    NOT connected (circle centre off the line) -- a pair that must be
    refused for what it is, never routed to 2N."""
    return (_node_circle_and_line(sketch) is not None
            and not _node_is_connected(sketch))


def _unconnected_node_refusal(sketches):
    """One refusal sentence when any sketch's first two elements are an
    UNCONNECTED circle + line pair, naming the offending sketch(es) and
    the reason; None when none of them is such a pair."""
    bad = [s for s in sketches if _unconnected_node(s)]
    if not bad:
        return None
    names = " and ".join(_sketch_name(s) for s in bad)
    if len(bad) == 1:
        return ("%s is a circle + line pair, but the circle centre is not "
                "on a line endpoint -- a node sketch connects its circle to "
                "the line at one of the line's endpoints" % names)
    return ("%s are circle + line pairs, but their circle centres are not "
            "on a line endpoint -- a node sketch connects its circle to the "
            "line at one of the line's endpoints" % names)


def _first_view_element(sketch):
    """The element ControlPoly4_FirstElement would pick: the first visible
    element, under the ArachNURBS type priority (cubic spline, elliptic
    arc, circular arc, line)."""
    vis = [g for _i, g in _visible_geometry(sketch)]
    for pick in (lambda g: _is_bspline_view(g),
                 lambda g: g.TypeId == "Part::GeomArcOfEllipse",
                 lambda g: g.TypeId == "Part::GeomArcOfCircle",
                 lambda g: g.TypeId == "Part::GeomLineSegment"):
        for g in vis:
            if pick(g):
                return g
    return None


def _sketch_kind(sketch):
    """'node' | '3L' | 'FirstElement' | None -- how `sketch` reads."""
    if _is_node_sketch(sketch):
        return "node"
    if _is_3l_sketch(sketch):
        return "3L"
    if _is_first_element_sketch(sketch):
        return "FirstElement"
    return None


def _sketch_name(sketch):
    return getattr(sketch, "Label", None) or getattr(sketch, "Name", "?")


def _kind_words(kind):
    return {"node": "circle + line node",
            "3L": "3 visible lines",
            "FirstElement": "one curve element",
            None: "neither a node nor a profile"}.get(kind, str(kind))


def _plane_normal(sketch):
    """World-space unit normal of `sketch`'s plane."""
    n = sketch.Placement.Rotation.multVec(FreeCAD.Vector(0, 0, 1))
    if n.Length > 0:
        n.normalize()
    return n


def _profile_poles(sketch, kind):
    """The 4 world poles `sketch` supplies as a plan/elevation profile.

    Mirrors ControlPoly4_3L / _FirstElement without creating a document
    object: classification runs on every panel refresh and must stay
    side-effect free. Used only to measure the elevation's height span.
    """
    mat = sketch.Placement.toMatrix()
    if kind == "3L":
        lines = [[mat.multiply(g.StartPoint), mat.multiply(g.EndPoint)]
                 for _i, g in _visible_geometry(sketch)]
        return list(AN.polyFromLineSet(lines, AN.default_tol))
    nurb = _first_view_element(sketch).toNurbs()
    nurb.increaseDegree(3)
    return [mat.multiply(nurb.getPole(k)) for k in (1, 2, 3, 4)]


def _height_span(poles, normal):
    """Max - min of a pole set's height along `normal`."""
    hs = [p.dot(normal) for p in poles]
    return max(hs) - min(hs)


def classify_sketches(sketches):
    """(mode, detail) for a selection of sketches.

    mode is '3L', 'FirstElement', '2N', 'plan_elevation', or None when the
    selection cannot build an Edge -- then detail is the refusal reason,
    naming the offending sketches (or the two plane normals). detail is
    always one human sentence, so the panel label and the console error
    can both use it verbatim.
    """
    sketches = list(sketches or [])
    n = len(sketches)
    if n == 0:
        return None, "no sketches selected"
    if n > 2:
        return None, ("%d sketches selected -- an Edge takes at most 2 "
                      "(one profile, one plan + elevation, or two nodes)"
                      % n)

    if n == 1:
        reason = _unconnected_node_refusal(sketches)
        if reason:
            return None, reason
        kind = _sketch_kind(sketches[0])
        if kind == "3L":
            return "3L", "3L (one sketch)"
        if kind == "FirstElement":
            return "FirstElement", "FirstElement (one sketch)"
        return None, ("%s is not a usable edge sketch (%s) -- a one-sketch "
                      "Edge needs exactly 3 visible lines, or one supported "
                      "curve element (line, arc, elliptic arc, or cubic "
                      "spline)" % (_sketch_name(sketches[0]),
                                   _kind_words(kind)))

    plan, elevation = sketches[0], sketches[1]
    kp, ke = _sketch_kind(plan), _sketch_kind(elevation)
    if kp == "node" and ke == "node":
        return "2N", "2N (two sketches)"

    # #90 review: a circle + line pair that is not connected must be
    # refused for what it IS (naming the sketch and the reason), in any
    # placement -- next to a node, a profile, or another such pair.
    reason = _unconnected_node_refusal(sketches)
    if reason:
        return None, reason

    profiles = ("3L", "FirstElement")
    if kp in profiles and ke in profiles:
        np_ = _plane_normal(plan)
        ne_ = _plane_normal(elevation)
        dot = np_.dot(ne_)
        if abs(dot) > _PLANE_PERP_TOL:
            return None, (
                "the two sketch planes are not perpendicular "
                "(normal (%.3f, %.3f, %.3f) . normal (%.3f, %.3f, %.3f) "
                "= %.3f) -- a plan + elevation Edge composes two "
                "perpendicular planes; rotate one profile or use two node "
                "sketches" % (np_.x, np_.y, np_.z,
                              ne_.x, ne_.y, ne_.z, dot))
        span = _height_span(_profile_poles(elevation, ke), np_)
        if span <= AN.default_tol:
            return None, (
                "the elevation sketch (%s) is flat along the plan plane's "
                "normal (height span %.2e) -- an elevation must rise above "
                "the plan plane" % (_sketch_name(elevation), span))
        return "plan_elevation", ("plan + elevation (%s, %s)"
                                  % (kp, ke))

    return None, (
        "%s (%s) and %s (%s) cannot form an Edge -- a two-sketch Edge "
        "needs either two node sketches (each a circle + line) or two "
        "profile sketches (a plan + an elevation)"
        % (_sketch_name(plan), _kind_words(kp),
           _sketch_name(elevation), _kind_words(ke)))


# ---- build helpers -------------------------------------------------------

def _read_legacy(doc, sketches, mode):
    """(poles, weights, legs) from a 3L / FirstElement / 2N ControlPoly4
    built on a throw-away object, removed before returning."""
    if mode == "2N":
        build, args = AN.ControlPoly4_2N, (sketches[0], sketches[1])
    elif mode == "3L":
        build, args = AN.ControlPoly4_3L, (sketches[0],)
    else:
        build, args = AN.ControlPoly4_FirstElement, (sketches[0],)
    dummy = doc.addObject("Part::FeaturePython", "_edge_tmp")
    try:
        build(dummy, *args)
        dummy.recompute()
        return list(dummy.Poles), list(dummy.Weights), list(dummy.Legs)
    finally:
        doc.removeObject(dummy.Name)


def _fill_view_poly4(obj, sketch):
    """Populate `obj` with the 4-pole ControlPoly4 a single profile sketch
    supplies (3L or FirstElement)."""
    if _is_3l_sketch(sketch):
        AN.ControlPoly4_3L(obj, sketch)
    else:
        AN.ControlPoly4_FirstElement(obj, sketch)
    obj.recompute()


def _compose_plan_elevation(doc, plan, elevation):
    """(poles, weights, legs) from ControlPoly4_2X4P: each plan pole
    lifted off the plan plane along its normal by the elevation pole's
    height. The two profile ControlPoly4s and the composer live on
    throw-away objects, all removed before returning."""
    made = []
    try:
        plan_obj = doc.addObject("Part::FeaturePython", "_edge_plan")
        made.append(plan_obj)
        _fill_view_poly4(plan_obj, plan)
        elev_obj = doc.addObject("Part::FeaturePython", "_edge_elev")
        made.append(elev_obj)
        _fill_view_poly4(elev_obj, elevation)
        comp = doc.addObject("Part::FeaturePython", "_edge_compose")
        made.append(comp)
        AN.ControlPoly4_2X4P(comp, plan_obj, elev_obj)
        comp.recompute()
        return list(comp.Poles), list(comp.Weights), list(comp.Legs)
    finally:
        for obj in reversed(made):
            try:
                doc.removeObject(obj.Name)
            except Exception:
                pass


def _apply_edge_geometry(fp, poles, weights, legs):
    """Store the geometry and rebuild the display Shape -- geometry only.
    Empty poles/legs is the honest "nothing built" state.

    `Shape` is GEOMETRY ONLY (#108): the cubic curve, shown per ShowCurve.
    The control polygon used to be appended here as loose edges -- which
    is what put grid wires into every compound built from Silk objects. It
    is a DISPLAY concern now: the view provider draws it as a Coin node
    (SilkMachinery.set_grid_display reads fp.Legs / ShowPolygon), so it is
    not part of Shape, not exported, not selectable, and toggling
    ShowPolygon no longer changes Shape.
    """
    fp.Poles = list(poles)
    fp.Weights = list(weights)
    fp.Legs = list(legs)
    if fp.ShowCurve and len(poles) == 4:
        curve = Part.BSplineCurve()
        curve.buildFromPoles(list(poles))
        fp.Shape = curve.toShape()
    else:
        fp.Shape = Part.Shape()


class Edge:
    def __init__(self, obj, sketches):
        latest_version = "0.01"

        obj.addProperty("App::PropertyLinkList", "Sketches", "C1 - Inputs",
                        "source sketches").Sketches = sketches
        obj.addProperty("App::PropertyFloat", "tolerance", "C1 - Inputs",
                        "point-to-point connection tolerance").tolerance = AN.default_tol
        obj.addProperty("App::PropertyBool", "reverse", "C1 - Inputs",
                        "reverse the pole sequence").reverse = False
        obj.addProperty("App::PropertyBool", "ShowCurve", "S1 - Display",
                        "show the cubic curve").ShowCurve = True
        obj.addProperty("App::PropertyBool", "ShowPolygon", "S1 - Display",
                        "show the control polygon").ShowPolygon = True
        obj.addProperty("App::PropertyVectorList", "Poles", "C2 - Outputs", "Poles").Poles
        obj.addProperty("App::PropertyFloatList", "Weights", "C2 - Outputs", "Weights").Weights = [1.0] * 4
        obj.addProperty("Part::PropertyGeometryList", "Legs", "C2 - Outputs", "control segments").Legs
        obj.addProperty("App::PropertyString", "object_type", "C3 - Identifiers",
                        "workbench class").object_type = "Edge"
        obj.setEditorMode("object_type", 1)
        obj.addProperty("App::PropertyString", "object_version", "C3 - Identifiers",
                        "class version").object_version = latest_version
        obj.setEditorMode("object_version", 1)
        obj.addProperty("App::PropertyString", "internalName", "C3 - Identifiers",
                        "internal FreeCAD name").internalName = obj.Name
        obj.setEditorMode("internalName", 1)
        obj.Proxy = self
        self.execute(obj)

    def onDocumentRestored(self, obj):
        self.execute(obj)

    def onChanged(self, fp, prop):
        if prop in ("ShowCurve", "ShowPolygon", "reverse"):
            if 'Restore' not in fp.State:
                self.execute(fp)

    def execute(self, fp):
        if 'Restore' in fp.State:
            return

        sketches = list(fp.Sketches or [])
        mode, detail = classify_sketches(sketches)
        if mode is None:
            # #90: a selection the Edge cannot build is REFUSED loudly and
            # left empty -- never a half-built geometry. "no sketches" is
            # the one quiet case (a fresh or blank edge).
            if sketches:
                FreeCAD.Console.PrintError(
                    "Silk: Edge not built -- %s\n" % detail)
            _apply_edge_geometry(fp, [], [], [])
            return

        if mode == "plan_elevation":
            poles, weights, legs = _compose_plan_elevation(
                fp.Document, sketches[0], sketches[1])
        else:
            poles, weights, legs = _read_legacy(fp.Document, sketches, mode)
        if fp.reverse:
            poles = list(reversed(poles))
            weights = list(reversed(weights))
        _apply_edge_geometry(fp, poles, weights, legs)


class EdgeViewProvider:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return iconPath

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object
        self._refresh_grid(self.Object, vobj)

    def claimChildren(self):
        """Ticket #52: group this Edge's sketches under it in the tree.

        FreeCAD renders tree parent-child through the view provider's
        claimChildren (DocumentModel/Tree in the 1.x core), not through
        document-level grouping -- the datas-level Sketches link list is
        unchanged, so the Edge/Patch identity model is untouched. Only the
        Edge claims: an edge owns 1-2 sketches, while an edge can serve two
        patches, so a Patch must never claim a sketch here."""
        return list(self.Object.Sketches or [])

    def _refresh_grid(self, obj, vobj):
        """Draw the control polygon as a Coin node (#108).

        The polygon is no longer part of Shape (see _apply_edge_geometry);
        it is rebuilt here from the stored `Legs` and shown per ShowPolygon,
        in the Edge's own LineColor / LineWidth. Headless (no ViewObject)
        is a silent no-op."""
        if obj is None or vobj is None:
            return
        set_grid_display(self, vobj, list(getattr(obj, "Legs", None) or []),
                         bool(getattr(obj, "ShowPolygon", True)),
                         getattr(vobj, "LineColor", None),
                         getattr(vobj, "LineWidth", None))

    def onChanged(self, vobj, prop):
        """Cascade the Edge's tree visibility onto its sketches (#108).

        The Edge GROUPS its sketches in the tree (claimChildren, #52), but
        FreeCAD does not link their visibility: hiding the Edge used to
        leave its construction lines on screen, so the edge "disappeared"
        while its input stayed. Mirroring the Edge's own Visibility is what
        makes the group read as one object.

        RULE: a plain mirror, in both directions. If the user has hidden
        one sketch on its own, showing the Edge shows that sketch again --
        the Edge's visibility IS the group's, and per-sketch memory would
        be state no property carries and the tree does not show. The
        alternative (remember which sketches the user hid, and restore only
        the others on show) was rejected for exactly that reason: it would
        not survive save/reload, and it would make "hide the Edge" not mean
        "hide what it groups".

        Headless is safe: a sketch with no ViewObject is skipped, never an
        error.
        """
        if prop == "Visibility":
            self._mirror_sketch_visibility(vobj)
        elif prop in ("LineColor", "LineWidth"):
            self._refresh_grid(getattr(vobj, "Object", None), vobj)

    def _mirror_sketch_visibility(self, vobj):
        try:
            visible = bool(vobj.Visibility)
        except Exception:
            return
        for sketch in list(getattr(self.Object, "Sketches", None) or []):
            sk_vobj = getattr(sketch, "ViewObject", None)
            if sk_vobj is None:
                continue          # headless / not shown: nothing to mirror
            try:
                sk_vobj.Visibility = visible
            except Exception:
                pass

    def updateData(self, obj, prop):
        if prop in ("Legs", "Shape", "ShowPolygon"):
            self._refresh_grid(obj, getattr(self, "ViewObject", None))
        return True

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class CreateEdge:
    def GetResources(self):
        return {'Pixmap': iconPath, 'MenuText': 'Edge', 'ToolTip': tooltip}

    def Activated(self):
        sel = Gui.Selection.getSelectionEx()
        if len(sel) == 0:
            tipsDialog("Silk: Edge", moreInfo)
            return

        doc = FreeCAD.ActiveDocument
        selected = []
        for item in sel:
            obj = item.Object
            if obj.TypeId == "Sketcher::SketchObject":
                selected.append(obj)

        if not selected:
            FreeCAD.Console.PrintError("Silk: Edge requires at least one Sketch selected.\n")
            return

        # #90: refuse an unbuildable selection BEFORE anything is created --
        # 3+ sketches, a mixed node/view pair, two non-perpendicular planes,
        # a flat elevation, and a sketch that is neither shape.
        mode, detail = classify_sketches(selected)
        if mode is None:
            FreeCAD.Console.PrintError(
                "Silk: cannot create an Edge -- %s\n" % detail)
            return

        edge = doc.addObject("Part::FeaturePython", "Edge")
        Edge(edge, selected)
        EdgeViewProvider(edge.ViewObject)
        edge.ViewObject.LineWidth = 2.00
        edge.ViewObject.LineColor = (0.00, 1.00, 0.00)
        edge.ViewObject.PointSize = 4.00
        edge.ViewObject.PointColor = (0.00, 0.33, 1.00)
        doc.recompute()
        FreeCAD.Console.PrintMessage(f"Edge created: {edge.Name}\n")

    def IsActive(self):
        return Gui is not None


Gui.addCommand("Silk_CreateEdge", CreateEdge())
