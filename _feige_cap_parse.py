"""Parse [FEIGE-WS-CAP-JSON] records out of a customer eCan.log (in-app capture,
ECAN_FEIGE_WS_CAPTURE=1) and produce the API-bypass feasibility verdict:

  - WS frames: text vs binary, distinct WS urls, + naive protobuf string-field
    extraction on sample binary frames (spot the message-text field fast).
  - HTTP: ByteDance endpoints hit + WHICH anti-bot/auth tokens appear.
  - js_probe: in-page send-handle candidates (window.* with send/dispatch).
Also writes the full records to a clean JSONL for deeper offline decoding.

Usage: python _feige_cap_parse.py customer_logs/eCan.log
"""
import sys, json, base64, re
from collections import Counter
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

LOG = sys.argv[1] if len(sys.argv) > 1 else "customer_logs/eCan.log"
TAG = "[FEIGE-WS-CAP-JSON] "
recs = []
for line in open(LOG, encoding="utf-8", errors="replace"):
    i = line.find(TAG)
    if i < 0:
        continue
    try:
        recs.append(json.loads(line[i + len(TAG):]))
    except Exception:
        pass

if not recs:
    print(f"No [FEIGE-WS-CAP-JSON] records in {LOG}.")
    print("Capture not run? Customer must set ECAN_FEIGE_WS_CAPTURE=1, restart, use real Feige a few min.")
    sys.exit()

out = LOG.rsplit(".", 1)[0] + "_feigecap.jsonl"
with open(out, "w", encoding="utf-8") as fh:
    for r in recs:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")

ws = [r for r in recs if r.get("k") == "ws"]
http = [r for r in recs if r.get("k") == "http"]
probes = [r for r in recs if r.get("k") == "js_probe"]
print(f"records={len(recs)}  ws={len(ws)}  http={len(http)}  js_probe={len(probes)}  -> {out}\n")

# ---- WS ----
txt = [r for r in ws if r.get("opcode") == 1]
binr = [r for r in ws if r.get("opcode") == 2]
print(f"=== WS FRAMES === text(opcode1)={len(txt)}  binary(opcode2)={len(binr)}")
for u, c in Counter(r.get("url", "?") for r in ws).most_common(6):
    print(f"  url: {u[:90]}  ({c} frames)")

def proto_strings(raw: bytes, maxn=8):
    """Naive protobuf wire walk: pull length-delimited (wiretype 2) fields that
    decode as printable UTF-8 — usually the human-readable message fields."""
    out, p, n = [], 0, 0
    while p < len(raw) and n < maxn:
        tag = raw[p]; p += 1
        field, wt = tag >> 3, tag & 7
        if wt == 2:
            ln = 0; sh = 0
            while p < len(raw):
                b = raw[p]; p += 1; ln |= (b & 0x7f) << sh; sh += 7
                if not (b & 0x80): break
            chunk = raw[p:p + ln]; p += ln
            try:
                s = chunk.decode("utf-8")
                if s and sum(ch.isprintable() for ch in s) > len(s) * 0.7:
                    out.append((field, s[:80])); n += 1
            except Exception:
                pass
        elif wt == 0:  # varint
            while p < len(raw) and (raw[p] & 0x80): p += 1
            p += 1
        else:
            break
    return out

if binr:
    print("\n  sample BINARY frames (first bytes hex + extracted string fields):")
    for r in binr[:6]:
        try:
            raw = base64.b64decode(r.get("payload_b64", ""), validate=False)
        except Exception:
            continue
        strs = proto_strings(raw)
        print(f"    [{r.get('dir')}] {len(raw)}B head={raw[:16].hex()}")
        for f, s in strs:
            print(f"        field#{f}: {s!r}")

# ---- HTTP / anti-bot ----
print(f"\n=== HTTP (ByteDance) === {len(http)} data-bearing requests")
AUTH = ["x-bogus", "a_bogus", "mstoken", "x-gorgon", "x-khronos", "x-ladon", "ttwid",
        "odin_tt", "x-tt-", "sec-", "sign", "signature", "_signature"]
seen_auth = Counter()
for r in http:
    hdrs = {k.lower(): v for k, v in (r.get("headers") or {}).items()}
    url = r.get("url", "")
    blob = (url + " " + " ".join(hdrs.keys())).lower()
    for a in AUTH:
        if a in blob:
            seen_auth[a] += 1
for u, c in Counter(re.sub(r"\?.*$", "", r.get("url", "")) for r in http).most_common(8):
    print(f"  {u[:100]}  ({c})")
print(f"  anti-bot/auth tokens present: {dict(seen_auth) or 'NONE seen'}")

# ---- in-page send handle ----
print("\n=== IN-PAGE SEND-HANDLE PROBE ===")
best = {}
for p in probes:
    for c in (p.get("probe", {}).get("sendCandidates") or []):
        best[c["key"]] = c["members"]
if best:
    for k, m in list(best.items())[:12]:
        print(f"  window.{k} -> {m}")
else:
    rr = any(p.get("probe", {}).get("reactRoot") for p in probes)
    print(f"  no window.* send candidates (reactRoot={rr}) -> in-page send likely buried in React; "
          f"send stays on DOM, detection-only win")

print("\n=== VERDICT HINTS ===")
print(f"  READ:  {'binary protobuf present -> decode offline, passive detection FEASIBLE' if binr else ('text frames -> even easier' if txt else 'NO WS frames captured (wrong tab? too short?)')}")
print(f"  SEND-raw:  {'anti-bot tokens present -> raw replay HARD (use in-page JS)' if seen_auth else 'no auth tokens seen in captured reqs (capture a real send to confirm)'}")
print(f"  SEND-inpage: {'candidate handle(s) found -> in-page JS send PLAUSIBLE' if best else 'no obvious handle -> needs deeper React probe'}")
