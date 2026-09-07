"""billing.validateCoupon IPC handler: forwards validate_coupon to
ecbAccountManager (amount in FEN), advisory preview for the top-up coupon input."""

import json
from unittest.mock import patch, MagicMock

import gui.ipc.w2p_handlers.payment_handler as ph


def _req():
    return {"id": "req-1", "method": "billing.validateCoupon"}


class _FakeResp:
    def __init__(self, body, status=200):
        self._b = body.encode("utf-8"); self.status = status
    def read(self, n=-1): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_validate_coupon_posts_fen_and_maps_response(monkeypatch):
    monkeypatch.setattr(ph, "is_cn", lambda: True)
    import gui.ipc.w2p_handlers.account_verify_handler as av
    monkeypatch.setattr(av, "_account_manager_url", lambda: "https://x.example/ecbAccountManager")
    monkeypatch.setattr(ph, "_coupon_bearer_token", lambda: "TOK")

    captured = {}
    def fake_urlopen(req, timeout=20):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["auth"] = req.headers.get("Authorization")
        return _FakeResp(json.dumps({
            "success": True, "valid": True, "pay_amount": 6800,
            "credit_amount": 7300, "currency": "CNY"}))
    monkeypatch.setattr(ph.urllib.request, "urlopen", fake_urlopen)

    resp = ph.handle_validate_coupon(_req(), {"code": "SPRING20", "amount": 6800, "purpose": "topup"})
    # forwarded correctly
    assert captured["body"] == {"action": "validate_coupon", "code": "SPRING20", "amount": 6800, "purpose": "topup"}
    assert captured["auth"] == "Bearer TOK"
    # mapped to IPC success with the raw payload as data
    assert resp["status"] == "success"
    assert resp["result"]["valid"] is True
    assert resp["result"]["pay_amount"] == 6800
    assert resp["result"]["credit_amount"] == 7300


def test_validate_coupon_requires_code(monkeypatch):
    monkeypatch.setattr(ph, "is_cn", lambda: True)
    resp = ph.handle_validate_coupon(_req(), {"amount": 6800})
    assert resp["status"] == "error"


def test_validate_coupon_cn_only(monkeypatch):
    monkeypatch.setattr(ph, "is_cn", lambda: False)
    resp = ph.handle_validate_coupon(_req(), {"code": "X", "amount": 100})
    assert resp["status"] == "error"
