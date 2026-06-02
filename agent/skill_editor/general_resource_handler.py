"""
General-purpose resource & Q&A handler for the app-wide eCan.ai agent.

The skill-editor agent classifies each request into an (action, resource) pair
(see ActionType / ResourceType in schemas.py). When the resource is something
other than a skill — an agent, task, prompt, the product docs, or the source
code — the request is delegated here instead of the skill-editor pipeline.

Design notes:
  * Agent/task CRUD is PROPOSE-ONLY: the cloud agent never writes a DB. It
    emits the equivalent local `ecan` CLI command (carried in the response
    metadata as `cli_command` + a structured `proposal`). The client runs it;
    the sync-capable CLI applies it locally and propagates to cloud; the client
    then posts the run result back as context. Write ops carry
    `requires_confirmation` unless the session opted out via the `/` skip command.
  * Source/doc Q&A reads the repo on disk (EC2), gated by ECAN_REPO_ROOT.
  * LLM access, user identity and language are injected by the caller so
    responses stay consistent with the rest of the agent.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from .schemas import AgentResponse, IntentType, ActionType, ResourceType

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    return Path(os.environ.get("ECAN_REPO_ROOT", "/home/ubuntu/repo/eCan.ai"))


# Directories we never want to walk when searching source / docs.
_SKIP_DIRS = {
    ".git", "venv", ".venv", "node_modules", "__pycache__", "build",
    "dist", ".mypy_cache", ".pytest_cache", "lambda_layers", "third_party",
    "customer_logs", "runlogs",
}


class GeneralResourceHandler:
    """Handles app-wide (action, resource) requests outside the skill editor."""

    def __init__(
        self,
        invoke_llm: Callable[..., Awaitable[str]],
        user_name: str = "User",
        get_lang: Optional[Callable[[], str]] = None,
        skip_confirmation: bool = False,
    ):
        self._invoke_llm = invoke_llm
        self._user_name = user_name
        self._get_lang = get_lang or (lambda: "en")
        # When True, write-op proposals are returned ready-to-run without a
        # confirmation gate. Toggled by the client's `/` skip command.
        self._skip_confirmation = skip_confirmation

    def set_skip_confirmation(self, value: bool) -> None:
        self._skip_confirmation = bool(value)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    async def handle(
        self,
        *,
        action: str,
        resource: str,
        message: str,
        session_id: Optional[str],
        on_event: Optional[Callable] = None,
        emit_progress: Optional[Callable[..., Awaitable[None]]] = None,
    ) -> AgentResponse:
        act = self._coerce(action, ActionType, ActionType.NONE)
        res = self._coerce(resource, ResourceType, ResourceType.NONE)

        async def progress(msg: str):
            if emit_progress and on_event:
                try:
                    await emit_progress(on_event, msg)
                except Exception:
                    pass

        try:
            if res in (ResourceType.AGENT, ResourceType.TASK):
                return await self._handle_entity(act, res, message, session_id, progress)
            if res == ResourceType.PROMPT:
                return await self._handle_prompt(act, message, session_id, progress)
            if res == ResourceType.APP_DOCS:
                return await self._answer_from_docs(message, session_id, progress)
            if res == ResourceType.SOURCE:
                return await self._answer_from_source(message, session_id, progress)
        except Exception as e:
            logger.error(f"[GeneralResourceHandler] {act.value}/{res.value} failed: {e}", exc_info=True)
            return self._resp(
                f"I hit an error handling that {res.value} request: {e}",
                resource=res, action=act, session_id=session_id, state="error",
            )

        return self._resp(
            f"I can't act on '{res.value}' yet.",
            resource=res, action=act, session_id=session_id,
        )

    # ------------------------------------------------------------------
    # Agents & Tasks — propose a local `ecan` CLI command (client executes)
    #
    # The cloud agent does NOT touch any DB. It proposes the CLI command the
    # local client runs; the (now sync-capable) CLI applies it locally and
    # propagates to cloud, then the client posts the run result back to the
    # agent for conversation context. Write ops require confirmation unless the
    # session opted out (the `/` skip command).
    # ------------------------------------------------------------------
    # Maps an action to the `ecan` subcommand and whether it mutates.
    _ENTITY_VERB = {
        ActionType.LIST: ("list", False),
        ActionType.QUERY: ("get", False),
        ActionType.CREATE: ("add", True),
        ActionType.MODIFY: ("update", True),
        ActionType.REMOVE: ("remove", True),
    }

    async def _handle_entity(
        self,
        action: ActionType,
        resource: ResourceType,
        message: str,
        session_id: Optional[str],
        progress: Callable[[str], Awaitable[None]],
    ) -> AgentResponse:
        group = "agents" if resource == ResourceType.AGENT else "tasks"
        noun = resource.value
        verb_info = self._ENTITY_VERB.get(action)
        if not verb_info:
            return self._resp(
                f"I understood you want to work with {noun}s, but not what to do "
                f"(create / list / show / update / remove). Could you rephrase?",
                resource=resource, action=action, session_id=session_id,
            )
        verb, is_write = verb_info
        await progress(f"Preparing `{verb}` for {noun}…")

        # --- LIST: no args, no target ---
        if action == ActionType.LIST:
            cmd = f"ecan {group} list"
            return self._propose(cmd, resource, action, message_intro=f"List your {noun}s",
                                  fields={}, target=None, is_write=False, session_id=session_id)

        # --- CREATE: needs a name (+ optional description) ---
        if action == ActionType.CREATE:
            fields = await self._extract_json(
                message,
                f"Extract fields to create a new {noun}. "
                'Return JSON: {"name": <string, required>, "description": <string>}. '
                "If no clear name is present, set name to null.",
            ) or {}
            name = fields.get("name")
            if not name:
                return self._resp(
                    f"What should I name the new {noun}?",
                    resource=resource, action=action, session_id=session_id, state="needs_info",
                )
            args = f"-n {self._q(name)}"
            if fields.get("description"):
                args += f" -d {self._q(fields['description'])}"
            cmd = f"ecan {group} {verb} {args}"
            return self._propose(cmd, resource, action,
                                 message_intro=f"Create {noun} **{name}**",
                                 fields={"name": name, "description": fields.get("description", "")},
                                 target=None, is_write=True, session_id=session_id)

        # --- QUERY / MODIFY / REMOVE: need a target (id-or-name) ---
        target = await self._extract_field(
            message, f"the name or id of the {noun} the user is referring to")
        if not target:
            return self._resp(
                f"Which {noun} do you mean? Tell me its name or id.",
                resource=resource, action=action, session_id=session_id, state="needs_info",
            )

        if action == ActionType.QUERY:
            cmd = f"ecan {group} get {self._q(target)}"
            return self._propose(cmd, resource, action, message_intro=f"Show {noun} **{target}**",
                                 fields={}, target=target, is_write=False, session_id=session_id)

        if action == ActionType.REMOVE:
            cmd = f"ecan {group} remove {self._q(target)}"
            return self._propose(cmd, resource, action, message_intro=f"Remove {noun} **{target}**",
                                 fields={}, target=target, is_write=True, session_id=session_id)

        # MODIFY
        updates = await self._extract_json(
            message,
            f"The user wants to update the {noun} named '{target}'. Extract ONLY the "
            'fields to change as JSON (e.g. {"name": ..., "description": ..., "status": ...}). '
            "Omit unchanged fields.",
        ) or {}
        updates = {k: v for k, v in updates.items() if k not in ("id",) and v is not None}
        if not updates:
            return self._resp(
                f"What would you like to change about **{target}**?",
                resource=resource, action=action, session_id=session_id, state="needs_info",
            )
        flag = {"name": "-n", "description": "-d", "status": "-s", "priority": "-p"}
        args = " ".join(f"{flag.get(k, '--' + k)} {self._q(v)}" for k, v in updates.items())
        cmd = f"ecan {group} update {self._q(target)} {args}"
        return self._propose(cmd, resource, action,
                             message_intro=f"Update {noun} **{target}** ({', '.join(updates)})",
                             fields=updates, target=target, is_write=True, session_id=session_id)

    def _propose(
        self, cmd: str, resource: ResourceType, action: ActionType, *,
        message_intro: str, fields: Dict[str, Any], target: Optional[str],
        is_write: bool, session_id: Optional[str],
    ) -> AgentResponse:
        """Build a proposal response carrying the CLI command for the client to run."""
        needs_confirm = is_write and not self._skip_confirmation
        if needs_confirm:
            body = (f"{message_intro}. Run this locally to apply it (it syncs to cloud "
                    f"automatically):\n```bash\n{cmd}\n```\nConfirm to proceed.")
            state = "awaiting_confirmation"
        else:
            body = f"{message_intro}:\n```bash\n{cmd}\n```"
            state = "proposed"
        meta = {
            "session_id": session_id,
            "state": state,
            "action": action.value,
            "resource": resource.value,
            "cli_command": cmd,
            "requires_confirmation": needs_confirm,
            "proposal": {
                "action": action.value,
                "resource": resource.value,
                "target": target,
                "fields": fields,
            },
        }
        return AgentResponse(message=body, intent=IntentType.RESOURCE_ACTION, metadata=meta)

    @staticmethod
    def _q(value: Any) -> str:
        """Quote a value for safe inclusion in a proposed shell command."""
        s = str(value)
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

    # ------------------------------------------------------------------
    # Prompts — propose a local `ecan prompts` CLI command (file-backed library).
    # Same propose-only model as agents/tasks: the client runs the command.
    # ------------------------------------------------------------------
    async def _handle_prompt(self, action, message, session_id, progress) -> AgentResponse:
        if action not in self._ENTITY_VERB:
            return self._resp(
                "For prompts I can list, show, create, update or remove. Could you rephrase?",
                resource=ResourceType.PROMPT, action=action, session_id=session_id,
            )
        await progress(f"Preparing `{action.value}` for prompts…")

        if action == ActionType.LIST:
            return self._propose("ecan prompts list", ResourceType.PROMPT, action,
                                 message_intro="List prompt templates",
                                 fields={}, target=None, is_write=False, session_id=session_id)

        if action == ActionType.CREATE:
            fields = await self._extract_json(
                message,
                'Extract fields to create a prompt template. Return JSON: '
                '{"name": <string, required>, "content": <string, the prompt text>}. '
                "Set a field to null if it is not present.",
            ) or {}
            name, content = fields.get("name"), fields.get("content")
            if not name:
                return self._resp("What should the prompt be named?", resource=ResourceType.PROMPT,
                                  action=action, session_id=session_id, state="needs_info")
            if not content:
                return self._resp(f"What should the **{name}** prompt contain?",
                                  resource=ResourceType.PROMPT, action=action,
                                  session_id=session_id, state="needs_info")
            cmd = f"ecan prompts add -n {self._q(name)} -c {self._q(content)}"
            return self._propose(cmd, ResourceType.PROMPT, action,
                                 message_intro=f"Create prompt **{name}**",
                                 fields={"name": name, "content": content},
                                 target=None, is_write=True, session_id=session_id)

        # QUERY / MODIFY / REMOVE need a target prompt name.
        target = await self._extract_field(message, "the prompt template name the user means")
        if not target:
            return self._resp("Which prompt do you mean? Tell me its name.",
                              resource=ResourceType.PROMPT, action=action,
                              session_id=session_id, state="needs_info")

        if action == ActionType.QUERY:
            cmd = f"ecan prompts get {self._q(target)}"
            return self._propose(cmd, ResourceType.PROMPT, action,
                                 message_intro=f"Show prompt **{target}**",
                                 fields={}, target=target, is_write=False, session_id=session_id)

        if action == ActionType.REMOVE:
            cmd = f"ecan prompts remove {self._q(target)}"
            return self._propose(cmd, ResourceType.PROMPT, action,
                                 message_intro=f"Remove prompt **{target}**",
                                 fields={}, target=target, is_write=True, session_id=session_id)

        # MODIFY → overwrite the prompt's content
        fields = await self._extract_json(
            message,
            f"The user wants to change the content of the prompt '{target}'. "
            'Return JSON: {"content": <the new prompt text>}.',
        ) or {}
        content = fields.get("content")
        if not content:
            return self._resp(f"What should the new content of **{target}** be?",
                              resource=ResourceType.PROMPT, action=action,
                              session_id=session_id, state="needs_info")
        cmd = f"ecan prompts add -n {self._q(target)} -c {self._q(content)} --overwrite"
        return self._propose(cmd, ResourceType.PROMPT, action,
                             message_intro=f"Update prompt **{target}**",
                             fields={"content": content}, target=target,
                             is_write=True, session_id=session_id)

    # ------------------------------------------------------------------
    # App-wide Q&A — documentation
    # ------------------------------------------------------------------
    async def _answer_from_docs(self, message, session_id, progress) -> AgentResponse:
        await progress("Searching the documentation…")
        context = self._gather_docs(message)
        if not context:
            # No docs matched — fall back to a plain answer.
            context = "(No matching documentation found.)"
        answer = await self._rag_answer(message, context, source_label="product documentation")
        return self._resp(answer, resource=ResourceType.APP_DOCS,
                          action=ActionType.QA, session_id=session_id)

    def _gather_docs(self, query: str, max_files: int = 6, max_chars: int = 12000) -> str:
        root = _repo_root()
        if not root.is_dir():
            return ""
        md_files: List[Path] = []
        for base in (root, root / "docs"):
            if base.is_dir():
                md_files.extend(base.glob("*.md"))
        if (root / "docs").is_dir():
            md_files.extend((root / "docs").rglob("*.md"))
        scored = self._rank_files(md_files, query)
        return self._concat_files(scored[:max_files], max_chars)

    # ------------------------------------------------------------------
    # App-wide Q&A — source code
    # ------------------------------------------------------------------
    async def _answer_from_source(self, message, session_id, progress) -> AgentResponse:
        await progress("Reading the source code…")
        context = self._gather_source(message)
        if not context:
            return self._resp(
                "I couldn't reach the eCan.ai source tree to answer that. Source-level "
                "questions need to run on the server where the repo lives.",
                resource=ResourceType.SOURCE, action=ActionType.QA, session_id=session_id,
                state="unavailable",
            )
        answer = await self._rag_answer(message, context, source_label="eCan.ai source code")
        return self._resp(answer, resource=ResourceType.SOURCE,
                          action=ActionType.QA, session_id=session_id)

    def _gather_source(self, query: str, max_files: int = 5, max_chars: int = 16000) -> str:
        root = _repo_root()
        if not root.is_dir():
            return ""
        py_files: List[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
            for fn in filenames:
                if fn.endswith(".py"):
                    py_files.append(Path(dirpath) / fn)
            if len(py_files) > 4000:  # safety bound on very large trees
                break
        scored = self._rank_files(py_files, query)
        return self._concat_files(scored[:max_files], max_chars)

    # ------------------------------------------------------------------
    # Shared retrieval helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _keywords(query: str) -> List[str]:
        words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", query.lower())
        stop = {"the", "and", "for", "how", "does", "what", "why", "where", "when",
                "with", "this", "that", "which", "are", "can", "you", "app", "code",
                "source", "implement", "implemented", "work", "works", "behavior"}
        return [w for w in dict.fromkeys(words) if w not in stop][:12]

    def _rank_files(self, files: List[Path], query: str) -> List[Path]:
        kws = self._keywords(query)
        if not kws:
            return files[:0]
        scored: List[Tuple[int, Path]] = []
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="ignore").lower()
            except Exception:
                continue
            score = sum(text.count(k) for k in kws)
            # Boost filename matches — the file named after the concept is often the answer.
            name = f.stem.lower()
            score += sum(5 for k in kws if k in name)
            if score > 0:
                scored.append((score, f))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [f for _, f in scored]

    def _concat_files(self, files: List[Path], max_chars: int) -> str:
        root = _repo_root()
        parts: List[str] = []
        budget = max_chars
        per_file = max(2000, max_chars // max(1, len(files))) if files else 0
        for f in files:
            if budget <= 0:
                break
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            chunk = text[:per_file]
            try:
                rel = f.relative_to(root)
            except Exception:
                rel = f
            parts.append(f"### File: {rel}\n```\n{chunk}\n```")
            budget -= len(chunk)
        return "\n\n".join(parts)

    async def _rag_answer(self, question: str, context: str, source_label: str) -> str:
        lang = self._lang_instruction()
        prompt = (
            f"You are an eCan.ai expert assistant. Answer the user's question using the "
            f"{source_label} excerpts below. Cite the relevant file path(s) when you rely "
            f"on them. If the excerpts don't contain the answer, say so plainly rather than "
            f"guessing.\n\n"
            f"=== CONTEXT ({source_label}) ===\n{context}\n=== END CONTEXT ===\n\n"
            f"Question: {json.dumps(question)}\n{lang}"
        )
        try:
            return str(await self._invoke_llm(prompt)).strip()
        except Exception as e:
            logger.error(f"[GeneralResourceHandler] RAG answer failed: {e}")
            return "I had trouble generating an answer just now. Please try again."

    # ------------------------------------------------------------------
    # LLM extraction utilities
    # ------------------------------------------------------------------
    async def _extract_json(self, message: str, instruction: str) -> Optional[Dict[str, Any]]:
        prompt = (
            f"{instruction}\n\nReturn JSON only, no prose, no markdown fences.\n\n"
            f"user_message={json.dumps(message)}"
        )
        try:
            raw = await self._invoke_llm(prompt)
        except Exception as e:
            logger.error(f"[GeneralResourceHandler] extract_json failed: {e}")
            return None
        return self._parse_json(raw)

    async def _extract_field(self, message: str, what: str) -> Optional[str]:
        prompt = (
            f"From the user message, extract {what}. Return JSON only: "
            '{"value": <string or null>}.\n\n'
            f"user_message={json.dumps(message)}"
        )
        try:
            raw = await self._invoke_llm(prompt)
        except Exception:
            return None
        data = self._parse_json(raw) or {}
        val = data.get("value")
        return str(val).strip() if val else None

    @staticmethod
    def _parse_json(text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        t = text.strip()
        if t.startswith("```"):
            t = re.sub(r"^```[a-zA-Z]*\n?", "", t).rstrip("`").strip()
        try:
            return json.loads(t)
        except Exception:
            m = re.search(r"\{.*\}", t, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    return None
        return None

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce(value: Any, enum_cls, default):
        try:
            return enum_cls(str(value).strip().lower())
        except Exception:
            return default

    def _lang_instruction(self) -> str:
        try:
            from .i18n import get_language_instruction
            return get_language_instruction(self._get_lang())
        except Exception:
            return ""

    def _resp(
        self,
        message: str,
        *,
        resource: ResourceType,
        action: ActionType,
        session_id: Optional[str],
        state: str = "idle",
        data: Any = None,
    ) -> AgentResponse:
        intent = IntentType.APP_QA if action == ActionType.QA else IntentType.RESOURCE_ACTION
        meta: Dict[str, Any] = {
            "session_id": session_id,
            "state": state,
            "action": action.value,
            "resource": resource.value,
        }
        if data is not None:
            meta["result"] = data
        return AgentResponse(message=message, intent=intent, metadata=meta)
