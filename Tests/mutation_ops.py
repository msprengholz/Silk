"""
Tests/mutation_ops.py — shared mutation operators + run_mutations helper
(issue #43 backfill; reused later by the #41 matrix).

Each operator applies a mutation through the ops layer (Sketches/Poles/
band edge + doc.recompute()), then re-validates its mutated object(s) with
the relevant SilkChecks oracle. Operators read their targets out of a
model dict produced by a test's build() callable and never inspect
private internals (_subgrids, _base_surface, ...) — behavior only.

run_mutations(doc, build, oracle, ops) is the reusable driver: for each
operator it builds a fresh fixture, asserts the full oracle is green
beforehand, applies the operator, then re-asserts the full oracle is
still green afterwards (proving each mutation neither corrupts geometry
nor leaves stale state).
"""

import FreeCAD

from SilkChecks import check_edge, check_patch, check_blend


def _doc(model):
    doc = model.get("doc")
    return doc or FreeCAD.ActiveDocument


def _edge(model, key):
    """Resolve the target edge: by key, by a bare 'edge' entry, or the
    first edge in the model's edges map."""
    if key is not None:
        return model["edges"][key]
    if model.get("edge") is not None:
        return model["edge"]
    return list(model["edges"].values())[0]


def _resolve(model, target, collection="patches"):
    """Resolve an operator target that may be an object, a key into
    model[collection], or a callable(model) -> object."""
    if callable(target):
        return target(model)
    if isinstance(target, str):
        return model[collection][target]
    return target


def _oracle_obj(obj):
    """Run the oracle appropriate to a single object's type."""
    try:
        t = obj.object_type
    except Exception:
        return []
    if t == "Edge":
        return check_edge(obj)
    if t == "Patch":   # the unified Patch (#37 quad / #38 pointed):
        return check_patch(obj, list(obj.Edges))   # quad->quad, pointed->pointed
    if t in ("Blend", "BlendStrip"):
        return check_blend(obj, obj.PatchA, obj.PatchB)
    return []


def _oracle_patch(p):
    """The patch oracle for a unified Patch: check_patch (the
    Edges count dispatches quad vs pointed, #37/#38)."""
    return check_patch(p, list(p.Edges))


def _oracle_green(prefix, results):
    bad = [(n, d) for n, ok, d in results if not ok]
    if bad:
        return [], ["%s oracle not green: %s" % (prefix, bad)]
    return ["%s oracle green (%d checks)" % (prefix, len(results))], []


# ---- operators ----------------------------------------------------------
# Every operator returns (checks, errors).

def move_boundary_pole(model, *, edge=None, pole_index=1, delta=None):
    """Move one pole on a driving Edge; dependent patches/blends rebuild
    to match; oracle stays green. Default target: the model's first edge
    (or the explicit shared edge key in a pipeline model)."""
    if delta is None:
        delta = FreeCAD.Vector(3.0, 2.0, 1.0)
    doc = _doc(model)
    e = _edge(model, edge)
    poles = list(e.Poles)
    poles[pole_index] = poles[pole_index] + delta
    e.Poles = poles
    doc.recompute()
    checks, errors = _oracle_green("move_boundary_pole[%s]" % e.Name,
                                   check_edge(e))
    if not errors:
        checks.append("pole %d moved by %s" % (pole_index, delta))
    return checks, errors


#: The neutral axis: `Split1 = 0`, `Split2 = 1`, i.e. no band at either
#: end and therefore no subdivision at all. #82: the sentinel IS the
#: property's own endpoint, so "no split on this axis" is a pair of
#: ordinary-looking numbers.
NO_BAND = (0.0, 1.0)


def change_splits(model, *, patch=None, splits_sweep=None, splits_axis="U"):
    """Set / remove / sweep the band edges on a unified Patch; subgrid
    cells rebuild and the object revalidates. `splits_axis` picks the
    swept axis ("U" or "V" -- the pointed seams often carry their band
    edge on the other axis than the quad ones) and `splits_sweep` is a
    list of `(Split1, Split2)` pairs.

    Only sweeps that keep the blend's band a single seam-adjacent cell
    are safe (per #33 the blend supports single-cell bands), so the seam
    stays clean. Which values those are depends on the axis (#41):
    - the axis PARALLEL to the shared seam controls the band's cell
      COUNT, so there a sweep may carry at most one END's edge, or two
      DIFFERENT ones -- each edge drops exactly one corner cell, which
      leaves the single remaining cell in the band. Two ends holding the
      SAME edge collapse to one split whose both cells are corner cells,
      so that pair has no band at all;
    - the PERPENDICULAR axis never affects the band count, so any
      values are safe.
    Callers pass the safe sweep per model; the default sweep is only
    safe on the perpendicular axis (or on models without a blend)."""
    doc = _doc(model)
    if patch is None:
        patch = model.get("patch")
        if patch is None and model.get("patches"):
            patch = list(model["patches"].values())[0]
    else:
        patch = _resolve(model, patch)
    if splits_sweep is None:
        splits_sweep = ((0.5, 1.0), (0.25, 0.75), NO_BAND, (0.1, 1.0),
                        (0.0, 0.9))
    checks, errors = [], []
    prop1, prop2 = "%sSplit1" % splits_axis, "%sSplit2" % splits_axis
    for pair in splits_sweep:
        setattr(patch, prop1, pair[0])
        setattr(patch, prop2, pair[1])
        doc.recompute()
        shown = "%s=%g/%g" % (splits_axis, float(getattr(patch, prop1)),
                              float(getattr(patch, prop2)))
        res = _oracle_patch(patch)
        bad = [(n, d) for n, ok, d in res if not ok]
        if bad:
            errors.append("change_splits %s not green: %s" % (shown, bad))
            continue
        if patch.Shape.isNull() or not patch.Shape.isValid():
            errors.append("change_splits %s: invalid shape" % shown)
            continue
        checks.append("%s -> oracle green, shape valid" % shown)
    return checks, errors


def reverse_edge(model, *, edge=None):
    """Reverse an Edge's pole sequence via the object's `reverse` flag
    (ControlPoly re-derives, so endpoint anchoring stays consistent);
    orient_a_to_b re-orients dependent patches. Oracle stays green."""
    doc = _doc(model)
    e = _edge(model, edge)
    e.reverse = not bool(e.reverse)
    doc.recompute()
    checks, errors = _oracle_green("reverse_edge[%s]" % e.Name, check_edge(e))
    if not errors:
        checks.append("reverse=%s" % e.reverse)
    return checks, errors


def toggle_display(model, *, obj=None):
    """Flip the display toggles (ShowSubgrids/ShowGrid/AutoHideBlend on a
    patch; ShowCurve/ShowPolygon on an edge). The Shape never becomes
    invalid and never ends up wrongly empty: at least one display layer is
    always kept on, and each config revalidates with the object's oracle."""
    doc = _doc(model)
    if obj is None:
        obj = model.get("patch")
        if obj is None and model.get("patches"):
            obj = list(model["patches"].values())[0]
        if obj is None:
            obj = _edge(model, None)
    else:
        obj = _resolve(model, obj, collection="patches")
    checks, errors = [], []
    if hasattr(obj, "ShowSubgrids"):
        flags = ["ShowSubgrids", "ShowGrid", "AutoHideBlend"]
        if not obj.USplit1 and obj.USplit2 == 1.0:
            # so ShowSubgrids exercises real sub-shapes. A band edge at
            # the 0 end (#82) is the neutral choice: it cuts the axis in
            # two and drops the first cell from any band.
            obj.USplit1 = 0.5
            doc.recompute()
    else:
        flags = ["ShowCurve", "ShowPolygon"]
    for f in flags:
        setattr(obj, f, not bool(getattr(obj, f)))
        if hasattr(obj, "ShowCurve") and not (obj.ShowCurve or obj.ShowPolygon):
            obj.ShowCurve = True   # never leave the display shape empty
        doc.recompute()
        if obj.Shape.isNull() or not obj.Shape.isValid():
            errors.append("toggle_display %s: shape invalid/empty" % f)
            continue
        res = _oracle_obj(obj)
        bad = [(n, d) for n, ok, d in res if not ok]
        if bad:
            errors.append("toggle_display %s -> %s: oracle not green: %s"
                          % (f, bool(getattr(obj, f)), bad))
            continue
        checks.append("toggled %s -> %s; shape valid, oracle green"
                      % (f, bool(getattr(obj, f))))
    return checks, errors


def _objects(model):
    """Every Silk object reachable from the model (deduped, in doc order)."""
    seen, out = set(), []
    def add(o):
        if o is None or id(o) in seen:
            return
        try:
            t = getattr(o, "object_type", None)
        except Exception:
            t = None
        if t is None:
            return
        seen.add(id(o))
        out.append(o)
    for v in model.values():
        if isinstance(v, dict):
            for sub in v.values():
                if isinstance(sub, (list, tuple)):
                    for o in sub:
                        add(o)
                else:
                    add(sub)
        elif isinstance(v, (list, tuple)):
            for o in v:
                add(o)
        else:
            add(v)
    return out


def recompute_convergence(model, *, iterations=5, tol=1e-6):
    """Recompute repeatedly. Hidden-cell sets / geometry must converge
    (no ping-pong, no stale state): every object's oracle stays green on
    every iteration, no pole set drifts beyond tol, and every object
    exposing _HiddenSubgridIdxs keeps the IDENTICAL set across all
    iterations with every index inside [0, nu*nv), where nu/nv are
    derived from the four public band edges (a set that is stale from
    before the first iteration, ping-pongs, or holds out-of-range cell
    indices after a split change is flagged)."""
    doc = _doc(model)
    objs = _objects(model)
    base = {o.Name: list(o.Poles) for o in objs}
    hidden0 = {}
    for o in objs:
        h = getattr(o, "_HiddenSubgridIdxs", None)
        if h is not None:
            hidden0[o.Name] = sorted(h)
    checks, errors = [], []
    for i in range(iterations):
        doc.recompute()
        for o in objs:
            bad = [(n, d) for n, ok, d in _oracle_obj(o) if not ok]
            if bad:
                errors.append("recompute_convergence iter %d: %s not green: %s"
                              % (i, o.Name, bad))
            dev = max((p - q).Length for p, q in zip(list(o.Poles), base[o.Name]))
            if dev > tol:
                errors.append("recompute_convergence iter %d: %s drifted %.3e"
                              % (i, o.Name, dev))
            h = getattr(o, "_HiddenSubgridIdxs", None)
            if h is None:
                continue    # only patches carry the auto-hide bookkeeping
            h = sorted(h)
            if o.Name in hidden0 and h != hidden0[o.Name]:
                errors.append("recompute_convergence iter %d: %s hidden-cell "
                              "set %r != baseline %r (ping-pong / stale)"
                              % (i, o.Name, h, hidden0[o.Name]))
            from SilkMachinery import build_intervals, split_pair
            nu = len(build_intervals(*split_pair(o, "U")))
            nv = len(build_intervals(*split_pair(o, "V")))
            oob = [k for k in h if not (0 <= k < nu * nv)]
            if oob:
                errors.append("recompute_convergence iter %d: %s hidden-cell "
                              "indices %r out of [0, %d)"
                              % (i, o.Name, oob, nu * nv))
    if not errors:
        msg = ("%d recomputes converged: oracle green, poles stable "
               "within %.0e across %d objects" % (iterations, tol,
                                                  len(objs)))
        if hidden0:
            msg += "; hidden-cell sets identical across all iterations, in range"
        checks.append(msg)
    return checks, errors


# ---- driver -------------------------------------------------------------

def run_mutations(doc, build, oracle, ops):
    """Run each mutation operator against a freshly built fixture.

    doc:    the test document (objects are built into it).
    build:  zero-arg callable returning a model dict of Silk objects.
    oracle: callable(model) -> list of (name, ok, detail); the full
            correctness check for the fixture.
    ops:    iterable of callables op(model) -> (checks, errors).

    For every operator: build fresh -> assert baseline oracle green ->
    apply the operator (which recomputes and self-validates) -> re-assert
    the full oracle is green (no stale state left behind).

    Returns (errors, checks).
    """
    FreeCAD.setActiveDocument(doc.Name)
    errors, checks = [], []
    for op in ops:
        name = getattr(op, "__name__", "operator")
        try:
            model = build()
        except Exception as e:
            errors.append("%s: build failed: %r" % (name, e))
            continue
        bad = [(n, d) for n, ok, d in oracle(model) if not ok]
        if bad:
            errors.append("%s: baseline oracle not green: %s" % (name, bad))
        try:
            op_checks, op_errors = op(model)
            checks += ["%s: %s" % (name, c) for c in op_checks]
            errors += op_errors
        except Exception as e:
            errors.append("%s: %r" % (name, e))
        bad = [(n, d) for n, ok, d in oracle(model) if not ok]
        if bad:
            errors.append("%s: post-mutation oracle not green: %s" % (name, bad))
        else:
            checks.append("%s: post-mutation oracle green (%d checks)"
                          % (name, len(oracle(model))))
    return errors, checks
