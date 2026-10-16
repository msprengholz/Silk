"""Upstream corner-type register + drift guard (ticket)."""

import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import silk_reload  # noqa: E402

MOD_DIR = silk_reload.MOD_DIR
ARACH = os.path.join(MOD_DIR, "ArachNURBS.py")
DOC = os.path.join(MOD_DIR, "docs", "research", "silk-upstream-type-register.md")
DEMOS = os.path.join(MOD_DIR, "Resources", "Demo_files")
REGEX = re.compile(r"(Grid|Surface).*(66.*Sub|64.*Grid44|Grid44.*EdgeSegments|NStar|StarTrim)")


def _read_classes():
    out = []
    if os.path.isfile(ARACH):
        with open(ARACH) as f:
            for m in re.finditer(r"^class\s+([A-Za-z0-9_]+)", f.read(), re.M):
                out.append(m.group(1))
    return out


def _curated_known():
    known = set()
    for c in _read_classes():
        if REGEX.search(c):
            known.add(c)
    if os.path.isdir(DEMOS):
        for fn in os.listdir(DEMOS):
            if not fn.endswith(".FCStd"):
                continue
            path = os.path.join(DEMOS, fn)
            try:
                z = zipfile.ZipFile(path)
                xml = z.read("Document.xml").decode("utf-8", "ignore")
            except Exception:
                continue
            for c in _read_classes():
                if c in xml:
                    known.add(c)
    for c in ("SubGrid33_2Grid64", "SubGrid63_2Surf64",
              "CubicSurface_44", "CubicSurface_64", "CubicSurface_66",
              "CubicCurve_4"):
        known.add(c)
    return known


def _doc_text():
    with open(DOC) as f:
        return f.read()


def _row_types():
    types = []
    for line in _doc_text().splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5:
            continue
        if cells[0].lower() == "type":
            continue
        types.append(cells[0])
    return types


def _covered(name, types):
    if name in _doc_text():
        return True
    for t in types:
        if "*" in t:
            prefix = t.split("*")[0].rstrip()
            if name.startswith(prefix):
                return True
    return False


def _ok(errors, checks):
    return {"pass": not errors, "errors": errors, "checks": checks}


def test_register_doc_exists(doc):
    errors, checks = [], []
    if not os.path.isfile(DOC):
        errors.append("register doc missing")
    else:
        checks.append("register doc present")
    return _ok(errors, checks)


def test_register_min_row_count(doc):
    errors, checks = [], []
    types = _row_types()
    if len(types) < 18:
        errors.append("fewer than 18 rows: %d" % len(types))
    else:
        checks.append("%d register rows" % len(types))
    return _ok(errors, checks)


def test_distinguish_upstream_arachnurbs_classes(doc):
    errors, checks = [], []
    classes = _read_classes()
    if not classes:
        errors.append("no classes parsed from ArachNURBS.py")
    else:
        checks.append("%d classes in ArachNURBS.py" % len(classes))
    grid_surface = [c for c in classes if "Grid" in c or "Surface" in c]
    checks.append("%d Grid/Surface-relevant classes" % len(grid_surface))
    if "Grid" not in _doc_text() and "Surface" not in _doc_text():
        errors.append("doc does not mention Grid/Surface")
    return _ok(errors, checks)


def test_register_doc_covers_every_arachnurbs_corner_type(doc):
    errors, checks = [], []
    types = _row_types()
    known = _curated_known()
    missing = []
    for name in sorted(known):
        if not _covered(name, types):
            missing.append(name)
    if missing:
        errors.append("curated upstream classes absent from register: %s" % missing)
    else:
        checks.append("all %d curated upstream classes covered" % len(known))
    return _ok(errors, checks)


def test_no_continuity_claims(doc):
    errors, checks = [], []
    low = _doc_text().lower()
    if "g1" in low and "threshold" in low:
        errors.append("continuity threshold language present")
    else:
        checks.append("no continuity thresholds")
    return _ok(errors, checks)


ALL_TESTS = [
    test_register_doc_exists,
    test_register_min_row_count,
    test_distinguish_upstream_arachnurbs_classes,
    test_register_doc_covers_every_arachnurbs_corner_type,
    test_no_continuity_claims,
]
