#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Helper chat commands: talk to the cloud helper / Manager from the terminal.

The same chat the GUI's helper panel shows, through the running app: the app's
handlers (skill_editor.chat.*) send and read history, and replies stream back
over the app's local WebSocket. The CLI listens on the "session:*" tap
(gui/LocalServer.py), which copies every session push without taking it away
from the GUI, so the panel and the terminal can follow the same chat.
"""

import json
import queue
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import click

from ..base.output import get_output

CHAT_EVENTS = ("skill_editor.chat.stream_chunk", "skill_editor.chat.stream_end", "skill_editor.chat.error")
PING_EVERY_S = 25          # the app closes sockets it hasn't heard from in 5 minutes


# ---- pure helpers (tested) ----

def parse_answers(answers: Tuple[str, ...], texts: Tuple[str, ...]) -> Dict[str, List[str]]:
    """--answer QID=CHOICE[,CHOICE] and --text QID=WORDS -> clarificationResponses
    ({qid: [choice ids]}, free text as freeform_<qid>, which picks the "other" choice)."""
    out: Dict[str, List[str]] = {}
    for item in answers:
        qid, sep, choices = item.partition("=")
        if not sep or not qid.strip() or not choices.strip():
            raise click.BadParameter(f"expected QID=CHOICE, got {item!r}", param_hint="--answer")
        out.setdefault(qid.strip(), []).extend(c.strip() for c in choices.split(",") if c.strip())
    for item in texts:
        qid, sep, words = item.partition("=")
        if not sep or not qid.strip() or not words.strip():
            raise click.BadParameter(f"expected QID=TEXT, got {item!r}", param_hint="--text")
        out.setdefault(qid.strip(), ["other"])
        out[f"freeform_{qid.strip()}"] = [words.strip()]
    return out


def clarification_questions(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The questions a reply asks, whether it sends a list or {questions: [...]}."""
    clar = payload.get("clarification")
    if isinstance(clar, dict):
        clar = clar.get("questions")
    return [q for q in (clar or []) if isinstance(q, dict)]


def format_questions(questions: List[Dict[str, Any]]) -> str:
    lines = []
    for q in questions:
        lines.append(f"  [{q.get('id')}] {q.get('question', '')}")
        for c in q.get("choices") or []:
            free = "  (+ --text)" if c.get("allow_freeform") else ""
            lines.append(f"      {c.get('id')}: {c.get('label', '')}{free}")
    lines.append("  Answer with: ecan helper send SESSION \"...\" --answer QID=CHOICE [--text QID=\"words\"]")
    return "\n".join(lines)


def message_text(m: Dict[str, Any]) -> str:
    return str(m.get("content") or m.get("fullContent") or "").strip()


def message_source(m: Dict[str, Any]) -> str:
    md = m.get("metadata") if isinstance(m.get("metadata"), dict) else {}
    return str(m.get("source") or md.get("source") or "")


class Printer:
    """Renders chat events for one session: chunks inline as they stream, the
    full text only when nothing streamed for that message, each message once."""

    def __init__(self, out, session_id: str):
        self.out, self.session_id = out, session_id
        self.streamed: Dict[str, bool] = {}
        self.done: set = set()
        self.ends = 0
        self.mid_line = False      # a chunk left the cursor mid-line

    def handle(self, event: Dict[str, Any]) -> bool:
        """Print one WebSocket event; True when it was for this session."""
        kind, p = event.get("type"), event.get("payload") or {}
        if kind not in CHAT_EVENTS or p.get("sessionId") != self.session_id:
            return False
        mid = str(p.get("messageId") or "")
        if kind == "skill_editor.chat.error":
            self.out.error(f"{p.get('message') or 'error'} ({p.get('code') or 'ERROR'})")
            self.ends += 1
            return True
        if kind == "skill_editor.chat.stream_chunk":
            if mid in self.done:
                return True
            if not self.streamed.get(mid):
                self._head(p)
                self.streamed[mid] = True
            self.out.print(p.get("chunk") or "", end="", flush=True)
            self.mid_line = True
            return True
        if mid in self.done:                                  # stream_end
            return True
        if self.streamed.get(mid):
            self.out.print()
            self.mid_line = False
        else:
            self._head(p)
            self.out.print(str(p.get("fullContent") or "").strip())
        questions = clarification_questions(p)
        if questions:
            self.out.print(format_questions(questions))
        self.done.add(mid)
        self.ends += 1
        return True

    def reply(self, result: Any) -> None:
        """The send call's own reply, when the stream did not already show it."""
        msg = result.get("message") if isinstance(result, dict) and isinstance(result.get("message"), dict) else result
        if not isinstance(msg, dict):
            return
        mid = str(msg.get("id") or msg.get("messageId") or "")
        if (mid and mid in self.done) or (not mid and self.ends):
            return
        self._head({"source": message_source(msg)})
        self.out.print(message_text(msg))
        questions = clarification_questions(result) or clarification_questions(msg)
        if questions:
            self.out.print(format_questions(questions))
        if mid:
            self.done.add(mid)
        self.ends += 1

    def _head(self, p: Dict[str, Any]) -> None:
        if self.mid_line:          # e.g. "Thinking..." status chunks with no end of their own
            self.out.print()
            self.mid_line = False
        who = "manager" if p.get("source") == "manager" else "helper"
        self.out.print(click.style(f"{who}> ", bold=True), end="", flush=True)


# ---- the app's push stream ----

class ChatStream:
    """Events from the app's local WebSocket "session:*" tap, on a queue."""

    def __init__(self, port: int):
        import websocket                                      # websocket-client
        self.events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._ws = websocket.create_connection(
            f"ws://127.0.0.1:{int(port)}/ws/skill-editor?channel=session:*", timeout=10)
        self._ws.settimeout(1)
        self._stop = threading.Event()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        import websocket
        last_ping = time.time()
        while not self._stop.is_set():
            if time.time() - last_ping > PING_EVERY_S:
                try:
                    self._ws.send(json.dumps({"type": "ping"}))
                except Exception:
                    break
                last_ping = time.time()
            try:
                raw = self._ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                break
            try:
                event = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if isinstance(event, dict) and event.get("type") in CHAT_EVENTS:
                self.events.put(event)
        self.events.put({"type": "closed"})

    def close(self) -> None:
        self._stop.set()
        try:
            self._ws.close()
        except Exception:
            pass


def _open_stream(out) -> Optional[ChatStream]:
    from ..base.app_client import AppNotRunning, find_app
    info = find_app()
    if not info:
        out.error(f"{AppNotRunning('eCan is not running')}. Start eCan first; this command works on the running app.")
        raise SystemExit(1)
    try:
        return ChatStream(info["port"])
    except Exception as e:
        out.warning(f"Live replies unavailable ({e}); showing the reply when the send finishes.")
        return None


def _follow(stream: Optional[ChatStream], printer: Printer, until, quiet_s: float) -> None:
    """Print events until until() is true and nothing came for quiet_s seconds."""
    last = time.time()
    while True:
        if until() and time.time() - last >= quiet_s:
            return
        if stream is None:
            time.sleep(0.2)
            continue
        try:
            event = stream.events.get(timeout=0.2)
        except queue.Empty:
            continue
        if event.get("type") == "closed":
            printer.out.warning("The app closed the live stream.")
            stream = None
            continue
        if printer.handle(event):
            last = time.time()


def _sessions() -> List[Dict[str, Any]]:
    from ..base.app_client import call
    r = call("skill_editor.chat.get_sessions", {}, timeout=60) or {}
    return list(r.get("sessions") or []) if isinstance(r, dict) else list(r or [])


def _history(session_id: str) -> List[Dict[str, Any]]:
    from ..base.app_client import call
    r = call("skill_editor.chat.get_history", {"sessionId": session_id}, timeout=60) or {}
    msgs = r.get("messages") if isinstance(r, dict) else r
    return [m for m in (msgs or []) if isinstance(m, dict)]


# ---- commands ----

@click.group()
def helper():
    """
    Chat with the cloud helper / Manager (the GUI's helper panel).

    CONTROL commands - need the running app.

    \b
    Examples:
      ecan helper new "store ads"
      ecan helper send SESSION "What did today's ads check find?"
      ecan helper send SESSION "go" --answer q1=c2 --text q3="only in chat"
      ecan helper watch SESSION
      ecan helper history SESSION --last 10
    """


@helper.command('sessions')
@click.option('--limit', '-n', default=20, show_default=True, help='How many, newest first')
def sessions_cmd(limit):
    """List helper chat sessions."""
    from ..base.app_client import AppCallError, AppNotRunning
    out = get_output()
    try:
        rows = _sessions()
    except (AppNotRunning, AppCallError) as e:
        out.error(str(e))
        raise SystemExit(1)
    rows.sort(key=lambda s: str(s.get("updatedAt") or s.get("createdAt") or ""), reverse=True)
    out.table("Helper chats", ["Session", "Name", "Updated"],
              [[s.get("id", ""), s.get("name", ""), str(s.get("updatedAt") or s.get("createdAt") or "")]
               for s in rows[:limit]])


@helper.command('new')
@click.argument('name', required=False, default='CLI chat')
def new_cmd(name):
    """Start a new helper chat; prints its session id."""
    from ..base.app_client import call_or_exit
    out = get_output()
    s = call_or_exit(out, "skill_editor.chat.create_session", {"name": name}, timeout=60) or {}
    sid = s.get("id") or s.get("sessionId") if isinstance(s, dict) else None
    if not sid:
        out.error(f"No session id in the reply: {json.dumps(s)[:300]}")
        raise SystemExit(1)
    out.print(sid)


@helper.command('history')
@click.argument('session_id')
@click.option('--last', '-n', default=20, show_default=True, help='Show the last N messages (0 = all)')
def history_cmd(session_id, last):
    """Show a chat's messages."""
    from ..base.app_client import AppCallError, AppNotRunning
    out = get_output()
    try:
        msgs = _history(session_id)
    except (AppNotRunning, AppCallError) as e:
        out.error(str(e))
        raise SystemExit(1)
    for m in (msgs[-last:] if last else msgs):
        role = m.get("role") or "?"
        who = "manager" if message_source(m) == "manager" else ("you" if role == "user" else "helper")
        stamp = str(m.get("timestamp") or m.get("createdAt") or "")
        out.print(click.style(f"{who} {stamp}".rstrip(), bold=True))
        out.print(message_text(m))
        out.print()


@helper.command('send')
@click.argument('session_id')
@click.argument('message')
@click.option('--answer', '-a', multiple=True, help='Answer a question: QID=CHOICE[,CHOICE] (repeatable)')
@click.option('--text', '-t', multiple=True, help='Free-text answer: QID="words" (repeatable)')
@click.option('--wait', '-w', default=10, show_default=True,
              help='After the reply, keep listening this many quiet seconds for follow-ups')
def send_cmd(session_id, message, answer, text, wait):
    """
    Send a message and print the reply as it streams.

    Use SESSION "new" to start a fresh chat. Background posts (e.g. the Manager
    reporting a build) keep printing until --wait seconds pass with nothing new;
    use `ecan helper watch` to follow a chat for longer.
    """
    from ..base.app_client import AppCallError, AppNotRunning, call, call_or_exit
    out = get_output()
    if session_id == "new":
        s = call_or_exit(out, "skill_editor.chat.create_session", {"name": message[:40]}, timeout=60) or {}
        session_id = s.get("id") or s.get("sessionId") or ""
        out.info(f"Session: {session_id}")
    params: Dict[str, Any] = {"sessionId": session_id, "content": message}
    responses = parse_answers(answer, text)
    if responses:
        params["clarificationResponses"] = responses

    stream = _open_stream(out)
    printer = Printer(out, session_id)
    box: Dict[str, Any] = {}

    def _send():
        try:
            box["result"] = call("skill_editor.chat.send_message", params, timeout=900)
        except (AppNotRunning, AppCallError) as e:
            box["error"] = e

    worker = threading.Thread(target=_send, daemon=True)
    worker.start()
    try:
        # The reply's stream_end usually lands just before the call returns; allow it a few seconds.
        _follow(stream, printer, lambda: not worker.is_alive(), quiet_s=3)
        if "error" in box:
            out.error(f"{box['error']}")
            raise SystemExit(1)
        printer.reply(box.get("result"))
        if wait > 0:
            _follow(stream, printer, lambda: True, quiet_s=wait)
    except KeyboardInterrupt:
        out.print()
    finally:
        if stream:
            stream.close()


@helper.command('watch')
@click.argument('session_id')
@click.option('--minutes', '-m', default=30, show_default=True, help='Stop after this many minutes (0 = until Ctrl+C)')
def watch_cmd(session_id, minutes):
    """Follow a chat: print every new message (yours, the helper's, the Manager's) as it arrives."""
    out = get_output()
    stream = _open_stream(out)
    if stream is None:
        raise SystemExit(1)
    printer = Printer(out, session_id)
    end = time.time() + minutes * 60 if minutes else None
    out.info(f"Watching {session_id} (Ctrl+C to stop)")
    try:
        _follow(stream, printer, lambda: end is not None and time.time() >= end, quiet_s=0)
    except KeyboardInterrupt:
        out.print()
    finally:
        stream.close()
