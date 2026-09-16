"""cc/bcc has to survive the whole trip: tool call -> handler -> GraphQL variables.

The failure this guards against is silent — a dropped `bcc` sends the mail to one
person and reports success, and nobody notices until the other recipients ask why
they never heard anything.
"""

import asyncio

import agent.mcp.server.messaging.messaging_tools as mt
from agent.cloud_api import cloud_api


class _FakeMainWin:
    def get_auth_token(self):
        return "token"

    def getNetworkApiEngine(self):
        return "wan"

    def getWanApiEndpoint(self):
        return "https://example.invalid/graphql"


def test_address_list_takes_a_list_or_a_separated_string():
    assert mt._address_list(["A@x.com", " b@y.com "]) == ["A@x.com", "b@y.com"]
    assert mt._address_list("a@x.com, b@y.com; c@z.com") == ["a@x.com", "b@y.com", "c@z.com"]
    assert mt._address_list(None) == []
    assert mt._address_list("") == []
    assert mt._address_list(" , ") == []


def test_send_email_forwards_cc_and_bcc(monkeypatch):
    sent = {}

    def fake_send(session, token, payload, endpoint):
        sent.update(payload)
        return {"success": True, "messageId": "mid-1"}

    monkeypatch.setattr(mt, "send_email_to_cloud", fake_send)
    result = asyncio.run(mt.send_email(_FakeMainWin(), {"input": {
        "to": "cust@example.com",
        "subject": "Order shipped",
        "body_text": "It is on its way.",
        "cc": "boss@example.com",
        "bcc": ["audit@example.com", "ops@example.com"],
    }}))

    assert sent["cc"] == ["boss@example.com"]
    assert sent["bcc"] == ["audit@example.com", "ops@example.com"]
    assert "cc=1" in result[0].text and "bcc=2" in result[0].text


def test_send_email_omits_cc_and_bcc_when_unused(monkeypatch):
    """An ordinary single-recipient send must look exactly as it did before.

    A backend whose SendEmailInput predates cc/bcc rejects the whole mutation if
    the client sends fields it does not declare, so absent means absent.
    """
    sent = {}

    def fake_send(session, token, payload, endpoint):
        sent.update(payload)
        return {"success": True, "messageId": "mid-2"}

    monkeypatch.setattr(mt, "send_email_to_cloud", fake_send)
    asyncio.run(mt.send_email(_FakeMainWin(), {"input": {
        "to": "cust@example.com", "subject": "Hi", "body_text": "Hello",
    }}))

    assert "cc" not in sent and "bcc" not in sent


def test_send_email_to_cloud_puts_cc_bcc_in_the_variables(monkeypatch):
    captured = {}

    def fake_request(query, session, token, endpoint, variables=None):
        captured["variables"] = variables
        return {"data": {"sendEmail": {"success": True, "messageId": "mid-3"}}}

    monkeypatch.setattr(cloud_api, "appsync_http_request", fake_request)
    cloud_api.send_email_to_cloud(None, "token", {
        "to": "cust@example.com",
        "subject": "Hi",
        "bodyText": "Hello",
        "cc": ["boss@example.com"],
        "bcc": [],
    }, "https://example.invalid/graphql")

    payload = captured["variables"]["input"]
    assert payload["cc"] == ["boss@example.com"]
    assert "bcc" not in payload, "an empty list must not be sent as a field"
