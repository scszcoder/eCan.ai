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
CMD_PATH = [8, 1]                # method/command code (chat send vs read-ack=2002 etc.)
READ_CMD = 2002                  # observed command code on conversation read-ack frames
READ_TALK_PATH = [8, 8, 604, 12] # talk_id (conversation) in a READ-ACK frame
READ_CURSOR_PATH = [8, 8, 604, 2]# "read up to" server msg id == a recv msg's .5 (read_cursor)
SENT_CONV_PATH = [8, 9]          # pigeon_cid in a SENT frame — MERCHANT-level, constant across
                                 # ALL customers of this shop (NOT a per-conversation key!)
SENT_TALK_PATH = [8, 8, 100, 14] # talk_id in a SENT frame — the real PER-CONVERSATION id
                                 # (== a recv msg's talk_id). Use THIS to key routing/templates.


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
    """pigeon_cid (.8.9) of a SENT frame — MERCHANT-level, constant. Kept for reference;
    do NOT key per-customer state on this (all customers share it)."""
    d = _wr().decode(template_bytes)
    v = get_path(d, SENT_CONV_PATH) if d else None
    if not v:
        return None
    return v[1][1] if isinstance(v[1], tuple) else v[1]


def sent_talk(template_bytes):
    """talk_id (.8.8.100.14) of a SENT frame, or None — the PER-CONVERSATION key that
    matches a recv message's talk_id. This is what routing/templates must key on."""
    d = _wr().decode(template_bytes)
    v = get_path(d, SENT_TALK_PATH) if d else None
    if not v:
        return None
    return str(v[1][1]) if isinstance(v[1], tuple) else str(v[1])


RECEIVER_ID_KEY = b"security_receiver_id\x12"   # kv entry: name + field-2 tag (.8.8.100.5)


def frame_receiver_id(frame_bytes: bytes) -> bytes | None:
    """Extract the security_receiver_id VALUE bytes from a SENT chat frame — the
    kv entry ``security_receiver_id`` + 0x12 (field-2 tag) + 1 length byte + value.
    Returns the raw value bytes, or None if absent/truncated."""
    i = frame_bytes.find(RECEIVER_ID_KEY)
    if i < 0:
        return None
    k = i + len(RECEIVER_ID_KEY)
    if k >= len(frame_bytes):
        return None
    ln = frame_bytes[k]
    val = frame_bytes[k + 1:k + 1 + ln]
    return val if len(val) == ln and ln > 0 else None


def build_first_contact_frame(session_template: bytes, *, receiver_id: str,
                              text: str, client_msg_id: str, talk_id: str = ""):
    """ws028: build a send frame for a conversation we have NO prior SENT template for,
    by cloning a session-wide donor frame and FULLY retargeting it to the target customer.

    Verified from captured frames (2026-06-08): chat sends route by **security_receiver_id**
    (the .8.8.100 envelope carries it — at the .5 kv entry and the .50 mirror — and has NO
    talk_id field), and that id == the customer's inbound ``security_sender_id``. So we swap
    the donor's security_receiver_id for the target customer's id (``receiver_id``) at EVERY
    occurrence, then swap text + a fresh client_msg_id.

    SAFE-BY-CONSTRUCTION: the receiver ids are fixed length (88 chars). We only retarget when
    the donor id is present and the target id is the SAME length (a clean in-place byte swap
    that can't shift the protobuf or leave a donor field behind). Any mismatch → return None
    so the caller falls back to the guarded DOM send rather than risk a mis-delivery. The
    server echo (keyed on our client_msg_id) is the second net. ``talk_id`` is swapped too
    only if the template happens to carry one (current frames don't)."""
    target = str(receiver_id or "").encode("latin-1", "replace")
    if not target:
        return None
    dec = _wr().decode(session_template)
    if dec is None:
        raise ValueError("session template did not decode")
    dec = set_path(dec, TEXT_PATH, (2, ("str", text)))
    if get_path(dec, CLIENT_ID_PATH) is not None:
        dec = set_path(dec, CLIENT_ID_PATH, (2, ("str", client_msg_id)))
    # ws032: talk_id at .8.8.100.14 is a VARINT (wiretype 0) in a genuine Feige
    # send frame (verified: confirmed frames + build_read_ack both use wt0). ws028
    # wrote it as a wt2 length-delimited string, producing a MALFORMED frame that
    # the server silently drops — so EVERY first-contact send (first reply on a new
    # conversation) never delivered and never echoed back, which then stalled the
    # serial delivery worker on wait_confirmed (4s+8s) and jammed the pipeline.
    # Write it as the correct varint; if talk_id isn't numeric, skip the first
    # contact entirely (return None → DOM fallback) rather than emit a bad frame.
    if talk_id:
        try:
            _talk_int = int(str(talk_id))
        except (TypeError, ValueError):
            return None
        if get_path(dec, SENT_TALK_PATH) is not None:
            dec = set_path(dec, SENT_TALK_PATH, (0, _talk_int))
    out = encode(dec)
    donor = frame_receiver_id(out)
    if donor is None or len(donor) != len(target):
        # donor id missing, or a length mismatch that would corrupt the frame /
        # leave the donor's customer addressed → refuse, let the caller use DOM.
        return None
    if donor != target:
        out = out.replace(donor, target)
    return out


def is_read_ack(frame_bytes):
    """True iff *frame_bytes* is a conversation read-ack (cmd .8.1==2002 with a
    talk_id at .8.8.604.12). Used to recognise/cache read-ack templates."""
    d = _wr().decode(frame_bytes)
    if d is None:
        return False
    cmd = get_path(d, CMD_PATH)
    cmdv = cmd[1] if cmd else None
    return cmdv == READ_CMD and get_path(d, READ_TALK_PATH) is not None


def read_ack_talk(frame_bytes):
    """talk_id (.8.8.604.12) of a read-ack frame, or None."""
    d = _wr().decode(frame_bytes)
    v = get_path(d, READ_TALK_PATH) if d else None
    if not v:
        return None
    return str(v[1][1]) if isinstance(v[1], tuple) else str(v[1])


def build_read_ack(template_bytes: bytes, *, talk_id: str, cursor: str):
    """已读 (tier 0): clone a captured read-ack template (cmd 2002) and retarget it to
    *talk_id* with *cursor* = the "read up to" server msg id (a recv msg's read_cursor /
    .5). Reuses the template's session-static pigeon_sign + envelope, like the send.
    Returns the frame, or None if the template/values don't fit."""
    dec = _wr().decode(template_bytes)
    if dec is None:
        raise ValueError("read-ack template did not decode")
    if get_path(dec, READ_TALK_PATH) is None or get_path(dec, READ_CURSOR_PATH) is None:
        return None
    dec = set_path(dec, READ_TALK_PATH, (0, int(talk_id)))
    try:
        dec = set_path(dec, READ_CURSOR_PATH, (0, int(cursor)))
    except (TypeError, ValueError):
        return None   # cursor not numeric — can't build a valid read-ack
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
