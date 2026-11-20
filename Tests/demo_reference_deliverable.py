"""Build, verify and save the Demo 01 rebuild that copies his corner setup.

Runs inside FreeCAD over RPC:

    flock /tmp/silk_rpc.lock -c "python3 Tests/demo_reference_deliverable.py"

The artifact is Resources/Test_files/_inspect/demo01_replayed_reference.FCStd.
This is a DELIVERABLE script, not a test module (no test_ prefix).
"""

import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
ARTIFACT = os.path.join(REPO, "Resources", "Test_files", "_inspect",
                        "demo01_replayed_reference.FCStd")
TABLE = os.path.join(REPO, "Resources", "Test_files", "_inspect",
                     "reference_replay_verified.txt")

BOOT = """import sys, traceback, os, time
sys.path.insert(0, __REPO__)
sys.path.insert(0, __HERE__)
for m in list(sys.modules.keys()):
    if m.startswith(('Silk','Tests','ArachNURBS','demo01','demo_reference')):
        del sys.modules[m]
import FreeCAD, FreeCADGui, SilkChecks as CK, SilkCorner as SC
import SilkMachinery as SM, demo_reference_replay as R
out=[]
try:
    records, result, doc = R.replay_in_new_document()
    doc.recompute(); doc.recompute()
    his={'CB_J1_FrontTopRight':1931.0,'CB_J2_FrontRightBottom':955.6,
         'CB_J3_TopRightBack':1982.5,'CB_J4_RightBottomBack':1532.0}
    out.append('fixture: %d sketches, %d edges, %d patches, %d blends, %d corners'
        % tuple(sum(1 for o in doc.Objects if (getattr(o,'object_type','') or o.TypeId)==t)
                for t in ('Sketcher::SketchObject','Edge','Patch','Blend','CornerBlend')))
    out.append('replay problems: %r' % (result['problems'],))
    out.append('refusals printed verbatim above in the replay log')
    seen={}
    for c in [o for o in doc.Objects if getattr(o,'object_type','')=='CornerBlend']:
        bad=[x for x in CK.check_corner_blend(c,*list(c.Strips)) if not x[1]]
        coins=sum(1 for i in range(len(c.Poles)) for j in range(i+1,len(c.Poles))
                  if (c.Poles[i]-c.Poles[j]).Length<=1e-6)
        folds=SM.net_fold_count(list(c.Poles),list(c.Weights))
        pin=SC.recorded_member_pin(c)
        seen[c.Name]=(tuple(tuple(round(x,9) for x in p) for p in c.Poles),
                      tuple(round(f.Area,6) for f in c.Shape.Faces),
                      tuple(getattr(c,'ReservedCells',[]) or []))
        area=max(f.Area for f in c.Shape.Faces)
        out.append('%s: %s member=%s[%d] poles=%d faces=%d cells=%d area=%.1f '
                   'his=%.1f delta=%+.1f%% coins=%d folds=%d oracle_bad=%r' % (
             c.Name,SC.corner_construction(c)[0],pin[0].Name,pin[1],
             len(c.Poles),len(c.Shape.Faces),
             len(getattr(c,'ReservedCells',[]) or []),
             area,his[c.Name],(area-his[c.Name])/his[c.Name]*100.0,
             coins,folds,bad))
    t=time.time()
    for _ in range(3): doc.recompute()
    out.append('3x recompute %.4fs touched=%r'%(time.time()-t,
        [o.Name for o in doc.Objects if 'Touched' in o.State]))
    # presentation: reference sketches/edges hidden, surfaces shown
    for o in doc.Objects:
        t=(getattr(o,'object_type','') or o.TypeId)
        if t in ('Sketcher::SketchObject','Edge'):
            o.ViewObject.Visibility=False
        elif t in ('Patch','Blend','CornerBlend'):
            o.ViewObject.Visibility=True
    doc.recompute(); doc.recompute()
    FreeCAD.setActiveDocument(doc.Name)
    doc.saveAs(__ARTIFACT__)
    out.append('SAVED %s (%d bytes)'%(__ARTIFACT__,os.path.getsize(__ARTIFACT__)))
    FreeCAD.closeDocument(doc.Name)
    again=FreeCAD.openDocument(__ARTIFACT__)
    again.recompute(); again.recompute()
    after={c.Name:(tuple(tuple(round(x,9) for x in p) for p in c.Poles),
                   tuple(round(f.Area,6) for f in c.Shape.Faces),
                   tuple(getattr(c,'ReservedCells',[]) or []))
           for c in again.Objects if getattr(c,'object_type','')=='CornerBlend'}
    out.append('reopen byte-identical=%s (%d corners)'%(seen==after,len(after)))
    out.append('reopen touched=%r'%[o.Name for o in again.Objects if 'Touched' in o.State])
    text='\\n'.join(out)+'\\n'
    open(__TABLE__,'w').write(text)
    print(text)
except Exception:
    print(traceback.format_exc())
""".replace("__REPO__", repr(REPO)).replace("__HERE__", repr(HERE)) \
   .replace("__ARTIFACT__", repr(ARTIFACT)).replace("__TABLE__", repr(TABLE))

if __name__ == "__main__":
    import xmlrpc.client
    result = xmlrpc.client.ServerProxy("http://127.0.0.1:9875").execute_code(BOOT)
    print(result.get("output", ""))
    if result.get("error"):
        print("RPC ERROR:", result["error"])
