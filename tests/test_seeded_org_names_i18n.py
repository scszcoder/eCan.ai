"""The seeded departments show in the UI language.

`organization_template.json` seeds every account with the same departments and
stores their names in the DB in English, so a CN build showed "Sales" and
"Finance" next to otherwise-Chinese UI. They are data, not UI strings, so
i18next cannot reach them — the door renderer translates them by the template's
stable id instead.

That makes three things that have to stay in step: the template, the TS id map,
and both locale files. These fail loudly when one of them moves.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'agent/ec_agents/organization_template.json'
TS_MAP = ROOT / 'gui_v2/src/pages/Orgs/defaultOrgNames.ts'
# The LIVE render site. `hooks/useOrgDoorRenderer.tsx` renders OrgDoor too and
# looks like the right place — but it has no callers, and wiring it there
# changed nothing on screen while this test passed. Assert against the file
# that actually renders, and prove it is reachable.
RENDERER = ROOT / 'gui_v2/src/pages/Agents/OrgNavigator.tsx'
DEAD_HOOK = ROOT / 'gui_v2/src/pages/Agents/hooks/useOrgDoorRenderer.tsx'


def _template_orgs() -> dict:
    """Every {id: name} in the seeded template."""
    found = {}

    def walk(node):
        if isinstance(node, dict):
            if 'id' in node and 'name' in node:
                found[str(node['id'])] = str(node['name'])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(json.loads(TEMPLATE.read_text(encoding='utf-8')))
    return found


def _ts_map() -> dict:
    body = re.search(r'SEEDED_ORG_DEFAULT_NAMES[^{]*\{(.*?)\n\};', TS_MAP.read_text(encoding='utf-8'), re.S)
    assert body, 'SEEDED_ORG_DEFAULT_NAMES not found'
    return dict(re.findall(r"(\w+):\s*'([^']*)'", body.group(1)))


def _locale(loc: str) -> dict:
    data = json.loads((ROOT / f'gui_v2/src/i18n/locales/{loc}.json').read_text(encoding='utf-8'))
    return data['pages']['agents'].get('departments', {})


def test_the_ts_map_matches_the_python_template():
    """If a seeded name changes, the rename guard stops translating it.

    seededOrgNameKey only returns a key while the stored name still equals the
    seeded default — so a drifted map silently disables the feature rather than
    showing something wrong, which is the harder bug to notice.
    """
    template = _template_orgs()
    for org_id, name in _ts_map().items():
        assert org_id in template, f'{org_id} is not in organization_template.json'
        assert template[org_id] == name, (
            f'{org_id}: template says {template[org_id]!r}, TS map says {name!r}')


@pytest.mark.parametrize('loc', ['en-US', 'zh-CN'])
def test_every_mapped_department_has_a_translation(loc):
    missing = sorted(set(_ts_map()) - set(_locale(loc)))
    assert not missing, f'{loc} is missing {missing}'


@pytest.mark.parametrize('loc', ['en-US', 'zh-CN'])
def test_no_translation_is_left_dangling(loc):
    """A key for an org nothing maps is dead weight and misleads the next reader."""
    extra = sorted(set(_locale(loc)) - set(_ts_map()))
    assert not extra, f'{loc} translates {extra}, which the TS map does not cover'


def test_the_chinese_names_are_actually_chinese():
    """The point of the exercise."""
    zh = _locale('zh-CN')
    for org_id, name in zh.items():
        assert re.search(r'[一-鿿]', name), f'{org_id} is still {name!r}'


def test_english_keeps_the_template_wording():
    """intl must be unchanged by this — same words, now via a key."""
    template = _template_orgs()
    for org_id, name in _locale('en-US').items():
        assert name == template[org_id], f'{org_id}: {name!r} != {template[org_id]!r}'


def test_the_company_root_is_not_translated():
    """eCan.ai is a brand, not a word."""
    assert 'org_root_001' not in _ts_map()
    for loc in ('en-US', 'zh-CN'):
        assert 'org_root_001' not in _locale(loc)


def test_the_renderer_uses_the_lookup():
    """Without this wiring the map and the keys exist and change nothing."""
    src = RENDERER.read_text(encoding='utf-8')
    assert 'seededOrgNameKey' in src
    # i18next echoes a missing key back; translating to the key itself would
    # put "pages.agents.departments.org_sales_001" on the door.
    assert 'translated !== seededKey' in src


def test_the_file_under_test_is_the_one_that_renders():
    """The first cut patched a hook with no callers and nothing changed.

    A test asserting "the renderer calls the lookup" is worthless if it is
    pointed at a file nothing imports, so check reachability too.
    """
    src = RENDERER.read_text(encoding='utf-8')
    assert '<OrgDoor' in src, 'RENDERER does not render OrgDoor'

    root = ROOT / 'gui_v2/src'
    stem = RENDERER.stem
    importers = [
        f for f in root.rglob('*.tsx')
        if f != RENDERER and stem in f.read_text(encoding='utf-8')
    ]
    assert importers, f'nothing references {stem}; it would be dead code'


def test_the_dead_hook_is_still_dead():
    """Guard the trap rather than pretend it is gone.

    useOrgDoorRenderer duplicates this logic and has no callers. If it ever
    gains one, the two copies must be reconciled — or the CN names will differ
    depending on which path renders.
    """
    root = ROOT / 'gui_v2/src'
    callers = [
        f for f in root.rglob('*.ts*')
        if f != DEAD_HOOK and 'useOrgDoorRenderer' in f.read_text(encoding='utf-8')
    ]
    assert not callers, (
        'useOrgDoorRenderer now has callers: ' + ', '.join(str(c) for c in callers) +
        ' — reconcile it with OrgNavigator or delete one')
