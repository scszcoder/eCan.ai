"""MCP tools for the 售后 agent's case note (agent/ec_agents/aftersales_router.py).

The platform's 售后单 stays the status source of truth; the note keeps what it
does not hold: evidence seen in chat, promises, approvals waiting for the
merchant, external ids, and which agent owns the buyer's case."""
import json
import time

from mcp.types import TextContent

from agent.ec_agents import aftersales_router as asr


def _out(data) -> list:
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, default=str))]


def _input(args) -> dict:
    inp = args.get("input", args) if isinstance(args, dict) else {}
    return inp if isinstance(inp, dict) else {}


def _when(t) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(t or 0)))


def _readable(case: dict) -> dict:
    return {"customer_id": case.get("customer"), "owner_agent_id": case.get("agent"),
            "opened": _when(case.get("opened")), "last_activity": _when(case.get("last")),
            "first_message": case.get("reason", ""), "order_id": case.get("order_id", ""),
            "notes": [dict(n, t=_when(n.get("t"))) for n in case.get("notes", [])]}


async def aftersales_case_get(mainwin, args):
    customer = str(_input(args).get("customer_id") or "").strip()
    case = asr.get_case(customer) if customer else None
    return _out({"found": bool(case), **({"case": _readable(case)} if case else {})})


async def aftersales_case_note(mainwin, args):
    inp = _input(args)
    try:
        note = asr.add_note(str(inp.get("customer_id") or "").strip(), str(inp.get("kind") or "note"),
                            str(inp.get("text") or ""), str(inp.get("order_id") or ""),
                            str(inp.get("ref") or ""))
        return _out({"ok": True, "note": dict(note, t=_when(note["t"]))})
    except (KeyError, ValueError) as exc:
        return _out({"ok": False, "error": str(exc)})


async def aftersales_case_close(mainwin, args):
    inp = _input(args)
    closed = asr.close_customer_case(str(inp.get("customer_id") or "").strip(),
                                     str(inp.get("resolution") or ""))
    return _out({"ok": closed, **({} if closed else {"error": "no open case for this customer"})})


def add_aftersales_case_tool_schemas(tool_schemas):
    import mcp.types as types
    cat = "<category>AfterSales</category><sub-category>Case</sub-category>"
    cust = {"type": "string", "description": "The buyer's customer_id (as in the turn's input)"}

    def tool(name, description, required, properties):
        tool_schemas.append(types.Tool(
            _meta={"run_in_cloud": False}, name=name, description=cat + description,
            inputSchema={"type": "object", "required": ["input"], "properties": {"input": {
                "type": "object", "required": required, "properties": properties}}}))

    tool("aftersales_case_get",
         "Read the buyer's open after-sales case: owner, when opened, the first message, "
         "order_id and every note (evidence, promises, approvals pending, external ids).",
         ["customer_id"], {"customer_id": cust})
    tool("aftersales_case_note",
         "Add a note to the buyer's open after-sales case. kind: evidence (what the photo/video "
         "shows), promise (what we told the buyer), pending_approval (an action waiting for the "
         "merchant), external_id (ERP order / tracking no.), note.",
         ["customer_id", "kind", "text"],
         {"customer_id": cust,
          "kind": {"type": "string", "enum": list(asr.NOTE_KINDS)},
          "text": {"type": "string", "description": "The note, short (<= 500 chars)"},
          "order_id": {"type": "string", "description": "Platform order id, when known"},
          "ref": {"type": "string", "description": "A reference: 售后单 id, tracking no., evidence file"}})
    tool("aftersales_case_close",
         "Close the buyer's after-sales case once it is resolved (their next messages go to "
         "pre-sales service again).",
         ["customer_id"],
         {"customer_id": cust,
          "resolution": {"type": "string", "description": "How it was resolved, one line"}})
