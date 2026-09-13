"""The Python and TypeScript pod rules must agree.

The desktop reaches pods through `gui/ipc/w2p_handlers/vehicle_handler.py`; the
web has no Python and talks to CloudBase directly through
`gui_v2/src/services/pods/podService.ts`, reading rows with
`gui_v2/src/types/domain/pod.ts`. Two implementations of the same rules is a
drift risk, and drift here is expensive: if the two disagree about which rows
are pods, a customer sees a different fleet depending on where they signed in.

These pin the parts that would silently diverge. They are deliberately
string/structure checks rather than a JS runtime — the aim is to fail loudly
when one side changes, not to re-run the TS.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / 'gui/ipc/w2p_handlers/vehicle_handler.py'
TS_MODEL = ROOT / 'gui_v2/src/types/domain/pod.ts'
TS_SERVICE = ROOT / 'gui_v2/src/services/pods/podService.ts'


@pytest.fixture(scope='module')
def src():
    return {
        'py': PY.read_text(encoding='utf-8'),
        'model': TS_MODEL.read_text(encoding='utf-8'),
        'service': TS_SERVICE.read_text(encoding='utf-8'),
    }


def test_both_sides_key_desired_state_on_the_same_settings_key(src):
    """If these diverge, each platform ignores the other's pods entirely."""
    py_key = re.search(r"POD_SETTINGS_KEY\s*=\s*'([^']+)'", src['py'])
    ts_key = re.search(r"POD_SETTINGS_KEY\s*=\s*'([^']+)'", src['model'])
    assert py_key and ts_key, 'POD_SETTINGS_KEY missing on one side'
    assert py_key.group(1) == ts_key.group(1) == 'pod'


def test_both_sides_use_the_same_desired_state_fields(src):
    py_fields = re.search(r"POD_DESIRED_FIELDS\s*=\s*\(([^)]*)\)", src['py'])
    assert py_fields, 'POD_DESIRED_FIELDS missing'
    names = set(re.findall(r"'([a-z_]+)'", py_fields.group(1)))
    assert names == {'lifecycle', 'idle_shutdown_minutes', 'desired_replicas'}
    for n in names:
        assert n in src['model'], f'{n} not handled in pod.ts'


def test_both_sides_discriminate_pods_the_same_way(src):
    """vehicle_type='cloud' AND a desired-state blob — never type alone.

    The fleet's own vehicle_register hard-codes 'cloud', so type alone would
    list runtime instances and rollout tombstones as the customer's pods.
    """
    py = re.search(r"def _is_customer_pod.*?\n\n\n", src['py'], re.S)
    ts = re.search(r"export function isCustomerPod.*?\n}", src['model'], re.S)
    assert py and ts, 'discriminator missing on one side'
    for body, where in ((py.group(0), 'python'), (ts.group(0), 'typescript')):
        assert 'cloud' in body or 'POD_VEHICLE_TYPE' in body, f'{where}: no vehicle_type check'
        assert 'ettings' in body or 'Blob' in body or 'blob' in body, f'{where}: no blob check'


def test_both_sides_read_columns_before_the_blob(src):
    """Once CN grows the columns, a blob written before the migration must lose."""
    assert 'column-first' in src['py'] or 'column-first' in src['py'].lower()
    assert 'column-first' in src['model']


def test_neither_side_sends_an_explicit_owner(src):
    """The server derives owner from the verified identity.

    Asserting it client-side is what produced "Cross-owner access is forbidden"
    for the WeChat account on 2026-09-08.
    """
    assert "'owner':" not in src['py'].split('# ===')[-1], 'python pod path sends owner'
    assert 'owner:' not in src['service'], 'web pod path sends owner'


def test_the_web_write_uses_camelcase_like_the_python_one(src):
    """CN resolvers read item.cpuCores and spread into Prisma.

    A snake_case payload passes SDL validation via the aliases and is then
    dropped by addVehicles or throws in updateVehicles.
    """
    for camel in ('vehicleType', 'cpuCores', 'memoryGb', 'maxConcurrentTasks'):
        assert camel in src['service'], f'{camel} missing from the web write'
    for snake in ('cpu_cores:', 'memory_gb:', 'vehicle_type:'):
        assert snake not in src['service'], f'{snake} would be dropped by the resolver'


def test_the_web_query_does_not_select_columns_that_do_not_exist():
    """Naming an absent field fails the WHOLE query, not just that field."""
    cfg = (ROOT / 'gui_v2/src/services/api/api-config.ts').read_text(encoding='utf-8')
    q = re.search(r'QUERY_VEHICLES:\s*`(.*?)`', cfg, re.S)
    assert q, 'QUERY_VEHICLES missing'
    body = q.group(1)
    for col in ('lifecycle', 'idle_shutdown_minutes', 'desired_replicas'):
        assert col not in body, f'{col} has no column on CN yet'
    for needed in ('settings', 'vehicle_type', 'cpu_cores', 'last_heartbeat'):
        assert needed in body, f'{needed} is needed to render a pod'


def test_remove_vehicles_passes_ids_on_the_web_too():
    cfg = (ROOT / 'gui_v2/src/services/api/api-config.ts').read_text(encoding='utf-8')
    m = re.search(r'REMOVE_VEHICLES:\s*`(.*?)`', cfg, re.S)
    assert m and 'removeVehicles(ids:' in m.group(1), 'the argument is ids, not input'


def test_pod_sizes_still_match_between_python_and_typescript(src):
    """Already covered for ids by test_unified_c3_placement; this pins the numbers."""
    from agent.pod_sizing import POD_SIZES

    ts = src['model']
    for size in POD_SIZES:
        pattern = (rf"id:\s*'{size['id']}',\s*cpu:\s*{size['cpu']},\s*"
                   rf"memory_gb:\s*{size['memory_gb']},\s*concurrency:\s*{size['concurrency']}")
        assert re.search(pattern, ts), f"{size['id']} differs between pod_sizing.py and pod.ts"
