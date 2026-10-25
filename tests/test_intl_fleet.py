"""The intl edition sends fleet/store/transfer/turn/pod/usage calls to AppSync.

On CN these are ``ecbAccountManager`` actions; AppSync has no such route, so on
intl every one of them used to come back HTTP 404. ``intl_fleet`` maps each
action to its AppSync field and answers in the CN shape, so the callers above it
keep their own status and ``success`` checks.

What is pinned here:

* the document and variables each action sends (AWSJSON as a JSON *string*);
* the owner never leaves the client, and the internal token is never used;
* every server answer (success, refusal, missing operation, expired session,
  transport failure) maps to what the CN route would have said;
* the missing-operation case reaches the Stores page as one readable sentence;
* CN is untouched: with ``ECAN_APP_ID=cn`` nothing goes near AppSync.
"""

import json
from unittest import mock

import pytest

from agent.cloud_api import intl_fleet, store_api, turn_queue
from agent.ec_skills import metering_reporter as reporter


OK_LIST = {"data": {"getStores": json.dumps({
    "stores": [{"storeId": "s1", "status": "active", "assignedVehicleId": "m1",
                "assignedVehicleOnline": True, "reportedVehicleId": None,
                "reportedVehicleOnline": None, "misplaced": False, "loginState": "ok",
                "loginStateAt": None, "lastReportedAt": None, "profile": {},
                "storeUrls": [], "platform": "", "label": "S1"}],
    "needsLogin": 0, "misplaced": 0})}}
REFUSED = {"data": {"assignStore": json.dumps(
    {"success": False, "error": "not_found: no machine m9 is registered to this account"})}}
CLAIM_WON = {"data": {"claimStore": json.dumps(
    {"won": True, "store": {"storeId": "s1", "assignedVehicleId": "m1"}})}}
ARCHIVED = {"data": {"archiveStore": json.dumps({"store": {"storeId": "s1", "status": "archived"}})}}
UNDEFINED = {"errors": [{"message": "Validation error of type FieldUndefined: Field 'getStores' "
                                    "in type 'Query' is undefined @ 'getStores'"}]}
UNAUTH = {"errors": [{"errorType": "UnauthorizedException", "message": "Token has expired."}]}
TRANSPORT = {"errors": [{"errorType": "RequestError", "message": "boom"}]}
INSUFF = {"data": {"getStores": {"success": False, "error": "ACCOUNT INSUFFICIENT"}}}
USAGE_OK = {"data": {"reportUsageEvents": {
    "accepted": 1, "duplicates": 1,
    "rejected": [{"idempotency_key": "k3", "reason": "unknown_meter"}]}}}


@pytest.fixture
def appsync(monkeypatch):
    """Intl, signed in, with AppSync mocked. Returns the request mock."""
    monkeypatch.setattr(intl_fleet, "use_appsync", lambda: True)
    monkeypatch.setattr(turn_queue, "_session_bearer_token", lambda: "id-token")
    monkeypatch.delenv(turn_queue.ENV_TOKEN, raising=False)
    request = mock.Mock(return_value=OK_LIST)
    monkeypatch.setattr(intl_fleet, "appsync_http_request", request)
    return request


def _sent(request):
    """(document, variables, token) of the last AppSync call."""
    args, kwargs = request.call_args
    return args[0], kwargs["variables"], args[2]


class _Task:
    def __init__(self, **kw):
        self.id = kw.get("id", "task_1")
        self.name = "t"
        self.agent_id = kw.get("agent_id", "agent_1")
        self.metadata = {}
        self.residency = "any"
        self.lifetime = "conversation"
        self.requires = []
        self.owner = ""
        self.state = {}


# ---------------------------------------------------------------------------
# 1. Documents and variables
# ---------------------------------------------------------------------------

def test_store_list_sends_the_optional_awsjson_query(appsync):
    intl_fleet.call("store_list", {"include_archived": False})
    document, variables, token = _sent(appsync)
    assert document == "query GetStores($input: AWSJSON) { getStores(input: $input) }"
    assert isinstance(variables["input"], str)
    assert json.loads(variables["input"]) == {"include_archived": False}
    assert token == "id-token"


def test_required_input_uses_a_non_null_type(appsync):
    appsync.return_value = {"data": {"getTransfer": json.dumps({"transfer": {}})}}
    intl_fleet.call("transfer_get", {"transfer_id": "t1"})
    document, _, _ = _sent(appsync)
    assert document == "query GetTransfer($input: AWSJSON!) { getTransfer(input: $input) }"


def test_an_empty_payload_is_still_sent_as_a_json_string(appsync):
    appsync.return_value = {"data": {"getPods": json.dumps({"pods": []})}}
    intl_fleet.call("pod_list", None)
    _, variables, _ = _sent(appsync)
    assert variables["input"] == "{}"


@pytest.mark.parametrize("action,expected", sorted(
    (a, f) for a, (_, f, _) in intl_fleet.AWS_OPS.items()))
def test_every_action_targets_its_field(appsync, action, expected):
    appsync.return_value = {"data": {expected: "{}"}}
    intl_fleet.call(action, {})
    document, _, _ = _sent(appsync)
    assert f"{{ {expected}(input: $input) }}" in document


# ---------------------------------------------------------------------------
# 2. What never leaves the client
# ---------------------------------------------------------------------------

def test_owner_is_stripped(appsync):
    appsync.return_value = {"data": {"enqueueTurn": json.dumps({"turn": {"id": "u1"}, "created": True})}}
    payload = {"task_id": "t1", "input": "", "requires": [], "owner": "x@y.com"}
    intl_fleet.call("turn_enqueue", payload)
    _, variables, _ = _sent(appsync)
    assert "owner" not in json.loads(variables["input"])
    assert payload["owner"] == "x@y.com"  # the caller's dict is not mutated


def test_pod_save_maps_task_id_to_snake_case(appsync):
    appsync.return_value = {"data": {"savePod": json.dumps({"pod": {}})}}
    intl_fleet.call("pod_save", {"name": "p", "taskId": "t1"})
    _, variables, _ = _sent(appsync)
    sent = json.loads(variables["input"])
    assert sent["task_id"] == "t1" and "taskId" not in sent


def test_the_internal_token_is_ignored_on_intl(appsync, monkeypatch):
    monkeypatch.setenv(turn_queue.ENV_TOKEN, "internal-token")
    intl_fleet.call("store_list", {})
    _, _, token = _sent(appsync)
    assert token == "id-token"


def test_no_session_is_refused_without_a_request(appsync, monkeypatch):
    monkeypatch.setattr(turn_queue, "_session_bearer_token", lambda: "")
    status, data = intl_fleet.call("store_list", {})
    assert status == 401 and data["error"] == "unauthorized"
    appsync.assert_not_called()


# ---------------------------------------------------------------------------
# 3-7. Result classification, and how store_api surfaces it
# ---------------------------------------------------------------------------

def test_a_store_list_fills_the_missing_llm_cost(appsync):
    status, data = intl_fleet.call("store_list", {})
    assert status == 200 and data["success"] is True
    assert data["stores"][0]["llm30d"] == {"calls": 0, "tokens": 0, "costFen": 0}


def test_fleet_status_fills_the_queue_ceiling(appsync):
    appsync.return_value = {"data": {"getFleetStatus": json.dumps(
        {"vehicles": [], "queue": {"queued": 0, "running": 0}})}}
    _, data = intl_fleet.call("fleet_status", {})
    assert data["queue"]["maxQueuedSeconds"] == 900


def test_a_refusal_keeps_the_servers_message(appsync):
    appsync.return_value = REFUSED
    status, data = intl_fleet.call("store_assign", {"store_id": "s1", "vehicle_id": "m9"})
    assert status == 404
    assert data == {"success": False, "error": "not_found",
                    "message": "no machine m9 is registered to this account"}
    with pytest.raises(store_api.StoreApiError) as caught:
        store_api.store_assign("s1", "m9")
    assert "no machine m9" in str(caught.value)
    assert not isinstance(caught.value, store_api.StoreApiUnavailable)


def test_a_missing_operation_reads_as_one_sentence(appsync):
    appsync.return_value = UNDEFINED
    status, data = intl_fleet.call("store_list", {})
    assert status == 503 and data["error"] == "not_available_on_edition"
    with pytest.raises(store_api.StoreApiUnavailable) as caught:
        store_api.store_list()
    assert str(caught.value) == "Store placement is not available on this edition yet"


def test_an_unknown_operation_error_type_is_the_same_case(appsync):
    appsync.return_value = {"errors": [{"errorType": "UnknownOperationException", "message": "x"}]}
    status, data = intl_fleet.call("store_list", {})
    assert status == 503 and data["error"] == "not_available_on_edition"


def test_an_expired_session_is_unavailable(appsync):
    appsync.return_value = UNAUTH
    assert intl_fleet.call("store_list", {})[0] == 401
    with pytest.raises(store_api.StoreApiUnavailable):
        store_api.store_list()


def test_a_transport_failure_is_an_error_not_unavailable(appsync):
    appsync.return_value = TRANSPORT
    status, data = intl_fleet.call("store_list", {})
    assert status == 502 and data["error"] == "transport_error"
    with pytest.raises(store_api.StoreApiError) as caught:
        store_api.store_list()
    assert not isinstance(caught.value, store_api.StoreApiUnavailable)


def test_an_insufficient_account_is_403_even_as_a_dict(appsync):
    appsync.return_value = INSUFF
    status, data = intl_fleet.call("store_list", {})
    assert status == 403 and data["error"] == "account_insufficient"


def test_a_null_field_with_no_errors_is_an_empty_response(appsync):
    appsync.return_value = {"data": {"getStores": None}}
    status, data = intl_fleet.call("store_list", {})
    assert status == 502 and data["error"] == "empty_response"


def test_a_doubly_encoded_awsjson_result_is_decoded(appsync):
    appsync.return_value = {"data": {"getStores": json.dumps(OK_LIST["data"]["getStores"])}}
    status, data = intl_fleet.call("store_list", {})
    assert status == 200 and data["stores"][0]["storeId"] == "s1"


def test_a_non_object_result_names_its_type(appsync):
    appsync.return_value = {"data": {"getStores": json.dumps([1, 2])}}
    status, data = intl_fleet.call("store_list", {})
    assert status == 502 and data["error"] == "bad_response" and "(list)" in data["message"]
def test_upper_case_codes_map_to_conflict(appsync):
    appsync.return_value = {"data": {"updateTransfer": json.dumps(
        {"success": False, "error": "INVALID_TRANSITION: done -> running"})}}
    status, data = intl_fleet.call("transfer_update", {"transfer_id": "t1"})
    assert status == 409 and data["message"] == "done -> running"


def test_an_uncoded_refusal_keeps_the_whole_string(appsync):
    appsync.return_value = {"data": {"assignStore": json.dumps(
        {"success": False, "error": "Something went wrong: try later"})}}
    status, data = intl_fleet.call("store_assign", {"store_id": "s1"})
    assert status == 400 and data["message"] == "Something went wrong: try later"


def test_claim_and_archive_round_trip_through_store_api(appsync):
    appsync.return_value = CLAIM_WON
    assert store_api.store_claim("s1", "m1")["won"] is True
    appsync.return_value = ARCHIVED
    assert store_api.store_archive("s1")["store"]["status"] == "archived"


# ---------------------------------------------------------------------------
# 8. Worker-only actions
# ---------------------------------------------------------------------------

def test_worker_only_actions_are_refused_locally(appsync):
    status, data = intl_fleet.call("turn_claim", {})
    assert status == 403 and data["error"] == "worker_only"
    appsync.assert_not_called()


def test_an_unknown_action_raises(appsync):
    with pytest.raises(ValueError):
        intl_fleet.call("no_such_action", {})


# ---------------------------------------------------------------------------
# 9. turn_queue on intl
# ---------------------------------------------------------------------------

def test_enqueue_on_intl_uses_the_session_and_no_owner(appsync, monkeypatch):
    monkeypatch.setenv(turn_queue.ENV_TOKEN, "internal-token")
    appsync.return_value = {"data": {"enqueueTurn": json.dumps(
        {"turn": {"id": "turn_9"}, "created": True})}}
    result = turn_queue.enqueue_task_turn(_Task(), owner="x@y.com")
    assert result["turn_id"] == "turn_9" and result["created"] is True
    _, variables, token = _sent(appsync)
    assert token == "id-token"
    sent = json.loads(variables["input"])
    assert "owner" not in sent and sent["task_id"] == "task_1"


def test_enqueue_refusal_raises_turn_queue_error(appsync):
    appsync.return_value = {"data": {"enqueueTurn": json.dumps(
        {"success": False, "error": "unknown_agent: agent_1"})}}
    with pytest.raises(turn_queue.TurnQueueError) as caught:
        turn_queue.enqueue_task_turn(_Task())
    assert not isinstance(caught.value, turn_queue.TurnQueueNotConfigured)
    assert "agent_1" in str(caught.value)


def test_enqueue_expired_session_is_not_configured(appsync):
    appsync.return_value = UNAUTH
    with pytest.raises(turn_queue.TurnQueueNotConfigured):
        turn_queue.enqueue_task_turn(_Task())


# ---------------------------------------------------------------------------
# 10. vehicle_handler
# ---------------------------------------------------------------------------

def _vehicle_handler():
    try:
        from gui.ipc.w2p_handlers import vehicle_handler
    except Exception as exc:                        # pragma: no cover
        pytest.skip(f"IPC handler stack unavailable: {exc}")
    return vehicle_handler


def test_pod_list_on_intl_calls_get_pods(appsync):
    vh = _vehicle_handler()
    appsync.return_value = {"data": {"getPods": json.dumps(
        {"pods": [], "unmanagedVehicles": [], "limits": {"podCeiling": 5}})}}
    status, data = vh._call_account_manager("pod_list", {})
    document, _, _ = _sent(appsync)
    assert "getPods(input: $input)" in document
    assert status == 200 and data["limits"]["podCeiling"] == 5


def test_account_manager_ipc_strips_success_and_maps_unavailable(appsync):
    vh = _vehicle_handler()
    request = mock.Mock()
    with mock.patch.object(vh, "create_success_response", side_effect=lambda r, d: ("ok", d)), \
         mock.patch.object(vh, "create_error_response", side_effect=lambda r, c, m: ("err", c, m)):
        appsync.return_value = {"data": {"getPods": json.dumps({"pods": []})}}
        kind, body = vh.handle_account_manager_call(request, {"action": "pod_list", "input": {}})
        assert kind == "ok" and body == {"pods": []}

        appsync.return_value = {"errors": [{"message": "Validation error of type FieldUndefined: getPods"}]}
        result = vh.handle_account_manager_call(request, {"action": "pod_list", "input": {}})
        assert result == ("err", "NOT_AVAILABLE", intl_fleet.NOT_AVAILABLE_MSG)


def test_fleet_status_ipc_on_intl(appsync):
    vh = _vehicle_handler()
    appsync.return_value = {"data": {"getFleetStatus": json.dumps(
        {"vehicles": [{"id": "v1", "live": True}], "liveVehicles": 1, "hasLivePod": True,
         "queue": {"queued": 0}, "limits": {"podCeiling": 5}, "staleAfterSeconds": 180})}}
    with mock.patch.object(vh, "create_success_response", side_effect=lambda r, d: d):
        body = vh.handle_get_fleet_status(mock.Mock(), {"include_all": True})
    assert body["liveVehicles"] == 1 and body["queue"]["maxQueuedSeconds"] == 900
    _, variables, _ = _sent(appsync)
    assert json.loads(variables["input"]) == {"include_all": True}


# ---------------------------------------------------------------------------
# 11. Usage events
# ---------------------------------------------------------------------------

def _usage_row(key, **overrides):
    row = {"id": f"ue_{key}", "idempotency_key": key, "scenario_code": "cs_chat",
           "meter_code": "message_replied", "quantity": "2", "owner": "acct-1",
           "store_id": "S1", "agent_id": None, "task_id": None, "skill_id": None,
           "vehicle_id": None, "occurred_at": "2026-10-24T08:00:00.123456",
           "evidence": '{"customer": "c1"}', "cost_basis": None, "source": "client"}
    row.update(overrides)
    return row


def test_usage_events_are_converted_for_appsync(appsync):
    appsync.return_value = USAGE_OK
    wire = reporter._to_wire_event(_usage_row("k1"))
    wire["account_id"] = "acct-1"
    intl_fleet.report_usage_events([wire])
    document, variables, _ = _sent(appsync)
    assert document == intl_fleet.USAGE_DOCUMENT
    assert isinstance(variables["input"], dict)
    event = variables["input"]["events"][0]
    assert event["occurred_at"] == "2026-10-24T08:00:00.123Z"
    assert event["evidence"] == json.dumps({"customer": "c1"})
    assert event["cost_basis"] is None
    assert event["quantity"] == 2
    assert "account_id" not in event


def test_an_aware_timestamp_is_converted_to_utc():
    assert intl_fleet._aws_datetime("2026-10-24T01:00:00-07:00") == "2026-10-24T08:00:00.000Z"


def test_report_pending_on_intl_leaves_rejected_keys_pending(appsync):
    appsync.return_value = USAGE_OK
    svc = mock.Mock()
    svc.get_unreported_events.return_value = [_usage_row("k1"), _usage_row("k2"), _usage_row("k3")]
    svc.mark_reported.side_effect = lambda ids: len(ids)
    with mock.patch.object(reporter, "_service", return_value=svc), \
         mock.patch.object(reporter, "_post") as cn_post:
        result = reporter.report_pending()
    svc.mark_reported.assert_called_once_with(["ue_k1", "ue_k2"])
    assert result["left_pending"] == 1 and result["rejected"] == 1
    cn_post.assert_not_called()


def test_report_pending_on_intl_signed_out_keeps_the_batch(appsync, monkeypatch):
    monkeypatch.setattr(turn_queue, "_session_bearer_token", lambda: "")
    svc = mock.Mock()
    svc.get_unreported_events.return_value = [_usage_row("k1")]
    with mock.patch.object(reporter, "_service", return_value=svc):
        result = reporter.report_pending()
    assert result["left_pending"] == 1
    svc.mark_reported.assert_not_called()
    appsync.assert_not_called()


# ---------------------------------------------------------------------------
# 12. CN unchanged
# ---------------------------------------------------------------------------

@pytest.fixture
def cn(monkeypatch):
    monkeypatch.setenv("ECAN_APP_ID", "cn")
    request = mock.Mock(side_effect=AssertionError("AppSync must not be called on CN"))
    monkeypatch.setattr(intl_fleet, "appsync_http_request", request)
    monkeypatch.setattr(turn_queue, "_session_bearer_token", lambda: "cn-session")
    monkeypatch.delenv(turn_queue.ENV_TOKEN, raising=False)
    monkeypatch.delenv(turn_queue.ENV_ENDPOINT, raising=False)
    monkeypatch.setattr(turn_queue, "_account_manager_url", lambda: "https://gw.example/ecbAccountManager")
    return request


def test_cn_store_api_still_posts_the_action(cn):
    response = mock.Mock(status_code=200, text=json.dumps({"success": True, "stores": []}))
    with mock.patch.object(store_api.requests, "post", return_value=response) as post:
        store_api.store_list()
    args, kwargs = post.call_args
    assert args[0] == "https://gw.example/ecbAccountManager"
    assert kwargs["json"]["action"] == "store_list"
    assert kwargs["headers"]["Authorization"] == "Bearer cn-session"


def test_cn_enqueue_still_posts_the_action(cn):
    import requests
    response = mock.Mock(status_code=200, text=json.dumps({"success": True, "turn": {"id": "u1"}}))
    with mock.patch.object(requests, "post", return_value=response) as post:
        turn_queue.enqueue_task_turn(_Task())
    _, kwargs = post.call_args
    assert kwargs["json"]["action"] == "turn_enqueue"
    assert kwargs["headers"]["Authorization"] == "Bearer cn-session"


def test_cn_account_manager_still_posts_the_action(cn):
    vh = _vehicle_handler()
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = b'{"success": true, "pods": []}'
    response.__enter__.return_value.status = 200
    with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
        status, data = vh._call_account_manager("pod_list", {})
    req = urlopen.call_args[0][0]
    assert req.full_url == "https://gw.example/ecbAccountManager"
    assert json.loads(req.data)["action"] == "pod_list"
    assert status == 200 and data["pods"] == []


def test_cn_metering_still_posts_the_action(cn):
    svc = mock.Mock()
    svc.get_unreported_events.return_value = [_usage_row("k1")]
    svc.mark_reported.side_effect = lambda ids: len(ids)
    with mock.patch.object(reporter, "_service", return_value=svc), \
         mock.patch.object(reporter, "_account_manager_url", return_value="https://gw.example/ecbAccountManager"), \
         mock.patch.object(reporter, "_bearer_token", return_value="cn-session"), \
         mock.patch.object(reporter, "_post", return_value={"_http_status": 200, "success": True,
                                                            "accepted": 1, "duplicates": 0,
                                                            "rejected": []}) as post:
        reporter.report_pending()
    url, token, body = post.call_args[0]
    assert url == "https://gw.example/ecbAccountManager" and token == "cn-session"
    assert body["action"] == "report_usage_event" and len(body["events"]) == 1
