"""Does the site-change detector actually work? Measured, not assumed.

The honest problem stated in `docs/SELF_HEALING_ROADMAP.md` §11: we have two
real site changes, both diagnosed after the fact, and the detector has never
fired on one. No labelled data, so no detection rate and no false-positive
rate.

This closes that, without waiting for a third redesign. It drives the **real**
fingerprint (`SIDEBAR_SHAPE_JS`, via `tools/emulation/fingerprint_probe.js`)
and the **real** decision path (`drift_journal.note_shape`) over row layouts
this site has actually shipped, plus synthetic mutations of them. Nothing is
reimplemented: a ported copy of either half would measure the copy.

What it reports is a coverage table — which *classes* of change are caught and
which are not. That is the useful answer. "The detector works" is not.
"""

import json
import pathlib
import shutil
import subprocess

import pytest

from agent.ec_skills.browser_use_extension import drift_journal as dj
from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    sidebar_preview_js as sp,
)

pytestmark = pytest.mark.skipif(not shutil.which("node"),
                                reason="node not installed")

ROOT = pathlib.Path(__file__).resolve().parents[2]
LAYOUTS_FILE = ROOT / "tools" / "emulation" / "layouts.json"
PROBE = ROOT / "tools" / "emulation" / "fingerprint_probe.js"
ROWS_PER_SCAN = 12


@pytest.fixture(autouse=True)
def journal_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_DRIFT_JOURNAL_DIR", str(tmp_path / "journal"))
    dj.reset_incident_window()
    yield
    dj.reset_incident_window()


@pytest.fixture(scope="module")
def layouts():
    data = json.loads(LAYOUTS_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


@pytest.fixture(scope="module")
def shape_js(tmp_path_factory):
    """The fingerprint as the app ships it, written where node can read it."""
    path = tmp_path_factory.mktemp("shape") / "shape.js"
    path.write_text(sp.SIDEBAR_SHAPE_JS, encoding="utf-8")
    return path


def fingerprint(shape_js, row_spec, tmp_path, n=ROWS_PER_SCAN):
    """Run the real fingerprint over n copies of a row description."""
    rows_file = tmp_path / "rows.json"
    rows_file.write_text(json.dumps([row_spec] * n), encoding="utf-8")
    out = subprocess.run(["node", str(PROBE), str(shape_js), str(rows_file)],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def detects(shape_js, tmp_path, before_spec, after_spec, key="row"):
    """Feed two layouts through the real decision path. True if it fired.

    Returns (fired, delta). The first sighting is a baseline by design, so the
    'before' layout is adopted first and only the second call can report.
    """
    dj.forget_shape("stress", key)
    dj.reset_incident_window()

    before = fingerprint(shape_js, before_spec, tmp_path)
    after = fingerprint(shape_js, after_spec, tmp_path)

    structural_before = {k: v for k, v in before.items() if k != "build_marker"}
    structural_after = {k: v for k, v in after.items() if k != "build_marker"}

    assert dj.note_shape("stress", key, structural_before) is None, "not a baseline"
    delta = dj.note_shape("stress", key, structural_after)
    return bool(delta), delta


# ── mutations: the classes of change a site can ship ───────────────────────

def _clone(spec):
    return json.loads(json.dumps(spec))


def _walk(spec):
    yield spec
    for kid in spec.get("children") or []:
        yield from _walk(kid)


def drop_attribute(spec, name="data-qa-id"):
    """The September rebuild: a machine id stops being emitted."""
    out = _clone(spec)
    for node in _walk(out):
        (node.get("attributes") or {}).pop(name, None)
    return out


def _rotate_token(tok):
    """Apply the site's own hash schemes to one class token."""
    import re
    m = re.fullmatch(r"([A-Za-z][A-Za-z0-9_]*)-([A-Za-z0-9_]{5,})", tok)
    if m and re.search(r"[A-Z0-9]", m.group(2)):
        return m.group(1) + "-Zz9Qw1"
    if (re.fullmatch(r"[A-Za-z0-9_]{16,}", tok)
            and re.search(r"[A-Z]", tok) and re.search(r"\d", tok)):
        return "Qq8Ww2Ee6Rr4Tt1Yy"
    return tok


def rename_hashes_routine(spec):
    """A deploy that rotates every hash EXCEPT ones we depend on by name.

    The common case: a rebuild that changes nothing we rely on. It must not
    reach the structural record, or deploy noise buries the real changes.
    """
    out = _clone(spec)
    for node in _walk(out):
        node["classes"] = [
            c if c in ANCHOR_TOKENS else _rotate_token(c)
            for c in (node.get("classes") or [])
        ]
    return out


def rename_hashes(spec):
    """A deploy that rotates EVERY hash, including anchors we depend on.

    Rotates both flavours the site uses -- `prefix-HASH` and fully opaque --
    because recognising only one of them was a real bug in the fingerprint.
    """
    out = _clone(spec)
    for node in _walk(out):
        node["classes"] = [_rotate_token(c) for c in (node.get("classes") or [])]
    return out


def rewrap(spec):
    """An extra wrapper div appears around the row's contents."""
    out = _clone(spec)
    out["children"] = [{"tag": "div", "classes": ["newWrapper-Aa1Bb2"],
                        "attributes": {}, "children": out.get("children") or []}]
    return out


def renest(spec):
    """Pure re-nesting: the same elements, one level deeper. No names change."""
    out = _clone(spec)
    for node in _walk(out):
        kids = node.get("children") or []
        if len(kids) >= 2:
            node["children"] = [{"tag": "div", "classes": [], "attributes": {},
                                 "children": kids}]
            break
    return out


def retag(spec):
    """div becomes section: a framework upgrade, not a redesign."""
    out = _clone(spec)
    for node in _walk(out):
        if node.get("tag") == "div":
            node["tag"] = "section"
    return out


def drop_anchor_element(spec, frag="nameLine"):
    """The element a parser keys on disappears entirely."""
    out = _clone(spec)

    def prune(node):
        kept = []
        for kid in node.get("children") or []:
            if any(frag in c for c in (kid.get("classes") or [])):
                kept.extend(kid.get("children") or [])   # promote its children
                continue
            prune(kid)
            kept.append(kid)
        node["children"] = kept

    prune(out)
    return out


def add_attribute(spec):
    """The site starts emitting something new."""
    out = _clone(spec)
    out.setdefault("attributes", {})["data-testid"] = "conversation-row"
    return out


# Tokens the parsers depend on BY LITERAL NAME. Rotating one of these is not a
# routine deploy -- it is that parser branch dying, which the detector SHOULD
# report. The distinction matters: conflating them is how you end up either
# crying wolf on every deploy or missing a real break.
ANCHOR_TOKENS = ("MP1bk3ccfHC9V2SnPCGD", "Jv6FtqUv5VoYARd2pp4y")


MUTATIONS = {
    "drop_attribute": drop_attribute,
    "rename_hashes_all": rename_hashes,
    "rename_hashes_routine": rename_hashes_routine,
    "rewrap": rewrap,
    "renest": renest,
    "retag": retag,
    "drop_anchor_element": drop_anchor_element,
    "add_attribute": add_attribute,
}


# ── the two real events ────────────────────────────────────────────────────

def test_it_catches_the_june_redesign(layouts, shape_js, tmp_path):
    """mt062 → the June rebuild. Hashed wrappers gone, semantic prefixes in."""
    fired, delta = detects(shape_js, tmp_path,
                           layouts["mt062_legacy"]["row"],
                           layouts["redesign_2026_06"]["row"])
    assert fired, "the June redesign went undetected"
    assert "anchors_present" in delta or "anchors_missing" in delta


def test_it_catches_the_september_rebuild(layouts, shape_js, tmp_path):
    """ws193: the nickname qa-id stops being emitted. This is the one that
    broke the click-open reader while the scan still worked."""
    fired, delta = detects(shape_js, tmp_path,
                           layouts["redesign_2026_06"]["row"],
                           layouts["rebuild_2026_09"]["row"])
    assert fired, "the September rebuild went undetected"
    lost = json.dumps(delta)
    assert "data_qa_id_nickname" in lost, (
        f"the vanished anchor is not named in the delta: {lost[:300]}")


def test_the_same_layout_twice_is_never_a_change(layouts, shape_js, tmp_path):
    """The false-positive floor. If this fires, nothing else here means much."""
    for name, layout in layouts.items():
        fired, _ = detects(shape_js, tmp_path, layout["row"], layout["row"],
                           key=f"same_{name}")
        assert not fired, f"{name} reported a change against itself"


# ── coverage per mutation class ────────────────────────────────────────────

@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
def test_mutation_coverage(mutation, layouts, shape_js, tmp_path, record_property):
    """Records which classes of change are caught. Asserts only the ones we
    have decided must be caught — the rest are measured, not demanded, and the
    honest answer is written into `docs/SELF_HEALING_ROADMAP.md`."""
    base = layouts["redesign_2026_06"]["row"]
    fired, delta = detects(shape_js, tmp_path, base, MUTATIONS[mutation](base),
                           key=f"mut_{mutation}")
    record_property(f"detects_{mutation}", fired)

    # Must be caught: these are the shapes the two real incidents took.
    if mutation in ("drop_attribute", "drop_anchor_element"):
        assert fired, (
            f"{mutation} is the shape of a real incident and went undetected")

    # Rotating a token we depend on BY NAME is a parser branch dying, so it
    # must be caught.
    if mutation == "rename_hashes_all":
        assert fired, "a rotation that killed an anchor went undetected"

    # A rotation that leaves our anchors alone is a routine deploy. Reporting it
    # on the structural record would bury real changes under deploy noise; the
    # deploy marker is what notices it — see the test below.
    if mutation == "rename_hashes_routine":
        assert not fired, (
            "a routine hash rotation must not register as a structural change")


def test_a_hash_rotation_moves_the_deploy_marker_instead(layouts, shape_js,
                                                         tmp_path):
    """The other half of the split: invisible to the structural record, visible
    as 'they shipped today'. That is the deploy calendar."""
    base = layouts["redesign_2026_06"]["row"]
    before = fingerprint(shape_js, base, tmp_path)
    after = fingerprint(shape_js, rename_hashes_routine(base), tmp_path)

    assert before["build_marker"] and after["build_marker"]
    assert before["build_marker"]["digest"] != after["build_marker"]["digest"], (
        "a deploy that rotated every hash did not move the deploy marker")


def test_the_detector_is_not_fooled_by_how_many_rows_were_sampled(layouts,
                                                                 shape_js,
                                                                 tmp_path):
    """Scroll position decides how many rows a scan sees. If that moves the
    fingerprint, the journal fills with phantom changes several times an hour."""
    base = layouts["redesign_2026_06"]["row"]
    few = fingerprint(shape_js, base, tmp_path, n=3)
    many = fingerprint(shape_js, base, tmp_path, n=30)

    strip = lambda f: {k: v for k, v in f.items()
                       if k not in ("rows_sampled", "build_marker")}
    # hashed_classes_per_row is normalised, so it must survive the comparison
    assert few["hashed_classes_per_row"] == many["hashed_classes_per_row"]
    assert strip(few) == strip(many)
    assert few["build_marker"]["digest"] == many["build_marker"]["digest"]


def test_coverage_summary(layouts, shape_js, tmp_path, capsys):
    """Prints the table. Run with -s to read it."""
    base = layouts["redesign_2026_06"]["row"]
    rows = []
    for name in sorted(MUTATIONS):
        fired, _ = detects(shape_js, tmp_path, base, MUTATIONS[name](base),
                           key=f"sum_{name}")
        rows.append((name, fired))

    with capsys.disabled():
        print("\n  detector coverage, structural record:")
        for name, fired in rows:
            print(f"    {'DETECTED    ' if fired else 'not detected'}  {name}")

    caught = sum(1 for _, f in rows if f)
    assert caught >= 3, f"only {caught}/{len(rows)} mutation classes detected"
