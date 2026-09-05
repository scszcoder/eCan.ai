"""MCP tools for outbound messaging — send_sms and send_email.

Both tools call the agentScheduler Lambda's GraphQL mutations
(`sendSms`, `sendEmail`) over AppSync. The Lambda then dispatches via
AWS End User Messaging SMS / SES respectively.

Tool wiring:
  - Schemas added by `add_send_sms_tool_schema` and `add_send_email_tool_schema`
    in tool_schemas.py.
  - Handlers `send_sms` and `send_email` registered in server.py
    `tool_function_mapping`.
"""

import mcp.types as types
from mcp.types import TextContent

from utils.logger_helper import logger_helper as logger, get_traceback
from agent.cloud_api.cloud_api import (
    send_sms_to_cloud,
    send_email_to_cloud,
)


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

def add_send_sms_tool_schema(tool_schemas):
    tool_schema = types.Tool(
        _meta={"run_in_cloud": True},
        name="send_sms",
        description=(
            "<category>Messaging</category><sub-category>SMS</sub-category>"
            "Send an SMS to a phone number on the merchant's behalf through the eCan platform. "
            "Use for short notifications, alerts, or 2FA-style confirmations. "
            "Returns {success, messageId, error}."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["phone_number", "message"],
                    "properties": {
                        "phone_number": {
                            "type": "string",
                            "description": (
                                "Recipient phone number in E.164 format, "
                                "e.g. '+14155550100' (must include country code)."
                            ),
                        },
                        "message": {
                            "type": "string",
                            "description": (
                                "SMS body. Plain ASCII keeps cost low and "
                                "delivery reliable. Carriers may segment >160 chars."
                            ),
                        },
                    },
                }
            },
        },
    )
    tool_schemas.append(tool_schema)


def add_send_email_tool_schema(tool_schemas):
    tool_schema = types.Tool(
        _meta={"run_in_cloud": True},
        name="send_email",
        description=(
            "<category>Messaging</category><sub-category>Email</sub-category>"
            "Send an email on the merchant's behalf through the eCan platform; use reply_to "
            "for the merchant's own address. Supports plain-text and/or HTML body. "
            "Returns {success, messageId, error}."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["to", "subject"],
                    "properties": {
                        "to": {
                            "type": "string",
                            "description": "Recipient email address.",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Email subject line.",
                        },
                        "body_text": {
                            "type": "string",
                            "description": (
                                "Plain-text body. At least one of body_text or "
                                "body_html must be provided."
                            ),
                        },
                        "body_html": {
                            "type": "string",
                            "description": (
                                "HTML body (optional). At least one of body_text "
                                "or body_html must be provided."
                            ),
                        },
                        "reply_to": {
                            "type": "string",
                            "description": "Optional reply-to address.",
                        },
                    },
                }
            },
        },
    )
    tool_schemas.append(tool_schema)


# ---------------------------------------------------------------------------
# Tool handlers (registered in server.py tool_function_mapping)
# ---------------------------------------------------------------------------

def _get_session_and_token(mainwin):
    """Resolve the auth session, token, and AppSync endpoint from MainGUI."""
    session = getattr(mainwin, "session", None)
    token = mainwin.get_auth_token() if hasattr(mainwin, "get_auth_token") else None
    network_api_engine = (
        mainwin.getNetworkApiEngine()
        if hasattr(mainwin, "getNetworkApiEngine")
        else "wan"
    )
    if network_api_engine == "lan" and hasattr(mainwin, "getLanApiEndpoint"):
        endpoint = mainwin.getLanApiEndpoint()
    elif hasattr(mainwin, "getWanApiEndpoint"):
        endpoint = mainwin.getWanApiEndpoint()
    else:
        endpoint = None
    return session, token, endpoint


async def send_sms(mainwin, args):
    """MCP handler: send_sms.

    Args shape:
      { "input": { "phone_number": "+1...", "message": "..." } }
    """
    try:
        cfg = (args or {}).get("input") or {}
        phone = (cfg.get("phone_number") or cfg.get("phoneNumber") or "").strip()
        message = (cfg.get("message") or "").strip()
        if not phone:
            return [TextContent(type="text", text="Error: phone_number is required")]
        if not message:
            return [TextContent(type="text", text="Error: message is required")]

        session, token, endpoint = _get_session_and_token(mainwin)
        result = send_sms_to_cloud(
            session,
            token,
            {"phoneNumber": phone, "message": message},
            endpoint,
        )
        if result and result.get("success"):
            msg = (
                f"📱 SMS queued — to={phone}, "
                f"messageId={result.get('messageId') or '(none)'}"
            )
            logger.info(f"[send_sms] {msg}")
            return [TextContent(type="text", text=msg)]

        err = (result or {}).get("error") or "Unknown error"
        logger.error(f"[send_sms] Failed: {err}")
        return [TextContent(type="text", text=f"❌ SMS send failed: {err}")]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSendSms")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def send_email(mainwin, args):
    """MCP handler: send_email.

    Args shape:
      { "input": { "to": "...", "subject": "...",
                   "body_text"?: "...", "body_html"?: "...",
                   "reply_to"?: "..." } }
    """
    try:
        cfg = (args or {}).get("input") or {}
        to_addr = (cfg.get("to") or "").strip()
        subject = (cfg.get("subject") or "").strip()
        body_text = cfg.get("body_text") or cfg.get("bodyText")
        body_html = cfg.get("body_html") or cfg.get("bodyHtml")
        reply_to = cfg.get("reply_to") or cfg.get("replyTo")

        if not to_addr:
            return [TextContent(type="text", text="Error: 'to' is required")]
        if not subject:
            return [TextContent(type="text", text="Error: 'subject' is required")]
        if not body_text and not body_html:
            return [TextContent(
                type="text",
                text="Error: at least one of 'body_text' or 'body_html' is required",
            )]

        session, token, endpoint = _get_session_and_token(mainwin)
        payload = {"to": to_addr, "subject": subject}
        if body_text:
            payload["bodyText"] = body_text
        if body_html:
            payload["bodyHtml"] = body_html
        if reply_to:
            payload["replyTo"] = reply_to

        result = send_email_to_cloud(session, token, payload, endpoint)
        if result and result.get("success"):
            msg = (
                f"✉️ Email queued — to={to_addr}, subject={subject!r}, "
                f"messageId={result.get('messageId') or '(none)'}"
            )
            logger.info(f"[send_email] {msg}")
            return [TextContent(type="text", text=msg)]

        err = (result or {}).get("error") or "Unknown error"
        logger.error(f"[send_email] Failed: {err}")
        return [TextContent(type="text", text=f"❌ Email send failed: {err}")]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSendEmail")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]
