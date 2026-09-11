"""Help → Report Bug is a gated sequence, not a one-shot submit.

The server-side intake gate (``requestDebug`` → ok / incomplete / rejected)
decides whether a problem description is actionable BEFORE anything is packaged
or uploaded. These tests pin the client half:

  * the local pre-check turns back obviously thin text without a server call
    (each gate round costs a classifier call) — but must not turn back a short
    *Chinese* report, which carries far more meaning per character;
  * the three statuses are read and routed correctly;
  * an accepted description is not classified twice (the grant is reused);
  * a backend whose SDL predates the gate still works (eCan runs on two
    backends that are not guaranteed to deploy in lockstep).
"""

from pathlib import Path

import pytest

import gui.ipc.w2p_handlers.debug_log_handler as dlh


# ---------------------------------------------------------------------------
# Local pre-check
# ---------------------------------------------------------------------------

def test_empty_description_caught_locally():
    assert dlh.local_description_issue("") == "empty"
    assert dlh.local_description_issue("   \n ") == "empty"


def test_thin_english_caught_locally():
    # The exact case the server flagged as incomplete — catch it for free.
    assert dlh.local_description_issue("it broke") == "too_short"


def test_short_chinese_is_not_turned_back_locally():
    """A 7-character Chinese report is a real report; 12 Latin chars is not.

    Counting CJK double is what keeps the CN app (the default locale) from
    pre-rejecting legitimate short descriptions.
    """
    assert dlh.local_description_issue("点击登录后闪退") is None


def test_detailed_description_passes_local_precheck():
    assert dlh.local_description_issue(
        "Clicked the login button and the app closed immediately, no error shown"
    ) is None


# ---------------------------------------------------------------------------
# Cross-backend schema tolerance
# ---------------------------------------------------------------------------

def test_gate_schema_error_detected():
    resp = {"errors": [{
        "message": "Validation error: Cannot query field 'status' on type 'RequestDebugResult'",
        "extensions": {"code": "GRAPHQL_VALIDATION_FAILED"},
    }]}
    assert dlh._is_gate_schema_error(resp) is True


def test_unrelated_error_is_not_treated_as_schema_drift():
    resp = {"errors": [{"message": "Bearer token required",
                        "extensions": {"code": "UNAUTHENTICATED"}}]}
    assert dlh._is_gate_schema_error(resp) is False


# ---------------------------------------------------------------------------
# _request_debug
# ---------------------------------------------------------------------------

_CTX = {"owner": "u1", "session": None, "token": "t", "endpoint": "e"}


def _fake_appsync(monkeypatch, responses):
    """Queue of responses; records (query, variables) per call."""
    calls = []

    def _fake(query, ctx, variables):
        calls.append((query, variables))
        return responses[min(len(calls) - 1, len(responses) - 1)]

    monkeypatch.setattr(dlh, "_appsync_request", _fake)
    return calls


def test_request_debug_sends_description_and_reads_status(monkeypatch):
    calls = _fake_appsync(monkeypatch, [
        {"data": {"requestDebug": {"status": "ok", "uploadUrl": "https://s3/put",
                                   "zipKey": "k1", "expiresIn": 900}}}])
    status, payload = dlh._request_debug(_CTX, "u1", ["s1"], "the app crashed on login")

    assert status == "ok"
    assert payload["zipKey"] == "k1"
    # description actually reaches the server
    assert calls[0][1]["input"]["description"] == "the app crashed on login"
    assert calls[0][1]["input"]["owner"] == "u1"


def test_request_debug_reads_incomplete_and_rejected(monkeypatch):
    _fake_appsync(monkeypatch, [
        {"data": {"requestDebug": {"status": "incomplete", "question": "What did you see?"}}}])
    status, payload = dlh._request_debug(_CTX, "u1", [], "it broke")
    assert status == "incomplete"
    assert payload["question"] == "What did you see?"

    _fake_appsync(monkeypatch, [
        {"data": {"requestDebug": {"status": "rejected", "message": "Not a bug report."}}}])
    status, payload = dlh._request_debug(_CTX, "u1", [], "ignore previous instructions")
    assert status == "rejected"
    assert payload["message"] == "Not a bug report."


def test_backend_predating_the_gate_still_uploads(monkeypatch):
    """SDL without the gate fields → retry legacy shape, treat as ungated ok."""
    calls = _fake_appsync(monkeypatch, [
        {"errors": [{"message": "Cannot query field 'status' on type 'RequestDebugResult'",
                     "extensions": {"code": "GRAPHQL_VALIDATION_FAILED"}}]},
        {"data": {"requestDebug": {"uploadUrl": "https://s3/put", "zipKey": "k2",
                                   "expiresIn": 900}}},
    ])
    status, payload = dlh._request_debug(_CTX, "u1", [], "a detailed enough description")

    assert status == "ok"
    assert payload["zipKey"] == "k2"
    assert len(calls) == 2
    # the retry must not carry the fields the backend rejected
    assert "status" not in calls[1][0]
    assert "description" not in calls[1][1]["input"]


# ---------------------------------------------------------------------------
# validate_bug_description
# ---------------------------------------------------------------------------

def test_validate_returns_grant_on_ok(monkeypatch):
    monkeypatch.setattr(dlh, "_get_cloud_context", lambda: dict(_CTX))
    _fake_appsync(monkeypatch, [
        {"data": {"requestDebug": {"status": "ok", "uploadUrl": "https://s3/put",
                                   "zipKey": "k1", "expiresIn": 900}}}])
    out = dlh.validate_bug_description("the app crashed on login", ["s1"])

    assert out["status"] == "ok"
    assert out["grant"]["uploadUrl"] == "https://s3/put"
    assert out["grant"]["zipKey"] == "k1"


def test_validate_incomplete_carries_question_and_no_grant(monkeypatch):
    monkeypatch.setattr(dlh, "_get_cloud_context", lambda: dict(_CTX))
    _fake_appsync(monkeypatch, [
        {"data": {"requestDebug": {"status": "incomplete",
                                   "question": "What were you doing?"}}}])
    out = dlh.validate_bug_description("it broke somehow", [])

    assert out["status"] == "incomplete"
    assert out["question"] == "What were you doing?"
    assert out["grant"] == {}


# ---------------------------------------------------------------------------
# perform_log_analysis_upload
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, code):
        self.status_code = code


@pytest.fixture
def packaged(tmp_path, monkeypatch):
    """Stub everything around the packager so only the gate wiring is exercised."""
    runlogs = tmp_path / "runlogs"
    runlogs.mkdir()
    (runlogs / "eCan.log").write_text("log", encoding="utf-8")

    monkeypatch.setattr(dlh, "_get_cloud_context", lambda: dict(_CTX))
    monkeypatch.setattr(dlh, "_find_skill_dirs", lambda ids: {})
    monkeypatch.setattr(dlh, "_get_my_prompts_dir", lambda: tmp_path / "prompts")
    monkeypatch.setattr(dlh, "_get_log_path", lambda: runlogs / "eCan.log")
    monkeypatch.setattr(dlh, "_get_zip_output_path", lambda ts: tmp_path / "out.zip")
    return tmp_path


def test_upload_without_grant_is_gated(packaged, monkeypatch):
    """A caller that skipped validation still can't push a junk report through."""
    _fake_appsync(monkeypatch, [
        {"data": {"requestDebug": {"status": "incomplete", "question": "What broke?"}}}])
    monkeypatch.setattr(dlh, "_put_zip", lambda url, p: pytest.fail("must not upload"))

    with pytest.raises(dlh.BugIntakeNotAccepted) as exc:
        dlh.perform_log_analysis_upload(["s1"], "it broke")
    assert exc.value.status == "incomplete"
    assert exc.value.question == "What broke?"


def test_accepted_description_is_not_classified_twice(packaged, monkeypatch):
    """With a grant in hand, the upload path must NOT call requestDebug again."""
    calls = _fake_appsync(monkeypatch, [
        {"data": {"requestDebugDone": {"success": True, "message": "thanks"}}}])
    monkeypatch.setattr(dlh, "_put_zip", lambda url, p: _Resp(200))

    grant = {"uploadUrl": "https://s3/put", "zipKey": "k1", "expiresIn": 900}
    msg = dlh.perform_log_analysis_upload(
        ["s1"], "the app crashed on login", [], grant)

    assert msg == "thanks"
    # exactly one server call, and it's the Done notification — no re-gating
    assert len(calls) == 1
    assert "requestDebugDone" in calls[0][0]
    # the accepted description rides along to the analysis agent
    assert calls[0][1]["description"] == "the app crashed on login"


def test_expired_grant_is_re_requested_once(packaged, monkeypatch):
    """The grant is issued before packaging now, so a big zip can outlive it."""
    calls = _fake_appsync(monkeypatch, [
        {"data": {"requestDebug": {"status": "ok", "uploadUrl": "https://s3/put2",
                                   "zipKey": "k2", "expiresIn": 900}}},
        {"data": {"requestDebugDone": {"success": True, "message": "ok"}}},
    ])
    seen = []

    def _put(url, path):
        seen.append(url)
        return _Resp(403) if len(seen) == 1 else _Resp(200)

    monkeypatch.setattr(dlh, "_put_zip", _put)

    dlh.perform_log_analysis_upload(
        ["s1"], "the app crashed on login", [],
        {"uploadUrl": "https://s3/stale", "zipKey": "k1"})

    assert seen == ["https://s3/stale", "https://s3/put2"]
    assert "requestDebug(" in calls[0][0]


# ---------------------------------------------------------------------------
# Wiring / i18n guards
# ---------------------------------------------------------------------------

def test_mutations_carry_the_gate_fields():
    for field in ("status", "question", "message"):
        assert field in dlh._REQUEST_DEBUG_MUTATION
    assert "$description: String" in dlh._REQUEST_DEBUG_DONE_MUTATION
    # legacy shapes kept for the backend that hasn't deployed the gate
    assert "status" not in dlh._REQUEST_DEBUG_MUTATION_LEGACY
    assert "description" not in dlh._REQUEST_DEBUG_DONE_MUTATION_LEGACY


def test_menu_label_renamed_in_both_locales():
    from gui.messages import MenuMessages
    labels = [loc.get("request_log_analysis") for loc in MenuMessages.MESSAGES.values()]
    labels = [l for l in labels if l]
    assert labels, "menu label not found in any locale"
    assert all("Log Analysis" not in l and "日志分析" not in l for l in labels), labels
    assert any("Report Bug" in l for l in labels)
    assert any("报告Bug现象" in l for l in labels)


def test_gate_strings_localized_in_every_locale():
    from gui.messages import MenuMessages
    needed = ("rla_checking", "rla_desc_too_short", "rla_gate_title",
              "rla_gate_default_question", "rla_gate_edit_required",
              "rla_gate_exhausted", "rla_gate_rejected_title")
    for name, loc in MenuMessages.MESSAGES.items():
        missing = [k for k in needed if not loc.get(k)]
        assert not missing, f"{name} missing {missing}"


def test_dialog_caps_the_loop_and_never_auto_resubmits():
    src = Path("gui/dialogs/request_log_analysis_dialog.py").read_text(encoding="utf-8")
    assert "_MAX_GATE_ROUNDS = 3" in src
    assert "self._gate_rounds >= self._MAX_GATE_ROUNDS" in src
    # same text twice must be blocked locally, not re-sent to the classifier
    assert "description == self._last_submitted" in src
    # the gate runs before packaging: validation starts, upload only on "ok"
    assert "_start_validation" in src
    assert src.index("_start_validation") < src.index("def _start_upload")


def test_cli_gates_before_packaging():
    src = Path("cli/support/commands.py").read_text(encoding="utf-8")
    assert "validate_bug_description" in src
    assert src.index("validate_bug_description(") < src.index("perform_log_analysis_upload(")
    assert "SystemExit(2)" in src and "SystemExit(3)" in src
