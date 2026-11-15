"""The chat panel asks the cloud for a session's running turn when its progress events
stop (getSkillEditorChatStatus). A backend without that query yet answers "no status"."""
from unittest.mock import patch

from gui.ipc.w2p_handlers import skill_editor_cloud_relay as relay

CTX = {"owner": "me", "token": "t", "session": None, "endpoint": "x"}


def test_status_is_parsed_from_awsjson():
    resp = {"data": {"getSkillEditorChatStatus": '{"turnId": "t1", "state": "running", "currentStep": "plan"}'}}
    with patch.object(relay, "_get_cloud_context", return_value=CTX), \
            patch.object(relay, "_appsync_request", return_value=resp) as req:
        assert relay.relay_get_status("s1") == {"turnId": "t1", "state": "running", "currentStep": "plan"}
    assert req.call_args.kwargs["variables"] == {"sessionId": "s1"}


def test_no_turn_or_no_such_query_means_no_status():
    with patch.object(relay, "_get_cloud_context", return_value=CTX):
        with patch.object(relay, "_appsync_request", return_value={"data": {"getSkillEditorChatStatus": None}}):
            assert relay.relay_get_status("s1") is None
        with patch.object(relay, "_appsync_request",
                          return_value={"errors": [{"message": "Cannot query field getSkillEditorChatStatus"}]}):
            assert relay.relay_get_status("s1") is None
    with patch.object(relay, "_get_cloud_context", return_value=None):
        assert relay.relay_get_status("s1") is None
