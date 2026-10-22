# Wizard redesign — native task panel, four collect-then-confirm stages

Settled in a grilling session on 2026-10-11 (grill-with-docs: grilling + domain-modeling). This
supersedes the #48 panel design. Read this together with the wizard-track decision-log entry on
map #1; every item below was decided, not left open.

**Status (#120).** This spec was written for THREE stages and the panel SHIPPED with FOUR:
**Edge / Patch / Blend / Corner Blend**. The fourth section was added after this spec was
settled, by #91 (`Silk_CreateCornerBlend` and the panel's corner section). The three-stage
decision is kept below as the record of what was decided on 2026-10-11 -- it is not rewritten
-- and the fourth section is described where the shipped panel is described.

## The finding that enables everything

`Gui.Control.showDialog()` expects a `Gui::TaskView::TaskDialog*`, which FreeCAD builds in C++.
It silently no-ops on a bare `QWidget`: FreeCAD's `TaskDialogPython` looks up `.ui` or **`.form`**
**by name**, finds neither, and shows an empty panel. That is ticket #51 exactly — the #48 panel
was one attribute away from working. Passing a duck-typed adapter **does** give a real native
task panel with native chrome:

```python
class SilkTaskDialog:
    def __init__(self, form):
        self.form = form              # QWidget, or a list of QWidgets
    def open(self): ...
    def accept(self): return True
    def reject(self): return True
    def clicked(self, button): ...
    def modifyStandardButtons(self, box): ...
    def getStandardButtons(self): ...
    def isAllowedAlterDocument(self): return True
    def isAllowedAlterView(self): return True
    def isAllowedAlterSelection(self): return True

Gui.Control.showDialog(SilkTaskDialog(panel))   # -> native Tasks panel
```

`panel.setWindowTitle(...)` becomes the TaskBox header. Verified live (attach, render,
Enter routing).

## Host & lifecycle

- Native task panel (#71), four sections: **Edge / Patch / Blend / Corner Blend** as
  header/content PAIRS in a fixed order, one open at a time. The container is `SilkTaskPanel`'s
  own `SectionStack` (a plain QWidget, deliberately NOT a QToolBox — a QToolBox stacks all four
  headers on top and cannot fold). No header takes focus (`focusPolicy: NoFocus`), so it never
  steals focus from the 3D view.
- **Refuse to open** if any foreign task dialog is active (FreeCAD allows one at a time and
  raises `RuntimeError("Active task dialog found")`). Never silently close someone else's task.
- **Close the panel on document switch** — collections would belong to a document the user is no
  longer looking at.
- Collections persist while the panel is open, cleared when it closes. No confirm-on-clear.
- The widget is **deleted** by FreeCAD on close (`closeDialog`); rebuild from scratch every open.

## Interaction model (uniform across all four stages)

Collect inputs, then confirm:

- **Enter** via `QShortcut` with `Qt.ApplicationShortcut` — **not** `keyPressEvent` (never fires
  while the 3D view holds focus, which is always). Register **both** `Qt.Key_Return` **and**
  `Qt.Key_Enter` (keypad Enter does not fire otherwise).
- **OR the native OK button** — same action. OK disabled until the open section's collection is
  valid.
- One confirm = **one document transaction = one undo step**, even for a multi-seam blend.
- After applying: collection clears, section stays open, no auto-advance.
- If the entry has gone stale (its edge deleted meanwhile), **refuse loudly on confirm, naming
  the bad item.** Never silently drop it — that would change a quad into a pointed patch.
- Wrong-type clicks are **silently ignored.** No dimming, no highlighting, no message.

## The four sections

- **Edge** — collect **1 or 2** sketches (1 → 3L, 2 → 2N). Collecting rather than firing on the
  first click is what keeps 2N reachable. List shows the collected sketches.
- **Patch** — collect **3 or 4** edges; list plus "N/4" and the resulting fill (quad/pointed).
- **Blend** — one merged table: every seam with its status (blendable / blended by X / blocked);
  clicking collects it, collected rows are highlighted and removable.
- **Corner Blend** (added by #91, after this spec was settled) — collect the **3 or 4 blends**
  that ring one shared junction: three where three patches meet (the triangular patch beside the
  quad is built by the corner stage), four where four do. The section's bound is a RANGE, so its count line
  reads "N collected -- ready" or "need 3 or 4" -- never "incomplete" at a confirmable 3.
  Enter or OK builds ONE `CornerBlend` in ONE transaction (one undo step); a selection that is
  not a ring around one shared junction is refused BY NAME and creates nothing, and a junction
  that already has a corner is an idempotent no-op that names the existing object.

## Blend split parameter (the fillet-radius idea)

No new property on Blend. The band width **is** the patch's split — each axis carries two NAMED
float properties, `USplit1` / `USplit2` / `VSplit1` / `VSplit2` (#82): `Split1` is the
parametric-0 end's band edge, `Split2` the parametric-1 end's, and the axis endpoints are the
sentinels (`Split1 = 0`, `Split2 = 1` reads as "no split on this axis"). `band_cells()` reads
the two named properties live on every call (`SilkMachinery.split_pair`, nothing cached). The
wizard exposes the band width per seam row (one editor per patch, #69) and edits the patch's
split edges directly, under the set-path normalization (`SilkPatch._normalize_splits_on_set` via
`SilkMachinery.normalize_edge_pair`): a value outside [0, 1] becomes that slot's own sentinel,
and a pair whose two edges are out of order is swapped (both reported on the console unless the
document is restoring). A chosen width is validated to still yield exactly **one** band cell
(multi-cell bands are still unsupported and must refuse clearly).

## Known traps (from the live investigation)

- `showDialog` raises if any task dialog is active, **including FreeCAD's Start page panel**.
- `showDialog` in 1.1.3 takes exactly **one** argument.
- No active document → silent no-op, not an exception.
- `getStandardButtons()` defaults to Ok|Cancel; use `modifyStandardButtons` to enable/disable OK.
- If the panel holds focus at close time the focus pointer dangles — move focus before closing.

## Removed by this design

`WorkflowGuide` container (#19/#47's persisting half) — the panel computes live; nothing publishes
state to the property editor. The old `SilkGuidePanel.py` (#48) and #51. #60's separate batch
feature (folded into the Blend section). #53 narrowed to its display residue.