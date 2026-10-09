"""
Tests/mutation_ops.py — shared mutation operators + run_mutations helper
(issue #43 backfill; reused later by the #41 matrix).

Each operator applies a mutation through the ops layer (Sketches/Poles/
USplits + doc.recompute()), then re-validates its mutated object(s) with
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

from SilkChecks import check_edge, check_patch44, check_blend


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
    if t == "Patch44":
        return check_patch44(obj, [obj.Poly0, obj.Poly1, obj.Poly2, obj.Poly3])
    if t == "BlendStrip":
        return check_blend(obj, obj.PatchA, obj.PatchB)
    return []


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


def change_splits(model, *, patch=None, splits_sweep=None):
    """Set / remove / sweep the perpendicular split parameters on a Patch44;
    subgrid cells rebuild and the object revalidates. Only splits that keep
    the blend's band a single seam-adjacent cell are swept (per #33 the
    blend supports single-cell bands), so the seam stays clean."""
    doc = _doc(model)
    if patch is None:
        patch = model.get("patch")
        if patch is None and model.get("patches"):
            patch = list(model["patches"].values())[0]
    else:
        patch = _resolve(model, patch)
    if splits_sweep is None:
        splits_sweep = ([0.5], [0.25, 0.75], [], [0.1], [0.9])
    checks, errors = [], []
    for splits in splits_sweep:
        patch.USplits = splits
        doc.recompute()
        res = check_patch44(patch, [patch.Poly0, patch.Poly1,
                                    patch.Poly2, patch.Poly3])
        bad = [(n, d) for n, ok, d in res if not ok]
        if bad:
            errors.append("change_splits USplits=%s not green: %s"
                          % (splits, bad))
            continue
        if patch.Shape.isNull() or not patch.Shape.isValid():
            errors.append("change_splits USplits=%s: invalid shape" % splits)
            continue
        checks.append("USplits=%s -> oracle green, shape valid" % (splits,))
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
        if not obj.USplits:
            obj.USplits = [0.5]   # so ShowSubgrids exercises real sub-shapes
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
    every iteration and no pole set drifts beyond tol."""
    doc = _doc(model)
    objs = _objects(model)
    base = {o.Name: list(o.Poles) for o in objs}
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
    if not errors:
        checks.append("%d recomputes converged: oracle green, poles stable "
                      "within %.0e across %d objects" % (iterations, tol,
                                                          len(objs)))
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
