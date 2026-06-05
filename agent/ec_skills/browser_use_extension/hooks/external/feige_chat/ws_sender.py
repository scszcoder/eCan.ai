"""Feige Frontier WebSocket SEND-frame builder — PLATFORM-SPECIFIC HOOK (feige_ws).

The send half of the API bypass: instead of typing a reply into the Feige DOM
(serial, typing-lock-gated, the real throughput bottleneck), construct the same
binary Frontier protobuf frame the page sends and put it on the socket.

Send-frame schema reverse-engineered from captured SENT frames:
   .8.8.100.4  = reply text
   .8.8.100.8  = client_message_id (uuid; server dedups on it -> must be fresh)
   .8.8.100.5  = kv-map: security_receiver_id (target customer), s:client_message_id,
                 shop_id, sender_role, track_info, ...
   .5.2 / .8.15 = pigeon_sign (session-STATIC, reusable -> no per-message anti-bot)

Chunk 1 (this module): a faithful protobuf encoder (round-trips captured frames
byte-exact) + build_send_frame() that clones a template and swaps text +
client_message_id.  Chunk 2 will capture a live per-conversation template + the
socket handle and inject via WebSocket.send.

Self-contained except ws_reader.decode (same package).  Offline-testable:
  python ws_sender.py customer_logs/eCan_feigecap.jsonl
"""
from __future__ import annotations
import sys
# ws_reader is imported lazily (relative in-package; direct in the __main__ CLI)
# so this module works both as a package member and run as a standalone script.


def _enc_varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7f
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def encode(fields) -> bytes:
    """Inverse of ws_reader.decode: (field, wiretype, value)[] -> protobuf bytes.
    value: wt0=int, wt1=8 bytes, wt5=4 bytes, wt2=('str',s)/('msg',[...])/('bytes',b)."""
    out = bytearray()
    for (f, wt, v) in fields:
        out += _enc_varint((f << 3) | wt)
        if wt == 0:
            out += _enc_varint(int(v))
        elif wt == 1:
            out += bytes(v)[:8].ljust(8, b"\x00")
        elif wt == 2:
            if isinstance(v, tuple):
                kind, payload = v
                if kind in ("str", "gzip_str"):
                    data = payload.encode("utf-8", "surrogatepass")
                elif kind in ("msg", "gzip_msg"):
                    data = encode(payload)
                else:  # bytes
                    data = bytes(payload)
            else:
                data = bytes(v)
            out += _enc_varint(len(data)) + data
        elif wt == 5:
            out += bytes(v)[:4].ljust(4, b"\x00")
        else:
            raise ValueError(f"cannot encode wiretype {wt} (field {f})")
    return bytes(out)


def get_path(dec, path):
    cur = dec
    for i, fp in enumerate(path):
        found = None
        for (f, wt, v) in cur:
            if f == fp:
                found = (wt, v)
        if found is None:
            return None
        wt, v = found
        if i == len(path) - 1:
            return (wt, v)
        if wt == 2 and isinstance(v, tuple) and v[0] in ("msg", "gzip_msg"):
            cur = v[1]
        else:
            return None
    return None


def set_path(dec, path, new_wt_val):
    """Return a new decoded list with field at `path` replaced by (wt, value)."""
    fp = path[0]
    out = []
    replaced = False
    for (f, wt, v) in dec:
        if f == fp and not replaced:
            if len(path) == 1:
                out.append((f, new_wt_val[0], new_wt_val[1]))
            elif wt == 2 and isinstance(v, tuple) and v[0] == "msg":
                out.append((f, 2, ("msg", set_path(v[1], path[1:], new_wt_val))))
            else:
                out.append((f, wt, v))  # path doesn't match structure; leave as-is
            replaced = True
        else:
            out.append((f, wt, v))
    return out


TEXT_PATH = [8, 8, 100, 4]
CLIENT_ID_PATH = [8, 8, 100, 8]
SENT_CONV_PATH = [8, 9]          # pigeon_cid in a SENT frame (== a recv msg's pigeon_cid)


def _wr():
    try:
        from . import ws_reader as m
    except Exception:
        import ws_reader as m
    return m


def frame_text(template_bytes):
    """Reply text in a SENT frame (.8.8.100.4); None if not a chat-message frame."""
    d = _wr().decode(template_bytes)
    v = get_path(d, TEXT_PATH) if d else None
    return v[1][1] if (v and isinstance(v[1], tuple) and v[1][0] == "str") else None


def sent_conv(template_bytes):
    """pigeon_cid (.8.9) of a SENT frame, or None — keys the per-conversation template."""
    d = _wr().decode(template_bytes)
    v = get_path(d, SENT_CONV_PATH) if d else None
    if not v:
        return None
    return v[1][1] if isinstance(v[1], tuple) else v[1]


def build_first_contact_frame(session_template: bytes, *, pigeon_cid: str,
                              text: str, client_msg_id: str):
    """S3: build a send frame for a conversation we have NO prior SENT template for,
    by cloning a session-wide template (any conversation — it donates the
    session-static pigeon_sign + the full send envelope) and retargeting it to
    `pigeon_cid` (.8.9) with our text + a fresh client_msg_id.

    UNVERIFIED: this swaps ONLY the conversation id, not security_receiver_id
    (.8.8.100.5). If the server routes purely by pigeon_cid this delivers to the
    right customer; if it also binds to the receiver id, it would mis-route. We have
    no captured cross-conversation data to settle this, so the caller MUST gate it
    (ECAN_FEIGE_WS_FIRST_CONTACT) and confirm via the server echo. Returns the frame
    or None when the template's .8.9 isn't a plain string (then fall back to DOM)."""
    dec = _wr().decode(session_template)
    if dec is None:
        raise ValueError("session template did not decode")
    cur = get_path(dec, SENT_CONV_PATH)
    if not (cur and cur[0] == 2 and isinstance(cur[1], tuple) and cur[1][0] == "str"):
        return None   # .8.9 not a str in this template — can't safely retarget
    dec = set_path(dec, SENT_CONV_PATH, (2, ("str", str(pigeon_cid))))
    dec = set_path(dec, TEXT_PATH, (2, ("str", text)))
    if get_path(dec, CLIENT_ID_PATH) is not None:
        dec = set_path(dec, CLIENT_ID_PATH, (2, ("str", client_msg_id)))
    return encode(dec)


def build_send_frame(template_bytes: bytes, *, text: str, client_msg_id: str) -> bytes:
    """Clone a captured SENT frame and swap in our `text` + a fresh client_msg_id.
    Reuses the template's session params (pigeon_sign, session_did, device,
    security_receiver_id) — so this targets the SAME conversation the template
    came from.  Cross-conversation send needs the receiver swapped too (Chunk 2)."""
    try:
        from . import ws_reader as _wr           # package member
    except Exception:
        import ws_reader as _wr                   # standalone script
    dec = _wr.decode(template_bytes)
    if dec is None:
        raise ValueError("template did not decode")
    dec = set_path(dec, TEXT_PATH, (2, ("str", text)))
    if get_path(dec, CLIENT_ID_PATH) is not None:
        dec = set_path(dec, CLIENT_ID_PATH, (2, ("str", client_msg_id)))
    return encode(dec)


# ------------------------------------------------------------------------- CLI
if __name__ == "__main__":
    import json, base64, uuid
    # import ws_reader directly when run as a script (no package context)
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    import ws_reader as wr
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    src = sys.argv[1] if len(sys.argv) > 1 else "customer_logs/eCan_feigecap.jsonl"

    sent = [json.loads(l) for l in open(src, encoding="utf-8", errors="replace")
            if '"dir": "sent"' in l and '"opcode": 2' in l]
    print(f"sent binary frames: {len(sent)}")

    # 1) round-trip faithfulness: encode(decode(raw)) == raw ?
    exact = total = 0
    template = None
    for d in sent:
        raw = base64.b64decode(d["payload_b64"], validate=False)
        dec = wr.decode(raw)
        if dec is None:
            continue
        total += 1
        if encode(dec) == raw:
            exact += 1
        if template is None and get_path(dec, TEXT_PATH) is not None:
            template = raw
    print(f"round-trip byte-exact: {exact}/{total}  (faithful encoder if == total)")

    # 2) build a modified send frame from a real template
    if template:
        old = get_path(wr.decode(template), TEXT_PATH)
        new_text = "【测试】这是一条通过WS帧构造的回复，请忽略"
        cid = str(uuid.uuid4())
        frame = build_send_frame(template, text=new_text, client_msg_id=cid)
        re = wr.decode(frame)
        got = get_path(re, TEXT_PATH)
        print(f"\ntemplate text : {old[1][1][:40]!r}")
        print(f"built  text   : {got[1][1][:40]!r}")
        print(f"new client_id : {cid}")
        print(f"frame bytes   : {len(frame)} (template {len(template)})  decodes_ok={re is not None}")
        print(f"text swapped OK: {got[1][1] == new_text}")
    else:
        print("no template frame with text at .8.8.100.4 found")
