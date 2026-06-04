"""Recursive protobuf decoder for the captured Feige Frontier WS frames — proves
the READ path: can we pull customer message text (incl. product cards) out of the
raw binary frames without the .proto schema?

Reads the *_feigecap.jsonl produced by _feige_cap_parse.py (k=="ws" records),
recursively decodes each frame's protobuf wire format (auto-detecting nested
messages vs strings vs gzip-compressed sub-messages), and prints the human
strings found per frame — so we can see the message body.

Usage: python _feige_proto_decode.py customer_logs/eCan_feigecap.jsonl
"""
import sys, json, base64, gzip, zlib
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

SRC = sys.argv[1] if len(sys.argv) > 1 else "customer_logs/eCan_feigecap.jsonl"

def read_varint(b, p):
    shift = 0; val = 0
    while p < len(b):
        c = b[p]; p += 1
        val |= (c & 0x7f) << shift
        if not (c & 0x80):
            return val, p
        shift += 7
        if shift > 63:
            return None, p
    return None, p

def printable_ratio(s):
    if not s: return 0.0
    return sum(ch.isprintable() or ch in "\n\t" for ch in s) / len(s)

def try_text(chunk):
    try:
        s = chunk.decode("utf-8")
    except Exception:
        return None
    return s if printable_ratio(s) > 0.85 else None

def decode_msg(b, depth=0, maxdepth=8):
    """Return list of (field, wiretype, value) or None if not a clean message."""
    out = []; p = 0
    while p < len(b):
        tag, p = read_varint(b, p)
        if tag is None: return None
        field = tag >> 3; wt = tag & 7
        if field == 0: return None
        if wt == 0:
            v, p = read_varint(b, p)
            if v is None: return None
            out.append((field, 0, v))
        elif wt == 1:
            if p + 8 > len(b): return None
            out.append((field, 1, b[p:p+8].hex())); p += 8
        elif wt == 2:
            ln, p = read_varint(b, p)
            if ln is None or p + ln > len(b): return None
            chunk = b[p:p+ln]; p += ln
            out.append((field, 2, _decode_ld(chunk, depth)))
        elif wt == 5:
            if p + 4 > len(b): return None
            out.append((field, 5, b[p:p+4].hex())); p += 4
        else:
            return None  # 3/4 (groups) / unknown -> not a clean message
    return out

def _decode_ld(chunk, depth):
    """Length-delimited: try text, then gzip/zlib+message, then nested message."""
    t = try_text(chunk)
    if t is not None and len(t) >= 1:
        # prefer text unless it ALSO cleanly decodes as a rich message (rare)
        return ("str", t)
    if depth < 8 and len(chunk) > 1:
        # gzip / zlib?
        for dec in (lambda c: gzip.decompress(c), lambda c: zlib.decompress(c)):
            try:
                raw = dec(chunk)
                sub = decode_msg(raw, depth+1)
                if sub: return ("gzip_msg", sub)
                tt = try_text(raw)
                if tt: return ("gzip_str", tt)
            except Exception:
                pass
        sub = decode_msg(chunk, depth+1)
        if sub is not None:
            return ("msg", sub)
    return ("bytes", chunk[:48].hex())

def collect_strings(decoded, path="", acc=None):
    if acc is None: acc = []
    for (field, wt, val) in decoded:
        fp = f"{path}.{field}"
        if wt == 2 and isinstance(val, tuple):
            kind, payload = val
            if kind in ("str", "gzip_str"):
                if any(ord(c) > 0x2000 for c in payload) or len(payload) >= 4:  # keep CJK / meaningful
                    acc.append((fp, kind, payload[:160]))
            elif kind in ("msg", "gzip_msg"):
                collect_strings(payload, fp, acc)
    return acc

# ---- run ----
recs = []
for line in open(SRC, encoding="utf-8", errors="replace"):
    try:
        d = json.loads(line)
    except Exception:
        continue
    if d.get("k") == "ws":
        recs.append(d)

recv = [r for r in recs if r.get("dir") == "recv" and r.get("opcode") == 2]
sent = [r for r in recs if r.get("dir") == "sent" and r.get("opcode") == 2]
print(f"frames: recv_binary={len(recv)} sent_binary={len(sent)}\n")

import re
CJK = re.compile(r"[一-鿿]")
hits = 0
print("=== RECV frames — extracted strings (looking for customer message text) ===")
for r in recv:
    try:
        raw = base64.b64decode(r.get("payload_b64", ""), validate=False)
    except Exception:
        continue
    dec = decode_msg(raw)
    if not dec:
        continue
    strs = collect_strings(dec)
    cjk = [(fp, s) for (fp, k, s) in strs if CJK.search(s)]
    if cjk:
        hits += 1
        if hits <= 25:
            print(f"\n  frame {len(raw)}B:")
            for fp, s in cjk[:12]:
                print(f"     {fp}: {s!r}")
print(f"\n=== {hits}/{len(recv)} recv frames contained CJK text (customer/agent message content) ===")
print("If message text appears above with stable field paths -> passive WS READ is PROVEN decodable.")
