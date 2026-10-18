# Band A / Band B driven by an expression (#74)

Ticket #74 asked for the wizard's band editors to be expression-drivable,
with the expression bound to the patch's own split property. This records
what was measured, what was built, and -- honestly -- what is still open.

## The model changed under the ticket, and that settles two of its decisions

The ticket's "settled" sections assume ONE list property per axis
(`USplits` / `VSplits`), and are written against it: the expression owns the
whole list, an edit "rewrites the expression, substituting the edited index
and preserving every other element's expression **text**", and a separate
scalar property was rejected because it "would cap the split count".

**#82 shipped the opposite model**: `USplit1` / `USplit2` / `VSplit1` /
`VSplit2`, one `App::PropertyFloat` per axis END, because there is nowhere to
put a third split (see `AGENTS.md`, `SilkMachinery.band_edge_prop`,
`band_delta`). `USplits` / `VSplits` are gone; an old document comes back
with no bands.

Consequences, decided by the code rather than re-decided here:

* "keep ONE list property" is moot -- there is no list.
* "an expression owns the WHOLE list, so an edit must rewrite the expression
  text preserving every other element's expression text" is moot too, and not
  merely moot: with one expression per scalar property there is no element
  index to substitute. Rewriting the property's expression text would mean
  replacing a live reference (`<<Sheet>>.s0`) with the typed literal, i.e.
  exactly the flatten-a-binding-into-a-literal failure the ticket names as
  the one to avoid. So the wizard does NOT rewrite a binding; it refuses the
  literal write and names the binding. One rule, one write path, as the
  ticket's consistency argument demands -- the branch is taken at the
  property, not at an index.
* Each property keeps its OWN expression, so "preserving the other elements'
  expression text" happens by construction: nothing else is touched.

## Hazard 3 (the blocking question) -- ANSWERED, and pinned

Measured on this build (FreeCAD 1.1.3) on an `App::PropertyFloat`:

| operation | measured result |
|---|---|
| `setExpression(prop, "0.25")` | works; `isValid()` True; `ExpressionEngine` shows `('USplit1', '0.25')` |
| `setExpression(prop, "<<Sheet>>.s0")` | works; resolves to the cell's value |
| `setExpression(prop, "<<NoSuchSheet>>.s0")` | accepted; after a recompute the object is `Touched, Invalid`, `getStatusString()` = `Property 'X' not found in 'X.Y' in property binding 'P.prop'` |
| `prop = 0.55` while driven | stored value becomes 0.55 (`State Touched`) and **the next recompute reverts it to 0.25 with no message** |
| `evalExpression(text)` | returns `0.25`/`0.3` when the binding resolves; raises `RuntimeError("Property 'Nope' not found in 'Nope.A1'")` when it does not -- the only mechanism that says WHY |
| `p.getExpression(...)` | does NOT exist on a FeaturePython in this build -- read `ExpressionEngine` |
| `p.USplit1 = ...` while driven, then no recompute | the property reads the typed number, so a panel that shows the property value is showing the user's number as if it had been stored |

So detection is possible, and the VALUE is the one thing that cannot answer
it. `SilkTaskPanel.band_binding_problem` uses the state string (which names
the property binding the way the editor does) plus `evalExpression`.

## What was built

* `SilkTaskPanel.band_expression(p, prop)` -- the expression text that owns
  the property, or None. One spelling, one read (`ExpressionEngine`).
* `SilkTaskPanel.band_binding_problem(p, prop, text)` -- why a binding does
  not produce a value, or None.
* `write_band_split` refuses an expression-owned property **by name** (patch,
  property, expression text, and the binding's own error when it does not
  resolve). Before this it wrote, returned True, and the number was reverted
  at the next recompute -- the silent-stale failure mode.
* The mounted band editor for a driven property is read-only, and its tooltip
  names the expression, the resolution error when there is one, and the fact
  that the displayed number is the last STORED value rather than the
  expression's.
* `SilkBlend._drop_band_split` detaches the binding with the band on unblend
  (a sentinel written into a driven property is reverted too, so the unblend
  would otherwise half-work: the blend gone, its band still carving the
  axis), naming the detached expression. An END that a surviving blend still
  needs keeps its own binding untouched.

Pinned by `Tests/test_band_expression.py` (3 tests: refusal + no transient
value + detach handback; broken binding named, editor read-only, tooltip
labels the stale number; unblend detaches and names).

## Still open (narrowed, not closed)

1. **No `f(x)` affordance in the wizard.** FreeCAD's expression editor is
   reached from the property editor (or `setExpression` from a script); the
   wizard's spin box offers no expression button. The ticket's "UI pattern:
   FreeCAD's own expression affordance (`f(x)` beside the field)" is therefore
   NOT implemented -- wiring it needs `Gui::QuantitySpinBox`/`bind()` or the
   expression dialog, which is a task-panel change of its own.
2. **`ensure_band_split` reads a driven value to decide whether to write.**
   A working binding means the axis "has an edge", so nothing is written (the
   right outcome). A BROKEN binding leaves a stale value that reads as an
   edge, and `ensure_band_split` will trust it -- the same stale-number
   hazard, one level up. It is not covered here because the wizard's own
   write path is the one that could report it; the fix (if any) belongs with
   the object, not the panel.
3. **A legal but wrong-shaped binding** (`<<Sheet>>.s0` on one end only, or a
   value outside `(0, 1)`) is detected by the property's own normalization
   (`normalize_edge_pair` treats it as "no band at this end") -- reported on
   the console, and not special-cased in the panel.
