# Console-message noise across the workbench actions (#88)

Ticket #88, raised in the #86 grilling: *"we have to check which actions emit a
console dialogue in general for our workbench. it seems sometimes to be too
much."* This is the audit and its measured outcome. The standing pattern --
"name the offender" refusals plus resolver-verbatim status lines -- is kept;
one measured noise source was removed, and the message-text changes the numbers
suggest but do NOT decide are listed at the end for the grilling session.

## Instrument

`Tests/console_noise_inventory.py` (MANUAL, run with
`python3 Tests/run_all.py console_noise_inventory`). It taps the three
**Python-side** writers (`FreeCAD.Console.PrintMessage` / `PrintWarning` /
`PrintError`), attributes each line to the running ACTION and to the function
that wrote it, drives a scripted walk through the wizard -- panel open, Edge
confirm, Patch confirm, Blend confirm (two seams, one step), band edits on both
bands, a refused band width, Corner confirm, a delete cascade -- and prints the
raw lines, a per-action table and a per-writer table.

Scope of the instrument, stated rather than implied: it captures every line
**Silk writes**. It does not capture a line written inside C++ (the Report View
path the expression engine uses, #74), so it is the right instrument for "is
our volume too much", and the wrong one for "did FreeCAD complain".

## Measured walk, before the reduction

Fixture: a fresh document; one 3-line sketch -> Edge, one 4-edge loop -> Patch,
a two-seam tube -> 2 Blends in one confirm, both bands edited, a width of 1.0
refused on each band, the 4-ring corner fixture -> 1 CornerBlend, then one
patch deleted (cascade).

| action | message | warning | error | total |
|---|---|---|---|---|
| edge confirm | 3 | 0 | 0 | 3 |
| patch confirm | 9 | 0 | 0 | 9 |
| blend confirm | 14 | 0 | 0 | 14 |
| band edit refused | 0 | 0 | 2 | 2 |
| corner confirm | 25 | 0 | 0 | 25 |
| delete cascade | 2 | 0 | 0 | 2 |
| **total** | **53** | **0** | **2** | **55** |

By writer:

| writer | lines |
|---|---|
| `ArachNURBS.__init__` | 44 |
| `SilkBlend._cascade_one` | 2 |
| `SilkTaskPanel.(confirm_edge\|confirm_patch\|confirm_blend\|confirm_corner)` | 5 |
| `SilkTaskPanel.write_band_split` (the two refusals) | 2 |

**The finding: 44 of 55 lines (80%) were `<Class> class Init` banners** --
`ArachNURBS.__init__` debug prints ("ControlPoly4_3L class Init"), 2 on an
Edge confirm, 8 on a Patch, 12 on a Blend, 25 on a Corner, growing with the
number of legacy maths instances a build happens to construct. They name a
class no user can act on, carry no state, and are identical every time. No test
in the suite asserted them (`grep "class Init" Tests/` = 0).

The two errors are the useful pattern the ticket asked to preserve: each names
the patch AND the property it refused to move
(`Silk: cannot set the band width on TubeA.USplit1 -- a width of 1 is not a
position inside the patch ...`). The five messages are the action lines: each
names the object created (`Edge created: Edge`, `Patch created: Patch`,
`Blend created across TubeA_left`, `Corner blend created: CornerBlend`, and the
cascade lines).

## The change: the measured noise removed

37 banner prints deleted from `ArachNURBS.py` (one per legacy class
`__init__`; the module's maths is untouched -- only the
`FreeCAD.Console.PrintMessage("\n<Class> class Init\n")` statements are gone).
The four identical prints in the three non-collected `ControlGridNStar66*`
modules were left alone: they are not on the wizard's path, and none of them
fired in the walk.

## Measured walk, after

| action | lines |
|---|---|
| edge confirm | 1 |
| patch confirm | 1 |
| blend confirm | 2 |
| band edit refused | 2 (errors) |
| corner confirm | 1 |
| delete cascade | 2 |
| **total** | **9** |

Every remaining line is an action line. **55 -> 9 lines (74 fewer, an 84%
reduction); banners 44 -> 0.**

Pinned by `Tests/test_console_noise.py`:
`test_a_full_build_writes_no_legacy_class_banner` (RED before the reduction --
the walk measured 44 banners) and
`test_the_build_still_says_what_it_did` (the action lines survive: the created
Patch is named, and the Blend says which seam it was created across).

## Inventory of the sites, grouped by action

Only the Python-side writers are listed; `Module.function` is the writer, and
the site is where the user meets it.

**Refusals (kept: name the offender).**
`SilkBlend._refuse` (band covers != 1 cell; patch has no subgrid at all);
`SilkPatch.execute` (boundary edge deleted; edges do not close a loop -- twice,
the fill's standalone path and the execute path; a non-Edge object in the
selection; a wrong edge count); `SilkMachinery.normalize_edge_pair` via
`SilkPatch.onChanged` (a split outside [0, 1], a swapped pair -- "correct it,
do not scold" plus the corrected values); `SilkWorkflowOps.resolve_seam` (0 / 1
/ 3+ referrers, three distinct sentences); `SilkWorkflowOps.create_patch`,
`create_corner_blend`, `create_corner_fill`, `create_fill`, `_build_fill`
(each names what did not close / did not build and says "Nothing was created");
`SilkCorner`, `SilkEdge`, `SilkWorkflowOps.create_edge` (selection shape);
`SilkTaskPanel._refuse` (stale entry / stale blend / band cells / band width --
console AND status line, deliberately the same sentence);
`SilkTaskPanel.write_band_split` (`band_width_problem`).

**Status: idempotent no-ops (kept).**
`SilkWorkflowOps.create_blend_by_edge` ("X and Y are already blended by Z -- no
second blend created"), `_existing_corner_blend` ("this junction already has a
corner blend (X)"), `SilkTaskPanel.confirm_blend` / `confirm_corner` (the
resolver's own words are re-used rather than a second sentence).

**Status: creations (kept, one line each).**
`SilkTaskPanel.confirm_edge` / `confirm_patch` / `confirm_blend` /
`confirm_corner`; `SilkWorkflowOps.create_fill` / `create_corner_fill`
("Silk: surface fill X created over N boundary edges"); the
`Silk_Create*` commands (`SilkEdge`, `SilkPatch`, `SilkBlend`).

**Cascade (kept, one line per removed dependent).**
`SilkBlend._cascade_one` -- and note it uses the `[Silk] ... cascaded with
deleted patch ...` prefix while everything else uses `Silk: ` (see the
grilling list).

**Not an action on geometry.** `SilkReloadManager` prints its own banner block
per hot reload (15 lines, not on the wizard path).

## For the grilling session (not decided here)

Each of these changes a user-facing message or its presence; the numbers above
do not settle them, so none was made.

1. **Prefix inconsistency.** The cascade line is the only one prefixed `[Silk]`;
   every other line is `Silk: ` or bare. Unify to one prefix? (94 -> 1 site.)
2. **Console duplicate of the status line.** Every panel creation writes the
   same sentence twice: once into `status_lbl`, once onto the console. Removing
   the console copy would need the tests that read it to change
   (`Tests/test_task_panel.py` asserts on captured console errors in several
   places, and `Tests/mcp_harness.py`'s `CaptureConsole` is how actions are
   observable headlessly). Keep both, or make the console copy opt-in?
3. **Success-line parity.** The ops layer prints a success line for Patch,
   Blend (via the resolver), Corner and fills, but `create_edge` prints none --
   the Edge line comes from its caller (panel / `SilkEdge` command). Make the
   ops layer uniform, or leave the caller owning it?
4. **`SilkReloadManager`'s banner block** (15 lines per hot reload) is developer
   plumbing, not a workbench action. Leave it, or gate it behind a flag?
5. **`SilkWorkflow.py`'s legacy command path** prints
   `SilkWorkflow: no active document.` and `select 3 or 4 BoundarySplines.` with
   no `Silk: ` prefix and no naming of the offenders (it names the count only)
   -- the only messages that do not follow the "name the offender" pattern.
   Retire, or reword to name what was selected?
