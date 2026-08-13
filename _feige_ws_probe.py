"""Feige API-bypass feasibility probe (2026-06-04, spike b).

Connects to a debuggable Chrome (existing-chrome mode), attaches to the Feige
tab(s), and in ONE session captures the three things we need to decide whether
eCan can bypass the DOM:

  1. WS frames recv+sent — FULL payloads (base64 for binary) to a JSONL file,
     so the protobuf can be decoded offline. (the mt059 in-app capture only
     logged 24 bytes — useless for decoding; this is the fix.)
  2. HTTP requests to *.jinritemai.com — method/url/headers/postData — so we see
     the SEND endpoint + the anti-bot/auth shape (X-Bogus/a_bogus/msToken/...).
  3. In-page JS probe — enumerate window for IM-SDK / send-function candidates,
     so we know if an in-page-JS send (no anti-bot RE) is reachable.

REQUIREMENT: run against a Chrome that has the REAL Feige open + logged in
(https://im.jinritemai.com/...). The 127.0.0.1:9876 emulation has no ByteDance
WS, so it only validates the plumbing.

  # 1. ensure Chrome has remote debugging (existing-chrome harness uses 9228):
  #    chrome.exe --remote-debugging-port=9228 --user-data-dir="C:\\chrome_data"
  # 2. open + log into https://im.jinritemai.com, have a test customer send a msg
  # 3. run:
  python _feige_ws_probe.py --port 9228 --seconds 180
  # 4. send back runlogs/feige_capture_<ts>.jsonl + the printed summary
"""
import argparse, asyncio, json, time, urllib.request
from pathlib import Path
from cdp_use import CDPClient

REPO = Path(__file__).resolve().parent

JS_PROBE = r"""
(function(){
  var out={globals:[], sendCandidates:[], reactRoot:false, wsResources:[], error:null};
  try {
    var rx=/(^|_)(im|sdk|message|msg|send|chat|frontier|wschannel|pace|byted|pigeon|toutiao|slardar)/i;
    var keys=Object.getOwnPropertyNames(window);
    for (var i=0;i<keys.length;i++){
      var k=keys[i]; if(!rx.test(k)) continue;
      var v; try{v=window[k];}catch(e){continue;}
      var t=typeof v; if(t!=='object'&&t!=='function') { out.globals.push({key:k,type:t}); continue; }
      out.globals.push({key:k,type:t});
      try{
        var members=[];
        for(var p in v){ try{ if(/send|message|emit|publish|dispatch|conn|socket/i.test(p)) members.push(p+':'+(typeof v[p])); }catch(e){} }
        if(members.length) out.sendCandidates.push({key:k, members:members.slice(0,24)});
      }catch(e){}
    }
    out.reactRoot = !!document.querySelector('#root,[data-reactroot]');
    out.wsResources = (performance.getEntriesByType('resource')||[])
      .map(function(r){return r.name;}).filter(function(n){return /^wss?:/.test(n);}).slice(0,12);
  } catch(e){ out.error=String(e); }
  return JSON.stringify(out);
})()
"""

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9228)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--match", default="jinritemai", help="substring to match Feige tab URLs")
    ap.add_argument("--seconds", type=int, default=180)
    ap.add_argument("--max-frames", type=int, default=2000)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    ts = int(time.time())
    out_path = Path(args.out) if args.out else REPO / "runlogs" / f"feige_capture_{ts}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 1) browser-level CDP endpoint
    try:
        ver = json.loads(urllib.request.urlopen(
            f"http://{args.host}:{args.port}/json/version", timeout=5).read().decode())
        ws_url = ver["webSocketDebuggerUrl"]
    except Exception as exc:
        print(f"[probe] cannot reach Chrome on {args.host}:{args.port}: {exc}")
        print("        launch Chrome with --remote-debugging-port=%d first." % args.port)
        return 1

    client = CDPClient(url=ws_url)
    await client.start()
    targets = (await client.send_raw("Target.getTargets", {})).get("targetInfos", [])
    feige = [t for t in targets if t.get("type") == "page" and args.match in (t.get("url") or "")]
    if not feige:
        print(f"[probe] no page target matching {args.match!r}. Open + log into real Feige first.")
        print("        tabs seen:", [t.get("url","")[:70] for t in targets if t.get("type")=="page"][:10])
        await client.stop(); return 1

    real = [t for t in feige if (t.get("url") or "").startswith("https://im.jinritemai.com")]
    print(f"[probe] {len(feige)} Feige tab(s) ({len(real)} real https). Capturing {args.seconds}s -> {out_path.name}")
    for t in feige:
        print(f"        - {t.get('url','')[:80]}  ({'REAL' if t in real else 'emulation/other'})")
    if not real:
        print("[probe] WARNING: no REAL https://im.jinritemai.com tab — protobuf won't appear (emulation has no ByteDance WS).")

    out = out_path.open("w", encoding="utf-8")
    counts = {"ws_recv": 0, "ws_sent": 0, "http": 0}
    ws_urls = {}   # requestId -> url

    def emit(rec):
        rec["t"] = time.time()
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def on_ws_created(params, session_id=None):
        try:
            ws_urls[params.get("requestId","")] = params.get("url","")
            emit({"k": "ws_created", "url": params.get("url",""), "sid": session_id})
        except Exception: pass

    def on_frame(direction):
        ck = "ws_recv" if direction == "recv" else "ws_sent"
        def h(params, session_id=None):
            try:
                if counts[ck] >= args.max_frames: return
                resp = params.get("response", {}) or {}
                op = int(resp.get("opcode", -1))
                if op in (8, 9, 10): return   # close/ping/pong noise
                counts[ck] += 1
                emit({"k": "ws", "dir": direction, "opcode": op,
                      "url": ws_urls.get(params.get("requestId",""), "?"),
                      "payload_b64": resp.get("payloadData", "")})   # FULL payload
            except Exception: pass
        return h

    def on_http(params, session_id=None):
        try:
            req = params.get("request", {}) or {}
            url = req.get("url", "")
            if "jinritemai" not in url and "byted" not in url and "douyin" not in url:
                return
            if req.get("method") == "GET" and not req.get("postData"):
                return   # only POST/data-bearing (sends/actions), skip GET asset noise
            counts["http"] += 1
            emit({"k": "http", "method": req.get("method"), "url": url,
                  "headers": req.get("headers", {}), "postData": req.get("postData", "")})
        except Exception: pass

    reg = client._event_registry
    sids = []
    for t in feige:
        sid = (await client.send_raw("Target.attachToTarget",
                                     {"targetId": t["targetId"], "flatten": True})).get("sessionId")
        if not sid: continue
        sids.append(sid)
        await client.send_raw("Network.enable", {}, session_id=sid)
        await client.send_raw("Runtime.enable", {}, session_id=sid)
    reg.register("Network.webSocketCreated", on_ws_created)
    reg.register("Network.webSocketFrameReceived", on_frame("recv"))
    reg.register("Network.webSocketFrameSent", on_frame("sent"))
    reg.register("Network.requestWillBeSent", on_http)

    # live progress
    waited = 0
    while waited < args.seconds:
        await asyncio.sleep(min(15, args.seconds - waited)); waited += 15
        out.flush()
        print(f"[probe] +{waited}s  ws_recv={counts['ws_recv']} ws_sent={counts['ws_sent']} http={counts['http']}")

    # in-page send-handle probe (per session)
    print("\n[probe] ===== IN-PAGE SEND-HANDLE PROBE =====")
    for sid in sids:
        try:
            r = await client.send_raw("Runtime.evaluate",
                                      {"expression": JS_PROBE, "returnByValue": True}, session_id=sid)
            val = (r.get("result", {}) or {}).get("value")
            if val:
                probe = json.loads(val)
                emit({"k": "js_probe", "sid": sid, "probe": probe})
                cands = probe.get("sendCandidates", [])
                print(f"  session {sid[-6:]}: reactRoot={probe.get('reactRoot')} "
                      f"globals={len(probe.get('globals',[]))} sendCandidates={len(cands)}")
                for c in cands[:8]:
                    print(f"      window.{c['key']} -> {c['members']}")
                if probe.get("wsResources"):
                    print(f"      live WS: {probe['wsResources']}")
        except Exception as exc:
            print(f"  session {sid[-6:]}: probe failed: {exc}")

    out.flush(); out.close()
    print(f"\n[probe] ===== SUMMARY =====")
    print(f"  ws_recv={counts['ws_recv']} ws_sent={counts['ws_sent']} http={counts['http']}")
    print(f"  capture -> {out_path}")
    # quick text/binary split of WS frames
    txt = bin_ = 0
    for l in out_path.read_text(encoding="utf-8").splitlines():
        try: d = json.loads(l)
        except Exception: continue
        if d.get("k") == "ws":
            if d.get("opcode") == 1: txt += 1
            elif d.get("opcode") == 2: bin_ += 1
    print(f"  WS frames: text(opcode1)={txt}  binary(opcode2)={bin_}  (binary => protobuf, decode offline)")
    try: await client.stop()
    except Exception: pass
    return 0

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
