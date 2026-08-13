"""Feige WS SEND prototype — live one-shot validation (feige_ws, Chunk 2).

Proves we can send a reply over the Feige Frontier socket instead of typing into
the DOM. Connects to the debug Chrome, hooks the page's WebSocket to grab the
Frontier socket handle, captures the operator's just-sent message as a template,
builds a modified frame (test text + fresh client_message_id via ws_sender), and
injects it back through the page's own authed socket.

SAFETY: dry-run by default (captures + builds + shows, does NOT send). Pass
--send to actually inject. It targets ONLY the conversation the template came
from, so send your template message in your THROWAWAY/TEST conversation.

  # 0. debug Chrome on 9228 with real Feige (https://im.jinritemai.com) logged in
  # 1. dry run — then send ONE message in your TEST conversation within 45s:
  python _feige_ws_send_test.py --port 9228
  # 2. if the dry run looks right, do it for real:
  python _feige_ws_send_test.py --port 9228 --send
"""
import argparse, asyncio, base64, json, sys, urllib.request, uuid
from pathlib import Path

# import the encoder/decoder directly (avoid pulling in the whole app)
_HOOK = Path(__file__).resolve().parent / "agent/ec_skills/browser_use_extension/hooks/external/feige_chat"
sys.path.insert(0, str(_HOOK))
import ws_reader, ws_sender  # noqa: E402
from cdp_use import CDPClient  # noqa: E402

TEST_TEXT = "【测试】这是通过WS帧直接发送的测试消息，请忽略"

HOOK_JS = r"""
(function(){
  if (window.__ecan_send_hooked) return "already-hooked";
  window.__ecan_send_hooked = true;
  var orig = WebSocket.prototype.send;
  WebSocket.prototype.send = function(data){
    try { if (this.url && this.url.indexOf('fxg.jinritemai.com') !== -1) window.__ecan_feige_ws = this; } catch(e){}
    return orig.apply(this, arguments);
  };
  return "hooked";
})()
"""

def INJECT_JS(b64):
    return ("(function(){var s=window.__ecan_feige_ws;if(!s)return 'NO_SOCKET';"
            "if(s.readyState!==1)return 'SOCKET_NOT_OPEN:'+s.readyState;"
            "var bin=atob('%s');var u=new Uint8Array(bin.length);"
            "for(var i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);"
            "s.send(u.buffer);return 'SENT bytes='+u.length;})()" % b64)

def _text(raw):
    d = ws_reader.decode(raw)
    v = ws_sender.get_path(d, ws_sender.TEXT_PATH) if d else None
    return v[1][1] if (v and isinstance(v[1], tuple) and v[1][0] == "str") else None

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9228)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--wait", type=int, default=45)
    ap.add_argument("--send", action="store_true", help="actually inject (default: dry run)")
    args = ap.parse_args()
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

    try:
        ver = json.loads(urllib.request.urlopen(f"http://{args.host}:{args.port}/json/version", timeout=5).read())
        ws_url = ver["webSocketDebuggerUrl"]
    except Exception as e:
        print(f"[send-test] cannot reach Chrome on {args.host}:{args.port}: {e}"); return 1

    client = CDPClient(url=ws_url); await client.start()
    targets = (await client.send_raw("Target.getTargets", {})).get("targetInfos", [])
    feige = [t for t in targets if t.get("type") == "page" and (t.get("url") or "").startswith("https://im.jinritemai.com")]
    if not feige:
        print("[send-test] no REAL https://im.jinritemai.com tab. Open + log into Feige first.")
        await client.stop(); return 1
    sid = (await client.send_raw("Target.attachToTarget", {"targetId": feige[0]["targetId"], "flatten": True})).get("sessionId")
    await client.send_raw("Network.enable", {}, session_id=sid)
    await client.send_raw("Runtime.enable", {}, session_id=sid)
    r = await client.send_raw("Runtime.evaluate", {"expression": HOOK_JS, "returnByValue": True}, session_id=sid)
    print(f"[send-test] WebSocket send-hook: {(r.get('result') or {}).get('value')}")

    template = {"raw": None, "text": None}
    def on_sent(params, session_id=None):
        try:
            resp = params.get("response", {}) or {}
            if int(resp.get("opcode", -1)) != 2: return
            raw = base64.b64decode(resp.get("payloadData", "") or "", validate=False)
            t = _text(raw)
            if t:  # a real chat-message send -> usable template
                template["raw"], template["text"] = raw, t
        except Exception: pass
    client._event_registry.register("Network.webSocketFrameSent", on_sent)

    # Delivery confirmation: when the server ACCEPTS our send it broadcasts the
    # message back (a recv render frame carrying our exact text + a server id), and
    # our client_message_id appears in the ack. Watch for either.
    pending = {"text": None, "cid": None}
    confirm = {"seen": False, "server_id": None, "via": None}
    def on_recv(params, session_id=None):
        try:
            if not pending["text"]:
                return
            resp = params.get("response", {}) or {}
            if int(resp.get("opcode", -1)) != 2:
                return
            raw = base64.b64decode(resp.get("payloadData", "") or "", validate=False)
            for m in ws_reader.extract_messages(raw):   # all roles (our echo is sender_role=2)
                if m.text == pending["text"]:
                    confirm.update(seen=True, server_id=m.msg_id, via="server echo (render frame)")
                    return
            if not confirm["seen"] and pending["cid"] and pending["cid"].encode() in raw:
                confirm.update(seen=True, via="client_message_id ack")
        except Exception:
            pass
    client._event_registry.register("Network.webSocketFrameReceived", on_recv)

    print(f"\n[send-test] >>> SEND ONE MESSAGE IN YOUR TEST CONVERSATION NOW (within {args.wait}s) <<<")
    waited = 0
    have_sock = False
    while waited < args.wait:
        await asyncio.sleep(3); waited += 3
        hv = await client.send_raw("Runtime.evaluate",
                                   {"expression": "(typeof window.__ecan_feige_ws!=='undefined' && window.__ecan_feige_ws? window.__ecan_feige_ws.readyState : -1)",
                                    "returnByValue": True}, session_id=sid)
        have_sock = ((hv.get("result") or {}).get("value")) == 1
        print(f"  +{waited}s  template_captured={template['raw'] is not None}  socket_handle={'OPEN' if have_sock else 'no'}")
        if template["raw"] is not None and have_sock:
            break

    if template["raw"] is None or not have_sock:
        print("\n[send-test] missing template or socket handle — did you send a message in the test conv? aborting.")
        await client.stop(); return 1

    cid = str(uuid.uuid4())
    frame = ws_sender.build_send_frame(template["raw"], text=TEST_TEXT, client_msg_id=cid)
    print(f"\n[send-test] template text : {template['text'][:46]!r}")
    print(f"[send-test] built    text : {TEST_TEXT!r}")
    print(f"[send-test] frame {len(frame)}B (template {len(template['raw'])}B)  client_id={cid}")

    if not args.send:
        print("\n[send-test] DRY RUN — not injecting. If the above looks right, re-run with --send.")
        await client.stop(); return 0

    pending["text"], pending["cid"] = TEST_TEXT, cid   # arm delivery confirmation
    rs = await client.send_raw("Runtime.evaluate",
                               {"expression": INJECT_JS(base64.b64encode(frame).decode()), "returnByValue": True},
                               session_id=sid)
    inj = (rs.get("result") or {}).get("value")
    print(f"\n[send-test] INJECT result: {inj}   (this only means the frame left the socket)")
    print("[send-test] watching recv frames for the SERVER's confirmation (echo of our text / cid ack)...")
    for i in range(15):
        await asyncio.sleep(1)
        if confirm["seen"]:
            break
        if i in (4, 9):
            print(f"   +{i+1}s  still waiting for server echo...")

    print("\n[send-test] ===== VERDICT =====")
    if confirm["seen"]:
        print(f"  ✅ DELIVERED — server ACCEPTED the WS send via {confirm['via']}"
              + (f"; server_id={confirm['server_id']}" if confirm["server_id"] else ""))
        print("     >>> WS write-back WORKS end-to-end. (Also eyeball the test conv to be 100%.)")
    else:
        print("  ⚠️  NOT CONFIRMED — frame left the socket but NO server echo/ack in 15s.")
        print("     Likely REJECTED (a field/sign/structure mismatch) or silently dropped.")
        print("     Check the test conv: if the 【测试】 message is NOT there, the frame was not accepted —")
        print("     send me the dry-run output + a fresh capture and I'll find the off field.")
    await asyncio.sleep(2)
    await client.stop(); return 0

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
