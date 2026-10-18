"""
BoundarySpline save/restore, against upstream's ControlPoly4 (ticket #10).

The ticket's repro was: build a BoundarySpline in the live doc, save, reopen
-- "the object (or its links) does not restore correctly".  Reproduced here
as an instrument rather than a claim, over EVERY property the object carries,
with the same measurement applied to `ArachNURBS.ControlPoly4_3L` (the
upstream class BoundarySpline was built around, and the ticket's open
comparison question).

WHAT IT MEASURES.  Two FeaturePython objects on one triangle sketch, saved to
a temp `.FCStd`, the document closed, the file reopened:

  * every property value before vs after (pole coordinates to 9 significant
    digits, weights, the `Legs` geometry types, the `Sketch` link target,
    tolerance / reverse / object_type / object_version / internalName),
  * the live proxy class on both sides,
  * the proxy the FILE records (`<Python module=... class=.../>` in
    Document.xml) -- a lossy save is exactly a missing or wrong class there,
  * and the same after a full recompute of the restored document, because a
    restored object that then recomputes to something else is not restored.

The only property allowed to differ is `_ElementMapVersion`, which FreeCAD
drops on load (internal, transient, no geometry meaning).

MEASURED (2026-10-18, this build): nothing is lost on either object.  Both
declare their module/class, both restore a live proxy of that class, and all
values (including the spline's 4 poles and its 1-edge Shape, and
ControlPoly4_3L's 3 segment legs) come back identical, before and after the
recompute.  So upstream's behaviour on restore is the same as ours: the
ticket's premise does not reproduce, and this test is what keeps it that way.
"""

import os
import re
import tempfile
import zipfile

import FreeCAD
import Part
from FreeCAD import Base

from Tests.mcp_harness import check


def _triangle_sketch(doc, name="Sketch"):
    """A 3-visible-line sketch: the shape BoundarySpline's 3L path expects."""
    sk = doc.addObject("Sketcher::SketchObject", name)
    sk.addGeometry(Part.LineSegment(Base.Vector(0, 0, 0),
                                    Base.Vector(10, 0, 0)), False)
    sk.addGeometry(Part.LineSegment(Base.Vector(10, 0, 0),
                                    Base.Vector(10, 10, 0)), False)
    sk.addGeometry(Part.LineSegment(Base.Vector(10, 10, 0),
                                    Base.Vector(0, 5, 0)), False)
    doc.recompute()
    return sk


def _value(v):
    """One property, flattened to a comparable, printable form."""
    if isinstance(v, list):
        out = []
        for q in v:
            if isinstance(q, Base.Vector):
                out.append("(%.9g,%.9g,%.9g)" % (q.x, q.y, q.z))
            elif isinstance(q, float):
                out.append("%.12g" % q)
            else:
                out.append(getattr(q, "TypeId", None) or repr(q))
        return out
    if isinstance(v, Base.Vector):
        return "(%.9g,%.9g,%.9g)" % (v.x, v.y, v.z)
    if v is not None and not isinstance(v, (int, float, str, bool)):
        return getattr(v, "Name", None) or repr(v)
    return v


def snapshot(obj):
    """Every saved property of `obj`, plus its proxy and Shape."""
    out = {}
    for prop in obj.PropertiesList:
        if prop in ("ExpressionEngine", "Visibility", "Shape", "Proxy",
                    "Label2", "_ElementMapVersion"):
            continue
        try:
            out[prop] = _value(getattr(obj, prop))
        except Exception as exc:            # a property that will not read
            out[prop] = "ERR %s" % exc
    proxy = getattr(obj, "Proxy", None)
    out["__proxy"] = (None if proxy is None
                      else "%s.%s" % (type(proxy).__module__,
                                      type(proxy).__name__))
    try:
        shape = obj.Shape
        out["__shape"] = "%s edges=%d" % (shape.ShapeType, len(shape.Edges))
    except Exception as exc:
        out["__shape"] = "ERR %s" % exc
    return out


def save_and_reopen(doc, name):
    """Save `doc` to a temp file, close it, reopen; (path, new_doc)."""
    path = os.path.join(tempfile.mkdtemp(prefix="silk_bs_"), name + ".FCStd")
    doc.saveAs(path)
    FreeCAD.closeDocument(doc.Name)
    return path, FreeCAD.openDocument(path)


def _declared_proxies(path):
    """{object name: "module.class"} as recorded in the saved file."""
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("Document.xml").decode()
    out = {}
    for obj in re.finditer(r'<Object name="([^"]+)"', xml):
        name = obj.group(1)
        tail = xml[obj.start():obj.start() + 200000]
        prop = re.search(r'<Property name="Proxy".*?<Python[^>]*/>',
                         tail[:tail.find("</Object>") + 9], re.S)
        if prop is None:
            continue
        decl = re.search(r'module="([^"]*)" class="([^"]*)"', prop.group(0))
        if decl:
            out[name] = "%s.%s" % (decl.group(1), decl.group(2))
    return out


def _diff(before, after):
    return {k: (before.get(k), after.get(k))
            for k in set(before) | set(after)
            if before.get(k) != after.get(k)}


def test_boundaryspline_and_controlpoly4_round_trip(doc):
    """Build, save, reopen: neither object loses a property or its proxy.

    `ControlPoly4_3L` is measured beside it because the ticket leaves open
    how upstream behaves on restore -- if upstream restored correctly and
    BoundarySpline did not, matching upstream would be the fix.  Measured:
    they behave the same, so there is nothing to match or diverge from.
    """
    from ArachNURBS import ControlPoly4_3L
    from BoundarySpline import BoundarySpline

    errors, checks = [], []

    round_doc = FreeCAD.newDocument("bs_round_trip")
    sketch = _triangle_sketch(round_doc)
    bs = round_doc.addObject("Part::FeaturePython", "BoundarySpline")
    BoundarySpline(bs, sketch)
    cp = round_doc.addObject("Part::FeaturePython", "ControlPoly4_3L")
    ControlPoly4_3L(cp, sketch)
    round_doc.recompute()

    before = {"BoundarySpline": snapshot(bs), "ControlPoly4_3L": snapshot(cp)}
    if len(bs.Poles) != 4:
        errors.append("fixture is wrong: BoundarySpline has %d poles, want 4"
                      % len(bs.Poles))
    path, reopened = save_and_reopen(round_doc, "bs_round_trip")

    declared = _declared_proxies(path)
    for name, kind in (("BoundarySpline", "BoundarySpline.BoundarySpline"),
                       ("ControlPoly4_3L", "ArachNURBS.ControlPoly4_3L")):
        recorded = declared.get(name)
        checks.append("%s: file records proxy %r" % (name, recorded))
        check(recorded == kind,
              "%s: the saved file records proxy %r, want %r"
              % (name, recorded, kind), errors)

        restored = reopened.getObject(name)
        if restored is None:
            errors.append("%s: gone from the reopened document" % name)
            continue
        after = snapshot(restored)
        if after["__proxy"] != kind:
            errors.append("%s: restored with proxy %r, want %r"
                          % (name, after["__proxy"], kind))
        lost = _diff(before[name], after)
        checks.append("%s: %d properties compared, %d differ%s"
                      % (name, len(before[name]), len(lost),
                         (" (%s)" % sorted(lost)) if lost else ""))
        check(not lost, "%s: lost on reopen: %s" % (name, lost), errors)

    # a restored object that recomputes to something else is not restored
    reopened.recompute()
    for name in ("BoundarySpline", "ControlPoly4_3L"):
        restored = reopened.getObject(name)
        if restored is None:
            continue
        lost = _diff(before[name], snapshot(restored))
        checks.append("%s: recompute after reopen changes %d properties"
                      % (name, len(lost)))
        check(not lost,
              "%s: changed by a recompute after reopen: %s" % (name, lost),
              errors)

    FreeCAD.closeDocument(reopened.Name)
    try:
        os.remove(path)
    except OSError:
        pass
    return {"pass": not errors, "errors": errors, "checks": checks}


ALL_TESTS = [
    test_boundaryspline_and_controlpoly4_round_trip,
]
