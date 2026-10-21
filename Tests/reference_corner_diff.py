#!/usr/bin/env python3
"""Tests/reference_corner_diff.py -- the CONSTRUCTION DIFF instrument.

**What it answers.** "Is our corner the maintainer's corner?" -- by printing
his corner's complete object graph and ours side by side and naming every
structural difference in one line each. It replaces the vocabulary that has
drifted for three sessions ("rolled", "spiderweb", "fill", "smaller surface")
with artifacts that can be compared.

**The reference.** The tutorial files are TRACKED in this repo
(`Resources/Tutorial_Files/Silk CopyPasta/`), so the reference needs no GUI and
no fetch. A `.FCStd` is a zip; `Document.xml` holds every object, its proxy
class, every property value and its LINK graph, and `Poles` / `Weights` /
`Shape` payloads live in sibling members of the same zip. So the reference can
be read with the standard library alone -- no FreeCAD, no GUI, no RPC.
`--fetch 29` will still `git show` a copy out of `upstream/master` to /tmp if
the tracked file is ever missing or a pristine copy is wanted.

**The pick.** `--corner auto` (the default) chooses the corner whose TRIANGULAR
surface has the smallest area, computed OFFLINE from the stored control net
(a 6x4 cubic Bezier patch sampled on a 32x32 grid -- see `net_area`); ties are
broken by the corner's own position in its folder's stored order. The rule is
printed with the pick, because "the central one" (the owner's words) cannot be
resolved without a 3D view: on the cleaned-up file the eight rolled corners sit
on a symmetric ring and none of them is nearer the model's centre than the
others.

**Two modes.**

  offline (default -- stdlib only, works with FreeCAD closed)
      python3 Tests/reference_corner_diff.py --ref /tmp/cp29.FCStd
      python3 Tests/reference_corner_diff.py --ref /tmp/cp29.FCStd --list
      python3 Tests/reference_corner_diff.py --ref /tmp/cp29.FCStd --corner \
  CubicSurface_66_014 --leaves

  with the owner's running FreeCAD (the only run path -- never spawn a window)
      flock /tmp/silk_rpc.lock -c "python3 Tests/reference_corner_diff.py \\
  --ref /tmp/cp29.FCStd --ours"

  `--ours` builds OUR corner at the leader the reference uses, in a scratch
  document in the owner's GUI over XML-RPC, walks it the same way, prints the
  two graphs side by side, and names the structural differences. The scratch
  document is closed without saving. Reference documents already open in the
  GUI are read, never written and never closed.

**What it does NOT do.** It asserts nothing. It is an instrument: numbers plus
names. The parity question ("do OUR primitives reproduce his construction")
is the throwaway prototype's job -- `Tests/prototype_reference_corner.py`,
which answers it 0.000e+00 across all 20 corners of episode 28.

**MEASURED (episode 29, corner CubicSurface_66_014, the smallest triangular
net).** Seven named differences, the load-bearing three being: his 6x6 has 0
coincident pole pairs of 630 (the assembly never reads the member's collapsed
row) where ours has 15 and a collapsed side; ours then re-solves with
`smooth_degenerate_cap`, moving the 6x6 poles by 0.0352 mm on a 0.0625-extent
corner; and his triangular face is `CubicSurface_64` over the member net where
ours is a FreeCAD `Surface::Filling` over the member's three real edges.
"""

import argparse
import os
import struct
import sys
import zipfile
import xml.etree.ElementTree as ET

MANUAL = True

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for _p in (REPO, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The reference archives, by copy-pasta episode -- TRACKED in this repo, so the
# offline half never needs a fetch. `--fetch` reads one out of upstream/master.
UPSTREAM_PATHS = {
    "27": "Resources/Tutorial_Files/Silk CopyPasta/"
          "Silk_CopyPasta_27_First_Corner_Rolled.FCStd",
    "28": "Resources/Tutorial_Files/Silk CopyPasta/"
          "Silk_CopyPasta_28_Full_Blend_Solid_3X4.FCStd",
    "29": "Resources/Tutorial_Files/Silk CopyPasta/"
          "Silk_CopyPasta_29_Full_Blend_Solid_3X4_Clean_Up.FCStd",
}


def default_reference(tag="29"):
    """The tracked reference file for a copy-pasta episode."""
    return os.path.join(REPO, UPSTREAM_PATHS[tag])

RPC_HOST = os.environ.get("SILK_RPC_HOST", "127.0.0.1")
RPC_PORT = int(os.environ.get("SILK_RPC_PORT", "9875"))

# The proxy classes that ROOT a corner construction: the finished surface.
CORNER_ROOT_CLASSES = ("CubicSurface_66", "CubicNStarSurface_NStar66")


# ---------------------------------------------------------------------------
# The .FCStd reader (stdlib only)
# ---------------------------------------------------------------------------

class Node:
    """One document object: its identity, its links, its scalars, its net.

    `links` maps a property name to the list of object names it points at
    (Link, LinkList, LinkSub and LinkSubList all reduce to a name list --
    the sub-element names are geometry, and this instrument walks OBJECTS).
    `scalars` holds every numeric / boolean / short-string property, which is
    where the construction's choices live: `u` on a cut, `Corner` on the
    triangular member's grid, `adjust_0` / `adjust_1` / `reverse` on a
    subgrid, `Scale0` / `Scale1` on a bridge curve.
    """

    __slots__ = ("name", "label", "cls", "links", "scalars", "poles",
                 "weights", "has_shape", "folder")

    def __init__(self, name):
        self.name = name
        self.label = None
        self.cls = None
        self.links = {}
        self.scalars = {}
        self.poles = None
        self.weights = None
        self.has_shape = False
        self.folder = []

    def coincident_pairs(self, tol=1e-7):
        """How many pole PAIRS coincide -- the degeneracy census.

        A collapsed row of six poles is 15 pairs; a regular net is 0. This is
        the number that says whether an assembly ever read a degenerate row.
        """
        p = self.poles or []
        n = 0
        for i in range(len(p)):
            for j in range(i):
                d = tuple(p[i][k] - p[j][k] for k in range(3))
                if (d[0] * d[0] + d[1] * d[1] + d[2] * d[2]) <= tol * tol:
                    n += 1
        return n

    def __repr__(self):
        return "<%s %s>" % (self.cls or "?", self.name)


def _child_value(prop_el, tag):
    """The `value` attribute of the first child element named `tag`."""
    child = prop_el.find(tag)
    return None if child is None else child.get("value")


def _link_targets(prop_el):
    """The object names a Link / LinkList / LinkSub / LinkSubList points at.

    Sub-element names are deliberately dropped: this instrument compares
    OBJECTS. (A `LinkSubList` names its object in `obj=`; the other three
    forms use `value=`.)
    """
    out = []
    for child in prop_el:
        if child.tag == "Link":
            out.append(child.get("value"))
        elif child.tag in ("LinkList", "LinkSub"):
            for entry in child:
                if entry.tag in ("Link", "LinkSub"):
                    out.append(entry.get("value"))
                else:
                    out.append(entry.get("value"))
        elif child.tag == "LinkSubList":
            for entry in child:
                out.append(entry.get("obj") or entry.get("value"))
    return [n for n in out if n]


def _scalar_value(prop_el):
    """A numeric / boolean / short-string property as a Python scalar.

    `None` for the compound types (constraint lists, geometry lists, the
    string hasher) -- this instrument only reads the values a construction
    CHOOSES, and those are all plain scalars.
    """
    for child in prop_el:
        if child.tag in ("Float", "Integer", "String", "Bool"):
            raw = child.get("value")
            if child.tag == "Bool":
                return raw == "true"
            if child.tag == "String":
                return raw if raw and len(raw) <= 40 else None
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None
    return None


class Archive:
    """A read-only view of one `.FCStd`."""

    def __init__(self, path):
        self.path = path
        self.nodes = {}
        self.order = []
        self._zip = zipfile.ZipFile(path)
        self._root = ET.fromstring(self._zip.read("Document.xml"))
        self._parse()
        self._folders()

    # -- parsing -------------------------------------------------------
    def _parse(self):
        data = self._root.find("ObjectData")
        if data is None:
            raise SystemExit("%s has no ObjectData -- is it a FreeCAD "
                             "document?" % self.path)
        for el in data:
            node = Node(el.get("name"))
            self._parse_props(node, el)
            self.nodes[node.name] = node
            self.order.append(node.name)

    def _parse_props(self, node, el):
        props = el.find("Properties")
        if props is None:
            return
        for p in props:
            name = p.get("name")
            if name is None:
                continue
            if name == "Proxy":
                py = p.find("Python")
                if py is not None:
                    node.cls = py.get("class")
                continue
            if name == "Label":
                node.label = _child_value(p, "String")
                continue
            if name in ("Label2", "internalName", "object_type",
                        "object_version", "ExpressionEngine"):
                continue
            ty = p.get("type") or ""
            if "Link" in ty:
                tg = _link_targets(p)
                if tg:
                    node.links[name] = tg
                continue
            if ty == "Part::PropertyPartShape":
                node.has_shape = p.find("Part") is not None
                continue
            if name == "Poles":
                node.poles = self._vector_list(p)
                continue
            if name == "Weights":
                node.weights = self._float_list(p)
                continue
            if ty == "Part::PropertyGeometryList":
                continue
            val = _scalar_value(p)
            if val is not None:
                node.scalars[name] = val

    # -- payload members ----------------------------------------------
    def _member_bytes(self, fname):
        try:
            return self._zip.read(fname)
        except KeyError:
            return None

    def _vector_list(self, p):
        el = p.find("VectorList")
        if el is None:
            return None
        if "file" in el.attrib:
            raw = self._member_bytes(el.get("file"))
            if raw is None:
                return None
            n = struct.unpack("<i", raw[:4])[0]
            return [struct.unpack("<3d", raw[4 + 24 * i:4 + 24 * i + 24])
                    for i in range(n)]
        return [(float(v.get("x")), float(v.get("y")), float(v.get("z")))
                for v in el]

    def _float_list(self, p):
        el = p.find("FloatList")
        if el is None:
            return None
        if "file" in el.attrib:
            raw = self._member_bytes(el.get("file"))
            if raw is None:
                return None
            n = struct.unpack("<i", raw[:4])[0]
            return list(struct.unpack("<%dd" % n, raw[4:4 + 8 * n]))
        return [float(v.get("value")) for v in el]

    # -- folder membership --------------------------------------------
    def _folders(self):
        for name in self.order:
            node = self.nodes[name]
            grp = node.links.get("Group")
            if not grp:
                continue
            label = node.label or node.name
            for member in grp:
                if member in self.nodes:
                    self.nodes[member].folder.append(label)

    # -- queries -------------------------------------------------------
    def by_class(self, cls):
        return [self.nodes[n] for n in self.order
                if self.nodes[n].cls == cls]

    def get(self, name):
        return self.nodes.get(name)

    def corners(self):
        """Every corner construction in the file, as a dict.

        A corner is found from its finished surface: a `CubicSurface_66` over
        a four-subgrid grid (the maintainer's quad, four ring members), or a
        `CubicNStarSurface_NStar66` over an N-subgrid grid (his three-member
        N-star -- the corner that has no fourth member at all).

        `tri` is the member's own face when the corner HAS a ring member that
        is a `ControlGrid64_3_1Grid44` -- the collapsed triangular member --
        and that grid's consumer of class `CubicSurface_64`.
        """
        out = []
        for grid_cls, kind in (("ControlGrid66_4Sub", "quad-4sub"),
                              ("ControlGridNStar66_NSub", "nstar")):
            for grid in self.by_class(grid_cls):
                subs = [n for k in sorted(grid.links) if k.startswith("Sub")
                        for n in grid.links[k]]
                root = None
                for cand in self.by_class(CORNER_ROOT_CLASSES[0]):
                    if cand.links.get("Grid") == [grid.name]:
                        root = cand
                        break
                if root is None:
                    for cand in self.by_class(CORNER_ROOT_CLASSES[1]):
                        if cand.links.get("NStarGrid") == [grid.name]:
                            root = cand
                            break
                if root is None:
                    continue
                members = _ring_members(self, subs)
                tri_grid = [m for m in members
                            if self.nodes[m].cls == "ControlGrid64_3_1Grid44"]
                tri_face = None
                if tri_grid:
                    for cand in self.by_class("CubicSurface_64"):
                        if cand.links.get("Grid") == [tri_grid[0]]:
                            tri_face = cand.name
                            break
                out.append({
                    "kind": kind,
                    "root": root.name,
                    "grid": grid.name,
                    "subs": subs,
                    "members": members,
                    "member_grid": tri_grid[0] if tri_grid else None,
                    "tri": tri_face,
                    "folders": list(root.folder),
                })
        return out

    def tri_area(self, corner):
        """The triangular member's area, OFFLINE, from its control net.

        A `CubicSurface_64` is a bicubic Bezier patch over its 6x4 net
        (degree 3 in both, clamped knots, the inner u knots at 1/3 and 2/3).
        Sampled on a 32x32 param grid. This is an ESTIMATE of the stored
        shape's `Shape.Area` (the same patch measured by OCCT over RPC), and
        it is used only to RANK corners, never as a distance.
        """
        grid = self.nodes.get(corner.get("member_grid") or "")
        if grid is None or not grid.poles or len(grid.poles) != 24:
            return None
        if grid.weights and any(abs(w - 1.0) > 1e-12 for w in grid.weights):
            return None          # rational net: the sample ignores weights
        return net_area(grid.poles)

    def leader_cuts(self, corner):
        """The cut positions under the corner's triangular member.

        The member's grid is built over a `ControlGrid44_2EdgeSegments`, i.e.
        between two CURVE SEGMENTS of the patch's corner cell. Each segment is
        a `ControlPoly4_segment` over a curve, cut by two `Point_onCurve`
        objects whose `u` is the cut. Those `u` values are the maintainer's
        "rolling leader" -- and they are read here, not guessed.
        """
        out = []
        grid = self.nodes.get(corner.get("member_grid") or "")
        if grid is None:
            return out
        for g44 in grid.links.get("ControlGrid44", []):
            for side in ("NL_Curve_a", "NL_Curve_b"):
                target = self.nodes.get(g44)
                if target is None:
                    continue
                for curve in target.links.get(side, []):
                    out.extend(_cut_chain(self, curve, side))
        return out


def _ring_members(archive, subs):
    """The ring members in the assembly's own order.

    `SubGrid_0`..`SubGrid_3` are consecutive PAIRS of ring members: subgrid k
    joins `Grid_0` to `Grid_1`, and subgrid k+1 starts where k ended, so the
    ring is `Grid_0` of each subgrid and the closure of the last one is the
    first member again. That chain is read here (and the closure dropped)
    rather than assumed, because WHICH member comes first is one of the
    things the maintainer's file decides and ours does not.
    """
    if not subs:
        return []
    members = []
    for s in sorted(subs):
        node = archive.nodes.get(s)
        if node is None:
            continue
        g0 = (node.links.get("Grid_0") or [None])[0]
        g1 = (node.links.get("Grid_1") or [None])[0]
        if not members:
            members.append(g0)
        members.append(g1)
    while len(members) > 1 and members[-1] == members[0]:
        members.pop()
    return [m for m in members if m]


def _cut_chain(archive, curve_name, side):
    """(side, curve, base curve, u0, u1) for one member edge, or [].

    Walks curve -> ControlPoly4_segment -> {NL_Curve, Point_onCurve_0/1} one
    level, which is where every cut in the reference lives.
    """
    node = archive.nodes.get(curve_name)
    if node is None:
        return []
    for poly in node.links.get("Poly", []):
        pn = archive.nodes.get(poly)
        if pn is None:
            continue
        base = (pn.links.get("NL_Curve") or [None])[0]
        u0 = _point_u(archive, pn.links.get("Point_onCurve_0"))
        u1 = _point_u(archive, pn.links.get("Point_onCurve_1"))
        if base is None:
            return []
        return [{"side": side, "segment": poly, "base": base,
                 "u0": u0, "u1": u1}]
    return []


def _point_u(archive, names):
    for n in (names or []):
        node = archive.nodes.get(n)
        if node is not None and "u" in node.scalars:
            return node.scalars["u"]
    return None


# ---------------------------------------------------------------------------
# Offline Bezier evaluation (ranking only -- see Archive.tri_area)
# ---------------------------------------------------------------------------

_KNOTS_U6 = (0.0, 0.0, 0.0, 0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0, 1.0, 1.0, 1.0)
_KNOTS_V4 = (0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0)


def _basis(i, p, u, knots):
    if p == 0:
        if knots[i] <= u < knots[i + 1]:
            return 1.0
        if u >= knots[-1] and knots[i] < knots[-1] <= knots[i + 1]:
            return 1.0
        return 0.0
    left = 0.0
    if knots[i + p] > knots[i]:
        left = ((u - knots[i]) / (knots[i + p] - knots[i])
                * _basis(i, p - 1, u, knots))
    right = 0.0
    if knots[i + p + 1] > knots[i + 1]:
        right = ((knots[i + p + 1] - u) / (knots[i + p + 1] - knots[i + 1])
                 * _basis(i + 1, p - 1, u, knots))
    return left + right


def net_point(poles, u, v):
    """One point of a 6x4 `CubicSurface_64` net (flat V*6 + U, per the store)."""
    bu = [_basis(i, 3, u, _KNOTS_U6) for i in range(6)]
    bv = [_basis(j, 3, v, _KNOTS_V4) for j in range(4)]
    x = y = z = 0.0
    for j in range(4):
        for i in range(6):
            w = bu[i] * bv[j]
            p = poles[j * 6 + i]
            x += w * p[0]
            y += w * p[1]
            z += w * p[2]
    return (x, y, z)


def net_area(poles, n=32):
    """Area of a 6x4 net by finite differences on an n x n param grid."""
    total = 0.0
    h = 1.0 / n
    for a in range(n):
        for b in range(n):
            u, v = (a + 0.5) * h, (b + 0.5) * h
            du = [net_point(poles, u + h, v)[k] - net_point(poles, u, v)[k]
                  for k in range(3)]
            dv = [net_point(poles, u, v + h)[k] - net_point(poles, u, v)[k]
                  for k in range(3)]
            cx = du[1] * dv[2] - du[2] * dv[1]
            cy = du[2] * dv[0] - du[0] * dv[2]
            cz = du[0] * dv[1] - du[1] * dv[0]
            total += (cx * cx + cy * cy + cz * cz) ** 0.5
    return total


# ---------------------------------------------------------------------------
# The graph walk
# ---------------------------------------------------------------------------

# The role each proxy class plays in a corner, in the maintainer's vocabulary.
ROLE = {
    "CubicSurface_66": "QUAD (the corner fill, 6x6)",
    "ControlGrid66_4Sub": "QUAD GRID (4 subgrids)",
    "SubGrid33_2Grid64": "QUAD SUBGRID (a ring pair's 3x3)",
    "CubicNStarSurface_NStar66": "QUAD (N-star, 3 members)",
    "ControlGridNStar66_NSub": "QUAD GRID (N subgrids)",
    "SubGrid63_2Surf64": "QUAD SUBGRID (surface pair)",
    "ControlGrid64_3_1Grid44": "TRI MEMBER GRID (collapsed row)",
    "ControlGrid44_2EdgeSegments": "TRI MEMBER CORNER CELL (2 edge segments)",
    "CubicSurface_44": "PATCH CORNER CELL SURFACE",
    "CubicSurface_64": "TRI FACE / ring blend surface",
    "ControlGrid64_2Grid44": "RING BLEND GRID",
    "ControlPoly4_segment": "CUT SEGMENT (u0..u1 of a curve)",
    "ControlPoly4_2P": "BRIDGE CURVE (2 points)",
    "ControlPoly4_3L": "CURVE FRAME (sketch-driven)",
    "CubicCurve_4": "CURVE",
    "Point_onCurve": "CUT (a position on a curve)",
}


def walk(archive, root_name, max_depth=8):
    """Depth-first over LINK properties, repeating objects marked ONCE.

    Returns a list of `(depth, node, via_prop, repeat)`.
    """
    rows = []
    seen = set()

    def rec(name, depth, via):
        node = archive.nodes.get(name)
        if node is None:
            rows.append((depth, None, via, False))
            return
        repeat = name in seen
        rows.append((depth, node, via, repeat))
        if repeat or depth >= max_depth:
            return
        seen.add(name)
        for prop in sorted(node.links):
            for tgt in node.links[prop]:
                rec(tgt, depth + 1, prop)

    rec(root_name, 0, None)
    return rows


def _describe(node):
    """The scalars that carry a construction choice, one compact string."""
    keep = ("u", "Corner", "adjust_0", "adjust_1", "reverse", "Scale0",
            "Scale1", "Scale0_abs", "Scale1_abs")
    bits = ["%s=%g" % (k, node.scalars[k]) for k in keep
            if k in node.scalars]
    if node.poles:
        bits.append("poles=%d" % len(node.poles))
        coins = node.coincident_pairs()
        if coins:
            bits.append("coincident_pairs=%d" % coins)
    return ", ".join(bits)


def graph_text(archive, root_name, max_depth=8):
    lines = []
    for depth, node, via, repeat in walk(archive, root_name, max_depth):
        pad = "  " * depth
        lead = ("%s.%s -> " % (pad, via)) if via else pad
        if node is None:
            lines.append("%s<missing>" % lead)
            continue
        desc = _describe(node)
        lines.append("%s%s [%s]%s%s"
                     % (lead, node.name, node.cls,
                        (" " + desc) if desc else "",
                        "   (... already walked)" if repeat else ""))
    return lines


def role_of(node):
    return ROLE.get(getattr(node, "cls", None), getattr(node, "cls", None))


# ---------------------------------------------------------------------------
# Picking a corner
# ---------------------------------------------------------------------------

def pick_corner(archive, which):
    """(corner, why) -- `which` is 'auto', a root name, or an index."""
    corners = [c for c in archive.corners() if c["tri"]]
    if not corners:
        corners = archive.corners()
    if not corners:
        raise SystemExit("%s carries no corner construction (no CubicSurface_66 "
                         "over a 4-subgrid grid, no CubicNStarSurface)"
                         % archive.path)
    if which not in (None, "auto"):
        for c in archive.corners():
            if which in (c["root"], c["grid"], c["tri"]):
                return c, "named by --corner %s" % which
        raise SystemExit("no corner with root/grid/tri named %r -- try --list"
                         % which)
    scored = []
    for c in corners:
        a = archive.tri_area(c)
        scored.append((a, c))
    known = [s for s in scored if s[0] is not None]
    if not known:
        return corners[0], ("no corner has a readable triangular net; took the "
                            "first in document order")
    best = min(a for a, _c in known)
    ties = [c for a, c in known if abs(a - best) <= 1e-9 * max(1.0, best)]
    chosen = ties[0]
    return chosen, ("smallest TRIANGULAR net area (%.3f mm^2 offline, 32x32 "
                    "sampling), %d of %d candidates tie at that area, tie "
                    "broken by the folder's stored order"
                    % (best, len(ties), len(known)))


# ---------------------------------------------------------------------------
# The reference side: one corner, everything we can read offline
# ---------------------------------------------------------------------------

def reference_report(archive, corner, leaves=False):
    lines = []
    lines.append("REFERENCE  %s" % os.path.basename(archive.path))
    lines.append("  corner   %s  (%s)" % (corner["root"], corner["kind"]))
    lines.append("  folder   %s" % (", ".join(corner["folders"]) or "-"))
    lines.append("  quad     %s over %s" % (corner["root"], corner["grid"]))
    lines.append("  ring     %d members, in the assembly's own order:"
                 % len(corner["members"]))
    for k, m in enumerate(corner["members"]):
        node = archive.nodes[m]
        tag = " <- TRI MEMBER" if m == corner["member_grid"] else ""
        lines.append("      [%d] %-32s %-24s poles=%s%s"
                     % (k, m, node.cls, len(node.poles or []) or "-", tag))
    if corner["tri"]:
        lines.append("  tri face %s (CubicSurface_64 over the member grid)"
                     % corner["tri"])
    area = archive.tri_area(corner)
    if area is not None:
        lines.append("  tri area %.3f mm^2 (offline net estimate)" % area)
    cuts = archive.leader_cuts(corner)
    if cuts:
        lines.append("  cuts under the member (the maintainer's leader):")
        for c in cuts:
            lines.append("      %-10s u %s .. %s  on %s  (segment %s)"
                         % (c["side"], c["u0"], c["u1"], c["base"],
                            c["segment"]))
    lines.append("")
    lines.append("  QUAD GRAPH (down from %s)" % corner["root"])
    for ln in graph_text(archive, corner["root"]):
        lines.append("    " + ln)
    if corner["tri"]:
        lines.append("")
        lines.append("  TRI GRAPH (down from %s)" % corner["tri"])
        for ln in graph_text(archive, corner["tri"]):
            lines.append("    " + ln)
    if leaves:
        lines.append("")
        lines.append("  LEAVES under the member (control poly / points)")
        grid = archive.nodes.get(corner["member_grid"] or "")
        if grid is not None:
            for prop in sorted(grid.links):
                for tgt in grid.links[prop]:
                    lines.append("    .%s -> %s" % (prop, tgt))
                    for ln in graph_text(archive, tgt, max_depth=6)[1:]:
                        lines.append("      " + ln)
    return lines


def node_table(archive, corner):
    """`{role: [node, ...]}` for the corner -- the diff's working set."""
    out = {}
    seen = set()
    roots = [corner["root"]] + ([corner["tri"]] if corner["tri"] else [])
    for r in roots:
        for _depth, node, _via, repeat in walk(archive, r, max_depth=4):
            if node is None or repeat or node.name in seen:
                continue
            seen.add(node.name)
            out.setdefault(role_of(node), []).append(node)
    return out


# ---------------------------------------------------------------------------
# THE ROW MAP (#127): which of each ring member's own rows the loop reads
# ---------------------------------------------------------------------------

# The reader's own index map, ported from `ArachNURBS.SubGrid33_2Grid64`
# (== `SilkMachinery.subgrid33_2grid64`).  A pair reads, from EACH of its two
# members, the two rows at the shared corner's V end and the half of the
# across-seam axis nearest the shared patch:
#
#   grid_0 corner 0  (V0,U0) -> rows (0, 1), columns 0..2
#   grid_0 corner 3  (V3,U5) -> rows (3, 2), columns 5..3
#   grid_1 corner 1  (V0,U5) -> rows (0, 1), columns 5..3
#   grid_1 corner 2  (V3,U0) -> rows (3, 2), columns 0..2
#
# So the pair's shared corner is on OPPOSITE ends of the two members' 6-pole
# axis (the shared patch) and on the SAME V end.  The first row read is the
# member's RING ROW (it becomes one side of the 6x6); the second is the row
# the interior extrapolation takes its tangent from.
READ_ROWS = {
    ("g0", 0): ((0, 1), (0, 1, 2)),
    ("g0", 3): ((3, 2), (5, 4, 3)),
    ("g1", 1): ((0, 1), (5, 4, 3)),
    ("g1", 2): ((3, 2), (0, 1, 2)),
}

CORNER_SLOTS = (0, 5, 18, 23)      # (V0,U0) (V0,U5) (V3,U0) (V3,U5)


def pair_needs_swap(common):
    """`SilkMachinery._pair_needs_swap`: the reader would transpose."""
    return common[0] in (1, 2) and common[1] in (0, 3)


def pair_common(poles_0, poles_1, tol=1e-6):
    """`SilkMachinery.pair_common` without FreeCAD: (i, j) or (None, why).

    A single geometric match is the ordinary case; the degeneracy rule that
    admits a collapsed end row lives in the machinery and is not duplicated
    here -- a pair that needs it is reported as `ambiguous` with its match
    list, which is all the row map needs.
    """
    c0 = [poles_0[k] for k in CORNER_SLOTS]
    c1 = [poles_1[k] for k in CORNER_SLOTS]
    matches = [(i, j) for i in range(4) for j in range(4)
               if _dist(c0[i], c1[j]) <= tol]
    if not matches:
        return None, "the two grids share no corner at tolerance %g" % tol
    if len(matches) == 1:
        return matches[0], None
    return None, "ambiguous (matches %r)" % (matches,)


def _dist(a, b):
    d = (a[0] - b[0], a[1] - b[1], a[2] - b[2])
    return (d[0] * d[0] + d[1] * d[1] + d[2] * d[2]) ** 0.5


def _row_degeneracy(poles, row):
    """How many pole PAIRS of one 6-pole row coincide (15 == collapsed)."""
    p = [poles[row * 6 + u] for u in range(6)]
    n = 0
    for i in range(6):
        for j in range(i):
            if _dist(p[i], p[j]) <= 1e-7:
                n += 1
    return n


def _surface_net(archive, surface_name):
    """(poles, weights) of a `CubicSurface_44`'s own 4x4 Bezier net.

    The surface stores no poles of its own -- it stores a SHAPE. Its net is
    the `ControlGrid44_flow` grid it is built over, whose poles are the ones
    FreeCAD's `getPoles()` reports for the surface (measured: using the
    flow's `InputGrid` instead leaves 6e-03 mm residuals, the flow grid
    1e-14)."""
    node = archive.nodes.get(surface_name or "")
    if node is None:
        return None, None
    grid = (node.links.get("Grid") or [None])[0]
    g = archive.nodes.get(grid or "")
    if g is None or not g.poles or len(g.poles) != 16:
        return None, None
    return g.poles, (g.weights or [1.0] * 16)


def _bezier44(poles, weights, u, v):
    """One point of a bicubic Bezier over a 4x4 [u][v] net."""
    bu = [((1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u ** 3)]
    bv = [((1 - v) ** 3, 3 * v * (1 - v) ** 2, 3 * v * v * (1 - v), v ** 3)]
    x = y = z = w = 0.0
    for i in range(4):
        for j in range(4):
            b = bu[0][i] * bv[0][j] * weights[i * 4 + j]
            p = poles[i * 4 + j]
            x += b * p[0]
            y += b * p[1]
            z += b * p[2]
            w += b
    return (x / w, y / w, z / w)


def surface_uv(poles, weights, pt, steps=40):
    """(residual mm, u, v): where `pt` sits on that surface's own net.

    A coarse scan plus a shrinking local refine. The RESIDUAL is the
    instrument's error floor and is printed with every reading: 1e-14 mm on
    a pole that lies on the surface, so a reading of `1/16` or `0.25` is a
    measurement, not an eyeball."""
    best = (float("inf"), 0.0, 0.0)
    for i in range(steps + 1):
        u = i / float(steps)
        for j in range(steps + 1):
            v = j / float(steps)
            q = _bezier44(poles, weights, u, v)
            d = _dist(q, pt)
            if d < best[0]:
                best = (d, u, v)
    d0, u0, v0 = best
    step = 1.0 / steps
    for _ in range(40):
        step *= 0.6
        for du in (-step, 0.0, step):
            for dv in (-step, 0.0, step):
                u = min(1.0, max(0.0, u0 + du))
                v = min(1.0, max(0.0, v0 + dv))
                d = _dist(_bezier44(poles, weights, u, v), pt)
                if d < d0:
                    d0, u0, v0 = d, u, v
    return d0, u0, v0


def member_cells(archive, member):
    """The base-surface CELLS one ring member is cut from, measured.

    A member is two `ControlGrid44_2EdgeSegments` cells (the triangular
    member is one), each a parametric RECTANGLE of a base `CubicSurface_44`.
    The rectangle is read off the cell's own stored 4x4 net by inverting it
    on the surface's net, so the reading does not depend on which of the
    cell's two cut curves was taken as the u range.
    """
    node = archive.nodes.get(member or "")
    out = []
    if node is None:
        return out
    cells = node.links.get("Grid_0", []) + node.links.get("Grid_1", [])
    cells += node.links.get("ControlGrid44", [])
    for cell in cells:
        c = archive.nodes.get(cell)
        if c is None or not c.poles or len(c.poles) != 16:
            continue
        surf = (c.links.get("NL_Surface") or [None])[0]
        sp, sw = _surface_net(archive, surf)
        if sp is None:
            continue
        us, vs, res = [], [], []
        for k in (0, 3, 12, 15):
            d, u, v = surface_uv(sp, sw, c.poles[k])
            us.append(u)
            vs.append(v)
            res.append(d)
        out.append({"cell": cell, "surface": surf,
                    "u": (min(us), max(us)), "v": (min(vs), max(vs)),
                    "residual": max(res)})
    return out


def row_map(archive, corner):
    """`{member: row facts}` + the four pair readings, read from the file.

    This is STEP 1 of #127: for every ring member, which of its own rows each
    neighbour subgrid reads, which V end both of its pairs agree on (the
    RING ROW end), whether the member's collapsed row is one of them, and
    where each row sits on its own base surface.
    """
    subs = sorted(corner["subs"])
    members = corner["members"]
    pairs = []
    for k, s in enumerate(subs):
        node = archive.nodes[s]
        g0 = (node.links.get("Grid_0") or [None])[0]
        g1 = (node.links.get("Grid_1") or [None])[0]
        common, why = pair_common(archive.nodes[g0].poles,
                                  archive.nodes[g1].poles)
        pairs.append({"sub": s, "g0": g0, "g1": g1, "common": common,
                      "why": why,
                      "swap": bool(common and pair_needs_swap(common))})
    facts = {}
    for m in members:
        node = archive.nodes[m]
        roles = []
        for k, pr in enumerate(pairs):
            if pr["g0"] == m and pr["common"] is not None:
                roles.append((k, "g0", pr["common"][0]))
            elif pr["g1"] == m and pr["common"] is not None:
                roles.append((k, "g1", pr["common"][1]))
        read = {}
        for (k, slot, idx) in roles:
            got = READ_ROWS.get((slot, idx))
            if got is None:
                read[k] = None          # the reader would transpose it
            else:
                read[k] = got
        ends = [read[k][0][0] for k in read if read[k] is not None]
        facts[m] = {
            "node": node,
            "roles": roles,
            "read": read,
            "ring_v": (ends[0] if ends and len(set(ends)) == 1 else None),
            "degenerate_rows": [v for v in range(4)
                                if _row_degeneracy(node.poles, v) >= 5],
            "cells": member_cells(archive, m),
        }
    return pairs, facts


def row_report(archive, corner):
    """The ROW MAP as text: the reference's side of STEP 1."""
    pairs, facts = row_map(archive, corner)
    lines = ["ROW MAP -- %s, corner %s" % (os.path.basename(archive.path),
                                            corner["root"]),
             "",
             "  the four ring PAIRS (the reader's own index map):"]
    for k, pr in enumerate(pairs):
        if pr["common"] is None:
            lines.append("    %d. %s | %s : %s"
                         % (k, pr["g0"], pr["g1"], pr["why"]))
            continue
        i, j = pr["common"]
        lines.append("    %d. %-30s | %-30s  corners (%d, %d)%s"
                     % (k, pr["g0"], pr["g1"], i, j,
                        "   [reader SWAPS the two grids]" if pr["swap"]
                        else ""))
    lines.append("")
    lines.append("  per member: which rows its two pairs read, and what its "
                 "own rows are")
    for m in corner["members"]:
        f = facts[m]
        node = f["node"]
        tag = "  <- TRI MEMBER" if m == corner.get("member_grid") else ""
        lines.append("    %-32s %s%s" % (m, node.cls, tag))
        for (k, slot, idx) in f["roles"]:
            got = f["read"].get(k)
            if got is None:
                lines.append("        pair %d (%s corner %d): NOT READABLE "
                             "without a grid swap" % (k, slot, idx))
            else:
                lines.append("        pair %d (%s corner %d): rows %s, "
                             "across-seam columns %s"
                             % (k, slot, idx, got[0], got[1]))
        if f["ring_v"] is None:
            lines.append("        RING V-END: its two pairs disagree -- the "
                         "6x6's two sides would be DIFFERENT rows of it")
        else:
            rows = sorted({v for got in f["read"].values() if got
                           for v in got[0]})
            unread = [v for v in range(4) if v not in rows]
            lines.append("        RING V-END: V%d (both pairs) -> rows %s "
                         "read (the first is the 6x6 side, the second the "
                         "extrapolation source); rows %s are NEVER read"
                         % (f["ring_v"], rows, unread))
        for v in range(4):
            deg = _row_degeneracy(node.poles, v)
            read_by = [k for k in f["read"] if f["read"][k]
                       and v in f["read"][k][0]]
            lines.append("        row V%d: coincident pairs %d/15, read by %s"
                         % (v, deg,
                            ("pairs " + ", ".join(str(k) for k in read_by))
                            if read_by else "NO PAIR"))
        for c in f["cells"]:
            lines.append("        cell %-34s on %-20s u %.4f..%.4f  "
                         "v %.4f..%.4f  (residual %.1e mm)"
                         % (c["cell"], c["surface"], c["u"][0], c["u"][1],
                            c["v"][0], c["v"][1], c["residual"]))
        if f["ring_v"] is not None:
            lines.extend(_ring_row_ends(archive, node, f["ring_v"],
                                        f["cells"]))
    return lines


def _ring_row_ends(archive, node, row, cells):
    """Where the RING ROW's two end poles sit on the member's own cells.

    This is the line the loop rule is read off: the ring row ends at the
    shared patch's corner cell FAR corner on the side that faces its ring
    neighbour, and on its own seam at the other end. Measured on the base
    surface's own parameters, with the inversion's residual as the error
    floor.
    """
    out = []
    ends = [node.poles[row * 6 + 0], node.poles[row * 6 + 5]]
    for c in cells:
        sp, sw = _surface_net(archive, c["surface"])
        if sp is None:
            continue
        got = [surface_uv(sp, sw, pt) for pt in ends]
        if max(g[0] for g in got) > 1e-3:
            continue          # these poles are not on this cell's surface
        out.append("        RING ROW V%d ends on %-20s (%.4f, %.4f) and "
                   "(%.4f, %.4f)  (residual %.1e mm)"
                   % (row, c["surface"], got[0][1], got[0][2],
                      got[1][1], got[1][2], max(g[0] for g in got)))
    return out


def row_verdict(archive, corner):
    """One line each: the rule, and what our ring does differently."""
    _pairs, facts = row_map(archive, corner)
    member = corner.get("member_grid")
    fm = facts.get(member) or {}
    ring_v = fm.get("ring_v")
    deg = fm.get("degenerate_rows") or []
    lines = [
        "THE RULE, in one sentence: every ring member's TWO pairs are read "
        "on the SAME V end -- the two rows at the member's ring-facing "
        "edge, its ring row plus the next one inward -- so the member "
        "contributes ONE WHOLE ROW as one side of the 6x6 and its opposite "
        "V end lies inside the loop and is never read.",
        "",
        "HIS TRI MEMBER: ring row V%s, collapsed row(s) V%s -> the collapse "
        "is %s the loop."
        % (ring_v, deg or "none",
           "NOT on" if (ring_v is not None and deg and ring_v not in deg)
           else "ON"),
        "OURS: the same rule -- `orient_junction_row` puts every strip's "
        "junction-end row at V3 and every pair is read (3,2) -- but our "
        "member's ring row IS its collapsed row, because the member is cut "
        "from the patch's corner cell, whose apex corner IS the ring's "
        "shared corner.",
    ]
    return lines


# ---------------------------------------------------------------------------
# Our side: one corner built over the RPC in the owner's GUI
# ---------------------------------------------------------------------------

OURS_CODE = r'''
import sys
sys.path.insert(0, %(repo)r)
sys.path.insert(0, %(here)r)
for _m in [m for m in list(sys.modules)
           if m.split(".")[0] in ("SilkMachinery", "SilkCorner",
                                  "SilkWorkflowOps", "SilkBlend", "SilkPatch",
                                  "SilkEdge", "SilkChecks", "Silk_dummy",
                                  "cube_corner_model", "corner_model",
                                  "reference_corner_diff", "ArachNURBS")]:
    del sys.modules[_m]
import FreeCAD
import reference_corner_diff as R
_free_before = None
for _n, _d in list(FreeCAD.listDocuments().items()):
    if _d.Label == "_refdiff_ours":
        FreeCAD.closeDocument(_d.Name)
out = R.ours_corner(leader=%(leader)r, rows=%(rows)s)
for line in out["text"]:
    print(line)
%(cleanup)s
'''


def ours_corner(leader, fixture="cube_corner", doc_label="_refdiff_ours",
                rows=False):
    """Build OUR corner at `leader` in a scratch document and describe it.

    RUNS INSIDE FREECAD (the local half sends `OURS_CODE` to the owner's GUI
    over XML-RPC). It uses the SHIPPED construction path on purpose: the
    question the diff answers is "what does our corner stage do", so it must
    be the stage, not a re-assembly.
    """
    import FreeCAD
    import Part
    import cube_corner_model as CCM
    import SilkChecks
    import SilkCorner as SC
    import SilkMachinery as M
    import SilkWorkflowOps as OPS

    doc = FreeCAD.newDocument(doc_label)
    FreeCAD.setActiveDocument(doc.Name)
    res = CCM.build_cube_corner_model(doc)
    strips = list(res["strips"].values())
    corner = OPS.create_corner_blend(strips, construction="rolling",
                                     leader=leader, name="OurCorner")
    doc.recompute()
    text = []
    if corner is None or not corner.Poles:
        text.append("OURS  the corner stage built NOTHING at leader %g "
                    "(see the console above for the refusal)" % leader)
        return {"text": text, "doc": doc}

    text.append("OURS  %s  (construction='rolling', leader=%g, on the "
                "cube-corner fixture)" % (doc.Label, leader))
    text.append("  quad     %s  [CornerBlend]  ONE object; the 6x6 is "
                "computed internally by SilkMachinery" % corner.Name)
    text.append("  poles    %d  coincident_pairs=%d"
                % (len(corner.Poles), _coins(corner.Poles)))
    side = M._collapsed_side(list(corner.Poles), 1e-6)
    text.append("  collapsed 6x6 side: %r" % side)
    text.append("  surface  faces=%d area=%.6f valid=%s"
                % (len(corner.Shape.Faces), corner.Shape.Area,
                   corner.Shape.isValid()))
    bb = corner.Shape.BoundBox
    text.append("  bbox     (%.5f %.5f %.5f) .. (%.5f %.5f %.5f)"
                % (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))
    flips = []
    for n in (39, 81, 150):
        flips.append(len(SilkChecks._normal_field_flips(
            corner.Shape.Faces[0].Surface, n=n)[0]))
    text.append("  normal flips n=39/81/150: %r" % (flips,))

    # the raw assembly, i.e. what the primitives produce BEFORE the corner
    # stage's own choice -- this is the number that says whether the stage
    # changed the construction or only reproduced it.
    grids, _cells, why = SC.corner_inputs(strips, SC.CORNER_DEFAULT_TOL)
    if grids is not None:
        if rows:
            text.extend(_our_row_lines(grids))
        subs = []
        for i in range(4):
            a, b = grids[i], grids[(i + 1) % 4]
            sp, sw, _w = M.subgrid33_2grid64(a[0], a[1], b[0], b[1])
            if sp is None:
                text.append("  raw assembly refused: %s" % _w)
                break
            subs.append((sp, sw))
        else:
            praw, wraw = M.control_grid66_4sub(subs)
            moved = max((praw[i] - corner.Poles[i]).Length
                        for i in range(36))
            text.append("  RAW assembly (subgrid33 + control_grid66, no stage "
                        "step): coincident_pairs=%d, collapsed side=%r"
                        % (_coins(praw), M._collapsed_side(praw, 1e-6)))
            text.append("  the stage moved the 6x6 poles by up to %.6f mm "
                        "(smooth_degenerate_cap)" % moved)

    for o in doc.Objects:
        if getattr(o, "object_type", None) == "RollingMemberFace":
            text.append("  member   %s  [RollingMemberFace] poles=%d "
                        "area=%.6f" % (o.Name, len(o.Poles), o.Shape.Area))
            text.append("           boundary_edges=%s"
                        % (list(getattr(o, "BoundaryEdges", []) or []),))
            mflips = [len(SilkChecks._normal_field_flips(
                o.Shape.Faces[0].Surface, n=n)[0]) for n in (39, 81, 150)]
            text.append("           normal flips n=39/81/150: %r" % (mflips,))
            d = _reach(o, corner)
            if d:
                text.append("           member interior -> quad: min %.5f "
                            "max %.5f mm (%.0f%%..%.0f%% of the corner "
                            "extent)" % (d[0], d[1], d[2], d[3]))
    for o in doc.Objects:
        if o.TypeId == "Surface::Filling":
            text.append("  tri face %s  [Surface::Filling] faces=%d "
                        "area=%.6f valid=%s order=%s"
                        % (o.Name, len(o.Shape.Faces), o.Shape.Area,
                           o.Shape.isValid(),
                           getattr(o, "BoundaryOrder", None)))
            d = _reach(o, corner)
            if d:
                text.append("           tri interior -> quad: min %.5f "
                            "max %.5f mm (%.0f%%..%.0f%% of the corner "
                            "extent)" % (d[0], d[1], d[2], d[3]))
    return {"text": text, "doc": doc, "corner": corner}


def _our_row_lines(grids):
    """OUR ring's row map, from the grids `corner_inputs` hands the algebra.

    RUNS INSIDE FREECAD. Same questions as `row_report`'s reference side, so
    the two tables can be read side by side: which rows each pair reads, the
    RING V-END both of a member's pairs agree on, and whether a member's
    collapsed row is one of them.
    """
    import SilkMachinery as M

    lines = ["", "  ROW MAP -- OURS (the ring `corner_inputs` assembles, in "
                 "ring order)"]
    members = [("strip %d" % k, g) for k, g in enumerate(grids)]
    reads = {n: [] for n, _g in members}
    for k in range(4):
        a, b = grids[k], grids[(k + 1) % 4]
        common, why = M.pair_common(a[0], b[0], 1e-6)
        if common is None:
            lines.append("    pair %d: %s" % (k, why))
            continue
        i, j = common
        swap = M._pair_needs_swap(common)
        lines.append("    pair %d: corners (%d, %d)%s"
                     % (k, i, j, "   [reader SWAPS the two grids]" if swap
                        else ""))
        for side, idx, name in (("g0", i, "strip %d" % k),
                                ("g1", j, "strip %d" % ((k + 1) % 4))):
            got = READ_ROWS.get((side, idx))
            reads[name].append((k, got))
    for k, (name, g) in enumerate(members):
        deg = [v for v in range(4) if _row_degeneracy(g[0], v) >= 5]
        ends = [got[0][0] for _k, got in reads[name] if got]
        rows = sorted({v for _k, got in reads[name] if got for v in got[0]})
        unread = [v for v in range(4) if v not in rows]
        lines.append("    %s: RING V-END %s, rows %s read, rows %s NEVER "
                     "read, collapsed row(s) %s"
                     % (name, ("V%d" % ends[0]) if ends and len(set(ends)) == 1
                        else "DISAGREE %r" % (ends,), rows, unread, deg or
                        "none"))
        for _k, got in reads[name]:
            if got is None:
                lines.append("        pair %d: NOT READABLE without a swap"
                             % _k)
            else:
                lines.append("        pair %d: rows %s, across-seam "
                             "columns %s" % (_k, got[0], got[1]))
        for v in range(4):
            lines.append("        row V%d: coincident pairs %d/15"
                         % (v, _row_degeneracy(g[0], v)))
    return lines


def _coins(poles, tol=1e-7):
    n = 0
    for i in range(len(poles)):
        for j in range(i):
            d = poles[i] - poles[j]
            if d.Length <= tol:
                n += 1
    return n


def _reach(fill_obj, corner, grid=9):
    """(min, max, pct_min, pct_max): how far an object's FACE INTERIOR
    stands off the quad, as a percentage of the corner's own extent.

    `distToShape` on the whole surfaces is 0 -- they share a boundary -- so
    this samples the FACE's own parameter rectangle and measures each sample
    to the quad shape. The parameter rectangle is the surface's `bounds()`,
    not [0,1]: a `Surface::Filling` returns a BSpline in its own knot space,
    and reading it as [0,1] reports distances a thousand times too large.
    """
    import Part
    try:
        face = fill_obj.Shape.Faces[0]
        b = face.Surface.bounds()
    except Exception:
        return None
    umin, umax, vmin, vmax = b[0], b[1], b[2], b[3]
    ds = []
    for a in range(1, grid):
        for c in range(1, grid):
            pt = face.Surface.value(umin + (umax - umin) * a / float(grid),
                                    vmin + (vmax - vmin) * c / float(grid))
            ds.append(Part.Vertex(pt).distToShape(corner.Shape)[0])
    if not ds:
        return None
    extent = max(corner.Shape.BoundBox.XLength, corner.Shape.BoundBox.YLength,
                 corner.Shape.BoundBox.ZLength) or 1.0
    return (min(ds), max(ds), 100.0 * min(ds) / extent,
            100.0 * max(ds) / extent)


def rpc_execute(code, timeout=900):
    """Send `code` to the owner's running FreeCAD. NEVER spawns one."""
    import xmlrpc.client
    proxy = xmlrpc.client.ServerProxy("http://%s:%d/" % (RPC_HOST, RPC_PORT))
    proxy.ping()
    res = proxy.execute_code(code, timeout)
    if not res.get("success"):
        raise SystemExit("RPC error: %s" % res.get("error"))
    return res.get("message", "")


def ours_over_rpc(leader, close=True, rows=False):
    boot = OURS_CODE % {"repo": REPO, "here": HERE, "leader": leader,
                        "rows": repr(bool(rows)),
                        "cleanup": ("FreeCAD.closeDocument(out['doc'].Name)"
                                    if close else "pass")}
    return rpc_execute(boot)


# ---------------------------------------------------------------------------
# The diff
# ---------------------------------------------------------------------------

def structural_differences(ref, ours_text):
    """One line per structural difference between the reference and ours.

    Computed, not asserted: every line reads a number out of the two graphs
    produced above. `ref` is the reference `Archive` + corner; `ours_text` is
    OUR side's printed lines (the object graph is one object deep, so its
    facts arrive as text and are scraped here -- keeping ONE rendering of
    them).
    """
    archive, corner = ref
    out = []
    quad = archive.nodes[corner["root"]]
    ours = "\n".join(ours_text)

    out.append(
        "ROOT: reference is a DAG of %d objects (%s down to %s); ours is ONE "
        "CornerBlend object that recomputes the 6x6 internally, plus a "
        "RollingMemberFace and its fill -- the maths is in Python, not in the "
        "document tree."
        % (len(node_table(archive, corner)), corner["root"], corner["grid"]))

    ref_coins = quad.coincident_pairs()
    member = archive.nodes.get(corner.get("member_grid") or "")
    our_coins = "-"
    for ln in ours_text:
        if ln.strip().startswith("poles ") and "coincident_pairs=" in ln:
            our_coins = ln.split("coincident_pairs=")[1].split()[0]
            break
    out.append(
        "DEGENERACY: the reference 6x6 has %d coincident pole pairs of 630 "
        "while its triangular member has %d of 276 -- the assembly NEVER reads "
        "the member's collapsed row, because both of the member's ring pairs "
        "are taken on the SAME end of its net. Our 6x6: %s coincident pairs."
        % (ref_coins,
           member.coincident_pairs() if member is not None else -1,
           our_coins))

    if "collapsed 6x6 side" in ours:
        line = [l for l in ours_text if "collapsed 6x6 side" in l][0]
        out.append(
            "COLLAPSED SIDE: %s -- ours lets the member's collapsed row land on "
            "a side of the 6x6 (which the maintainer's never does), and then "
            "re-solves the interior to stop it folding (next line)."
            % line.strip())

    if "smooth_degenerate_cap" in ours:
        line = [l for l in ours_text if "smooth_degenerate_cap" in l][0]
        out.append(
            "STAGE STEP: %s -- `smooth_degenerate_cap` (the Coons re-solve of "
            "the member-side rows) has NO counterpart in the reference: on a "
            "fold-free input (0 coincident pairs) the function is a no-op, so "
            "his corners never go through it." % line.strip())

    out.append(
        "TRI FACE: the reference draws `CubicSurface_64` over the member net "
        "(%s); ours draws a FreeCAD `Surface::Filling` over the member's "
        "three REAL edges and HIDES the silk member -- the fill is a "
        "different surface construction, not a different net."
        % (corner["tri"] or "-"))

    cuts = archive.leader_cuts(corner)
    if cuts:
        out.append(
            "LEADER: the reference cuts in CURVE PARAMETER SPACE -- %s -- and "
            "feeds the two segments to `ControlGrid44_2EdgeSegments`; ours "
            "writes the leader into the patch's band-edge SPLIT property "
            "(the `Silk: the rolling leader moved ...` lines above) and lets "
            "the patch's own cells re-cut."
            % ", ".join("%s u %s..%s" % (c["side"], c["u0"], c["u1"])
                        for c in cuts))

    members = [archive.nodes[m].cls for m in corner["members"]]
    member_at = [k for k, m in enumerate(corner["members"])
                 if m == corner["member_grid"]]
    out.append(
        "RING ORDER: the reference's assembly order is readable off its own "
        "subgrids (%s), and the TRIANGULAR member sits at position %s of it. "
        "Ours is produced by `corner_ring_3`/`corner_ring` from document order "
        "and then searched over patch x corner x reversal by "
        "`corner_inputs`/`corner_member_pin` -- a search the reference never "
        "needs, because the user places the member by hand there."
        % (", ".join(members), member_at or "?"))
    return out


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def fetch_reference(tag, dest=None):
    """Read the episode-`tag` copy-pasta file out of `upstream/master`.

    Only needed when the tracked copy is missing or a pristine one is wanted:
    the tutorial files ship in this repo, so the ordinary run reads them in
    place.
    """
    import subprocess
    path = UPSTREAM_PATHS[tag]
    dest = dest or os.path.join("/tmp", "cp%s.FCStd" % tag)
    with open(dest, "wb") as fh:
        subprocess.run(["git", "show", "upstream/master:%s" % path],
                       cwd=REPO, check=True, stdout=fh)
    return dest


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="The construction diff: the maintainer's corner vs ours.")
    ap.add_argument("--ref", default=default_reference("29"),
                    help="the reference .FCStd (default: the tracked copy of "
                         "episode 29)")
    ap.add_argument("--fetch", nargs="?", const="29",
                    choices=sorted(UPSTREAM_PATHS),
                    help="git-show the episode's file to /tmp/cpNN.FCStd first")
    ap.add_argument("--corner", default="auto",
                    help="'auto' (smallest tri area), or a root/grid/tri name")
    ap.add_argument("--list", action="store_true",
                    help="list every corner in the file and stop")
    ap.add_argument("--leaves", action="store_true",
                    help="also print the control-poly leaves under the member")
    ap.add_argument("--rows", action="store_true",
                    help="print THE ROW MAP instead: which of each ring "
                         "member's own rows the loop reads (his side "
                         "offline, ours over the RPC when --with-ours is "
                         "added)")
    ap.add_argument("--with-ours", action="store_true",
                    help="with --rows: also build OUR corner and print its "
                         "row map beside his")
    ap.add_argument("--ours", action="store_true",
                    help="also build OUR corner over the RPC and diff it")
    ap.add_argument("--leader", type=float, default=None,
                    help="the rolling leader for OUR build (default: the "
                         "first cut u read from the reference)")
    args = ap.parse_args(argv)

    if args.fetch:
        args.ref = fetch_reference(args.fetch)
        print("fetched %s -> %s" % (args.fetch, args.ref))

    if not os.path.exists(args.ref):
        raise SystemExit("%s does not exist -- run with --fetch 29, or:\n"
                         "  git show \"upstream/master:%s\" > %s"
                         % (args.ref, UPSTREAM_PATHS["29"], args.ref))

    archive = Archive(args.ref)

    if args.list:
        print("%-28s %-22s %-24s %10s  %s"
              % ("quad", "kind", "tri face", "tri area", "folders"))
        for c in archive.corners():
            a = archive.tri_area(c)
            print("%-28s %-22s %-24s %10s  %s"
                  % (c["root"], c["kind"], c["tri"] or "-",
                     "-" if a is None else "%.3f" % a,
                     ", ".join(c["folders"]) or "-"))
        return 0

    corner, why = pick_corner(archive, args.corner)
    print("PICK  %s" % why)
    print("")
    if args.rows:
        for ln in row_report(archive, corner):
            print(ln)
        print("")
        for ln in row_verdict(archive, corner):
            print(ln)
        if args.with_ours:
            leader = args.leader
            if leader is None:
                cuts = archive.leader_cuts(corner)
                us = [c["u0"] for c in cuts if c["u0"] is not None]
                leader = min(us) if us else 0.25
            print("")
            print("OUR LEADER  %g" % leader)
            for ln in ours_over_rpc(leader, rows=True).splitlines():
                print(ln)
        return 0
    ref_lines = reference_report(archive, corner, leaves=args.leaves)
    for ln in ref_lines:
        print(ln)

    if not args.ours:
        print("")
        print("(offline only. --ours builds OUR corner in the owner's running "
              "FreeCAD over XML-RPC and prints the two side by side.)")
        return 0

    leader = args.leader
    if leader is None:
        cuts = archive.leader_cuts(corner)
        us = [c["u0"] for c in cuts if c["u0"] is not None]
        leader = min(us) if us else 0.25
    print("")
    print("OUR LEADER  %g  (the smallest cut u under the reference's member)"
          % leader)
    ours_text = ours_over_rpc(leader).splitlines()
    ours_text = [l for l in ours_text
                 if not l.startswith("CONSOLE:")] or ours_text
    print("")
    for ln in ours_text:
        print(ln)

    print("")
    print("SIDE BY SIDE  (role | reference | ours)")
    ref_tab = node_table(archive, corner)
    ref_roles = sorted(ref_tab)
    ours_roles = _ours_roles(ours_text)
    for role in ref_roles:
        names = ", ".join(n.name for n in ref_tab[role])
        print("  %-46s | %s" % (role, names))
        if role in ours_roles:
            print("  %-46s | %s" % ("", ours_roles.pop(role)))
    for role in sorted(ours_roles):
        print("  %-46s | %s" % ("(no reference counterpart) " + role,
                                ours_roles[role]))

    print("")
    print("NAMED STRUCTURAL DIFFERENCES")
    for i, line in enumerate(structural_differences((archive, corner),
                                                    ours_text), 1):
        print("  %d. %s" % (i, line))
    return 0


def _ours_roles(ours_text):
    """`{role: "object (facts)"}` read off OUR side's own printed lines."""
    out = {}
    for ln in ours_text:
        if "[CornerBlend]" in ln:
            out["QUAD (the corner fill, 6x6)"] = ln.strip()
        elif "[RollingMemberFace]" in ln:
            out["TRI MEMBER (silk net + face)"] = ln.strip()
        elif "[Surface::Filling]" in ln:
            out["TRI FACE (FreeCAD fill)"] = ln.strip()
    return out


if __name__ == "__main__":
    sys.exit(main())
