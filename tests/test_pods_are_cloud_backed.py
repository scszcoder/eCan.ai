"""Pods live in the cloud, and the vehicle GraphQL matches what CN actually reads.

Before this, `save_pod` wrote the local DB and stopped — a pod created on the
desktop existed only on that machine, which is why one never appeared in the web
app. These assert the pod actually leaves the box, and that the vehicle
generators speak the dialect the CN resolvers parse rather than one that passes
validation and is then silently dropped.

Reference for every "the resolver does X" claim below:
``eCan_lambda/cn/tencent/cloudbase-graphql/scf/resolvers/entities.js`` —
``addVehicles`` reads ``item.cpuCores``, ``updateVehicles`` spreads its input
straight into Prisma, and ``removeVehicles`` destructures ``{ ids }``.
"""

import json

import pytest

from gui.ipc.types import create_request


# ---------------------------------------------------------------------------
# The wire format
# ---------------------------------------------------------------------------

def test_remove_vehicles_passes_ids_not_input():
    """``removeVehicles(ids: [ID!]!)`` — the old generator sent ``input:``.

    It had no production caller, so the mismatch had never been executed.
    """
    from agent.cloud_api.cloud_api import gen_remove_vehicles_string

    q = gen_remove_vehicles_string(["pod_abc123"])

    assert "removeVehicles(ids: [" in q
    assert "input:" not in q
    assert '"pod_abc123"' in q


def test_add_vehicles_emits_camelcase_the_resolver_reads():
    """Snake_case passes validation via the SDL aliases and is then dropped.

    ``addVehicles`` reads ``item.vehicleType`` / ``item.cpuCores`` directly, so a
    snake_case payload would create a pod with no type and no size — which is
    worse than an error, because it looks like it worked.
    """
    from agent.cloud_api.cloud_api import gen_add_vehicles_string

    q = gen_add_vehicles_string([{
        "id": "pod_1", "name": "p", "vehicle_type": "cloud",
        "cpu_cores": 2, "memory_gb": 4.0, "max_concurrent_tasks": 3,
    }])

    for camel in ("vehicleType:", "cpuCores:", "memoryGb:", "maxConcurrentTasks:"):
        assert camel in q, f"{camel} missing — resolver will not see it"
    for snake in ("vehicle_type:", "cpu_cores:", "memory_gb:", "max_concurrent_tasks:"):
        assert snake not in q, f"{snake} would be dropped by the resolver"


def test_update_vehicles_sends_only_what_was_set_and_never_owner():
    """Update spreads into Prisma, so every key sent is a key overwritten."""
    from agent.cloud_api.cloud_api import gen_update_vehicles_new_string

    q = gen_update_vehicles_new_string([{"id": "pod_1", "status": "online"}])

    assert 'id: "pod_1"' in q
    assert "status:" in q
    assert "name:" not in q, "an unset field must be left alone, not blanked"
    assert "owner:" not in q, "the resolver deletes owner and scopes by identity"


def test_json_fields_are_graphql_literals_not_json_strings():
    """``capabilities``/``settings`` are the ``JSON`` scalar on CN, not AWSJSON.

    The old code embedded them as quoted strings, which stores the literal text
    ``'["a"]'``. GraphQL object keys are also unquoted, so ``json.dumps`` of a
    dict is a syntax error here, not merely the wrong shape.
    """
    from agent.cloud_api.cloud_api import gen_add_vehicles_string, gql_literal

    assert gql_literal(["a", "b"]) == '["a", "b"]'
    assert gql_literal({"lifecycle": "always_on"}) == '{lifecycle: "always_on"}'
    assert gql_literal(None) == "null"
    assert gql_literal(True) == "true"

    q = gen_add_vehicles_string([{"name": "p", "capabilities": ["dedicated:agent_x"]}])
    assert 'capabilities: ["dedicated:agent_x"]' in q
    assert 'capabilities: "[' not in q, "a quoted string would persist as text"


def test_query_vehicles_filters_by_owner_and_gates_the_pod_columns():
    """The pod columns do not exist on CN yet.

    Naming one in a selection set fails the WHOLE query with
    GRAPHQL_VALIDATION_FAILED, so they have to be opt-in.
    """
    from agent.cloud_api.cloud_api import gen_query_vehicles_string

    lean = gen_query_vehicles_string({"owner": "o3YBk2"})
    assert 'owner: "o3YBk2"' in lean
    assert "settings" in lean, "the desired-state blob has to come back"
    assert "last_heartbeat" in lean, "observed state the fleet reports"
    for col in ("lifecycle", "idle_shutdown_minutes", "desired_replicas"):
        assert col not in lean

    rich = gen_query_vehicles_string({}, with_pod_columns=True)
    for col in ("lifecycle", "idle_shutdown_minutes", "desired_replicas"):
        assert col in rich


# ---------------------------------------------------------------------------
# Desired state survives a backend that has no columns for it
# ---------------------------------------------------------------------------

def test_pod_view_reads_desired_state_out_of_the_settings_blob():
    """Today's backend: no columns, so the blob is the only copy."""
    from gui.ipc.w2p_handlers.vehicle_handler import _pod_view

    view = _pod_view({
        "id": "pod_1", "name": "p", "vehicle_type": "cloud",
        "cpu_cores": 2, "memory_gb": 4,
        "settings": {"pod": {"lifecycle": "on_demand",
                             "idle_shutdown_minutes": 15,
                             "desired_replicas": 3}},
    })

    assert view["lifecycle"] == "on_demand"
    assert view["idle_shutdown_minutes"] == 15
    assert view["desired_replicas"] == 3


def test_pod_view_prefers_a_real_column_over_the_blob():
    """After the migration the column is authoritative; a stale blob must lose."""
    from gui.ipc.w2p_handlers.vehicle_handler import _pod_view

    view = _pod_view({
        "id": "pod_1", "name": "p", "cpu_cores": 2, "memory_gb": 4,
        "desired_replicas": 4,
        "settings": {"pod": {"desired_replicas": 1}},
    })

    assert view["desired_replicas"] == 4


def test_pod_view_parses_settings_that_arrive_as_a_string():
    """Some backends hand JSON columns back encoded."""
    from gui.ipc.w2p_handlers.vehicle_handler import _pod_view

    view = _pod_view({
        "id": "pod_1", "name": "p", "cpu_cores": 2, "memory_gb": 4,
        "settings": json.dumps({"pod": {"desired_replicas": 2}}),
    })

    assert view["desired_replicas"] == 2


def test_pod_view_accepts_camelcase_sized_fields():
    """``withSnakeMirrors`` is the server's courtesy, not a guarantee."""
    from gui.ipc.w2p_handlers.vehicle_handler import _pod_view

    view = _pod_view({"id": "p", "name": "p", "cpuCores": 8, "memoryGb": 16,
                      "maxConcurrentTasks": 4, "lastHeartbeat": "2026-09-13T00:00:00Z"})

    assert view["cpu_cores"] == 8
    assert view["memory_gb"] == 16
    assert view["max_concurrent_tasks"] == 4
    assert view["last_heartbeat"] == "2026-09-13T00:00:00Z"


# ---------------------------------------------------------------------------
# The handlers go to the cloud
# ---------------------------------------------------------------------------

@pytest.fixture
def cloud(monkeypatch):
    """Stub the cloud context and record what each handler sends."""
    from gui.ipc.w2p_handlers import vehicle_handler as vh

    monkeypatch.setattr(vh, "_pod_columns_supported", False, raising=False)
    monkeypatch.setattr(vh, "_cloud_ctx", lambda: {
        "session": object(), "token": "t", "endpoint": "https://x/graphql",
    })

    sent = {}

    def _add(session, vehicles, token, endpoint, **kw):
        sent["add"] = vehicles
        return [{"id": vehicles[0]["id"], "success": True}]

    def _update(session, vehicles, token, endpoint, **kw):
        sent["update"] = vehicles
        return [{"id": vehicles[0]["id"], "success": True}]

    def _remove(session, ids, token, endpoint, **kw):
        sent["remove"] = ids
        return [{"id": ids[0], "success": True}]

    import agent.cloud_api.cloud_api as api
    monkeypatch.setattr(api, "send_add_vehicles_request_to_cloud", _add)
    monkeypatch.setattr(api, "send_update_vehicles_decorated_to_cloud", _update)
    monkeypatch.setattr(api, "send_remove_vehicles_request_to_cloud", _remove)
    monkeypatch.setattr(vh, "_query_pod_rows", lambda ctx: sent.get("rows", []))
    return sent


def test_saving_a_pod_writes_it_to_the_cloud(cloud):
    """The whole point: the pod leaves the machine."""
    from gui.ipc.w2p_handlers.vehicle_handler import handle_save_pod

    resp = handle_save_pod(create_request("save_pod"), {
        "name": "cs-pod", "cpu_cores": 2, "memory_gb": 4,
        "lifecycle": "on_demand", "idle_shutdown_minutes": 10,
        "desired_replicas": 2,
    })

    assert resp["status"] == "success", resp
    assert "add" in cloud, "nothing was sent to the cloud"
    row = cloud["add"][0]
    assert row["vehicle_type"] == "cloud"
    assert row["id"].startswith("pod_")
    # owner is the server's to decide. Asserting it client-side is what got
    # "Cross-owner access is forbidden" on 2026-09-08, when this account's
    # identity.sub matched neither the prefixed nor the bare openid.
    assert "owner" not in row


def test_desired_state_is_always_written_to_settings(cloud):
    """The blob is what a backend without the columns reads back."""
    from gui.ipc.w2p_handlers.vehicle_handler import handle_save_pod

    handle_save_pod(create_request("save_pod"), {
        "name": "cs-pod", "cpu_cores": 2, "memory_gb": 4,
        "lifecycle": "on_demand", "idle_shutdown_minutes": 10,
        "desired_replicas": 2,
    })

    blob = cloud["add"][0]["settings"]["pod"]
    assert blob == {"lifecycle": "on_demand",
                    "idle_shutdown_minutes": 10,
                    "desired_replicas": 2}


def test_columns_are_not_sent_to_a_backend_that_lacks_them(cloud):
    """updateVehicles spreads into Prisma — an unknown key throws."""
    from gui.ipc.w2p_handlers.vehicle_handler import handle_save_pod

    handle_save_pod(create_request("save_pod"), {
        "name": "cs-pod", "cpu_cores": 2, "memory_gb": 4, "desired_replicas": 2,
    })

    row = cloud["add"][0]
    for col in ("lifecycle", "idle_shutdown_minutes", "desired_replicas"):
        assert col not in row, f"{col} has no column on this backend"


def test_columns_are_sent_once_the_backend_has_them(cloud, monkeypatch):
    from gui.ipc.w2p_handlers import vehicle_handler as vh

    monkeypatch.setattr(vh, "_pod_columns_supported", True, raising=False)
    vh.handle_save_pod(create_request("save_pod"), {
        "name": "cs-pod", "cpu_cores": 2, "memory_gb": 4, "desired_replicas": 2,
    })

    row = cloud["add"][0]
    assert row["desired_replicas"] == 2
    assert row["settings"]["pod"]["desired_replicas"] == 2, "blob stays as the fallback"


def test_deleting_a_pod_deletes_it_in_the_cloud(cloud):
    from gui.ipc.w2p_handlers.vehicle_handler import handle_delete_pod

    resp = handle_delete_pod(create_request("delete_pod"), {"id": "pod_1"})

    assert resp["status"] == "success", resp
    assert cloud["remove"] == ["pod_1"]


def test_an_unreachable_cloud_is_an_error_not_an_empty_list(monkeypatch):
    """[] renders as "you have no pods" and invites a second paid pod."""
    from gui.ipc.w2p_handlers import vehicle_handler as vh

    monkeypatch.setattr(vh, "_cloud_ctx", lambda: {
        "session": object(), "token": "t", "endpoint": "e"})

    def _boom(ctx):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(vh, "_query_pod_rows", _boom)

    resp = vh.handle_get_pods(create_request("get_pods"), {})

    assert resp["status"] == "error"
    assert resp["error"]["code"] == "CLOUD_UNREACHABLE"


def test_signed_out_is_told_so_rather_than_shown_nothing(monkeypatch):
    from gui.ipc.w2p_handlers import vehicle_handler as vh

    monkeypatch.setattr(vh, "_cloud_ctx", lambda: None)

    resp = vh.handle_get_pods(create_request("get_pods"), {})

    assert resp["status"] == "error"
    assert resp["error"]["code"] == "NO_CLOUD"


def test_get_pods_returns_only_pods_not_machines(monkeypatch):
    """The owner's cloud vehicles include desktops registered by affinity."""
    from gui.ipc.w2p_handlers import vehicle_handler as vh

    monkeypatch.setattr(vh, "_cloud_ctx", lambda: {
        "session": object(), "token": "t", "endpoint": "e"})
    monkeypatch.setattr(vh, "_query_pod_rows", lambda ctx: [
        {"id": "pod_1", "name": "p", "vehicle_type": "cloud",
         "cpu_cores": 2, "memory_gb": 4},
        {"id": "m_1", "name": "laptop", "vehicle_type": "desktop",
         "cpu_cores": 8, "memory_gb": 16},
    ])

    resp = vh.handle_get_pods(create_request("get_pods"), {})

    assert resp["status"] == "success", resp
    assert [p["id"] for p in resp["result"]["pods"]] == ["pod_1"]


def test_missing_pod_columns_is_told_apart_from_a_real_failure():
    """Falling back on any error would make an outage look like an old schema."""
    from gui.ipc.w2p_handlers.vehicle_handler import _is_missing_pod_columns

    schema = Exception('queryVehicles failed: Cannot query field '
                       '"desired_replicas" on type "Vehicle". '
                       'GRAPHQL_VALIDATION_FAILED')
    outage = Exception("queryVehicles failed: Unexpected error.")

    assert _is_missing_pod_columns(schema)
    assert not _is_missing_pod_columns(outage)
