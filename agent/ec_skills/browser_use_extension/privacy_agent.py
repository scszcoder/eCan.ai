"""
PrivacyAgent - A privacy-preserving wrapper for browser-use Agent.

This module provides a subclass of browser-use's Agent that intercepts
browser state before it's sent to the LLM, applying privacy filters
to mask or redact sensitive information.

Usage:
    from agent.ec_skills.browser_use_extension.privacy_agent import PrivacyAgent
    from agent.ec_skills.browser_use_extension.privacy import (
        RegexMaskFilter,
        load_privacy_config,
    )
    
    # Create filter with custom config
    config = load_privacy_config("path/to/config.json")
    privacy_filter = RegexMaskFilter(config)
    
    # Create privacy-aware agent
    agent = PrivacyAgent(
        task="Navigate to bank website and check balance",
        llm=my_llm,
        privacy_filter=privacy_filter,
    )
    
    # Run as normal - privacy filtering happens automatically
    result = await agent.run()
"""

import asyncio
import copy
import os
import time
import json
from typing import Any, Callable, Awaitable, Literal

from utils.logger_helper import logger_helper as logger

# ── Hook API (PR 1) ─────────────────────────────────────────────────────
# The dispatcher/types live in sibling modules so plugin authors can import
# from a stable path (`.hooks`) without pulling in PrivacyAgent internals.
from .hook_api import (
    Decision,
    Hook,
    HookContext,
    HookManifest,
    HookResult,
    Stage,
)
from .hook_dispatcher import (
    HookDispatcher,
    MemoryStateStore,
    ScopedToolProxy,
)
from .hook_loader import (
    HookBundleSpec,
    load_bundles,
)

# Import browser-use components
try:
    from browser_use import Agent, BrowserSession, BrowserProfile
    from browser_use.agent.views import (
        AgentStepInfo,
        AgentState,
        AgentStructuredOutput,
        ActionResult,
    )
    from browser_use.browser.views import BrowserStateSummary
    from browser_use.llm.base import BaseChatModel
    from browser_use.tools.service import Tools
    BROWSER_USE_AVAILABLE = True
except Exception:
    BROWSER_USE_AVAILABLE = False
    BrowserSession = BrowserProfile = Tools = object  # type: ignore
    BrowserStateSummary = object  # type: ignore
    ActionResult = object  # type: ignore

# Import privacy components
from .privacy import (
    PrivacyFilter,
    RegexMaskFilter,
    FilterResult,
    PrivacyConfig,
    load_privacy_config,
)

from agent.cloud_api.cloud_api import (
    send_start_long_llm_task_to_cloud,
    register_long_llm_task_waiter,
    cancel_long_llm_task_waiter,
    get_appsync_endpoint,
)


class PrivacyAgent:
    """
    Privacy-preserving wrapper for browser-use Agent.
    
    This class wraps the browser-use Agent and intercepts the browser state
    before it's sent to the LLM, applying privacy filters to mask sensitive data.
    
    Key features:
    - Non-invasive: Uses subclassing, not monkey-patching
    - Configurable: Supports global and per-domain filtering rules
    - Extensible: Can chain multiple filters (regex, LLM-based, etc.)
    - Debuggable: Optionally keeps original data for inspection
    
    Architecture:
    - Overrides _prepare_context() to intercept BrowserStateSummary
    - Applies privacy filter before MessageManager creates LLM messages
    - Stores filter results for debugging/auditing
    """
    
    def __init__(
        self,
        task: str,
        llm: "BaseChatModel | None" = None,
        privacy_filter: PrivacyFilter | None = None,
        privacy_config: PrivacyConfig | None = None,
        privacy_enabled: bool = True,  # Set to False to bypass filtering
        privacy_debug: bool | None = None,
        privacy_step_delay_seconds: float | None = None,
        # Pass through all other Agent parameters
        browser_profile: "BrowserProfile | None" = None,
        browser_session: "BrowserSession | None" = None,
        browser: "BrowserSession | None" = None,
        tools: "Tools | None" = None,
        controller: "Tools | None" = None,
        sensitive_data: dict[str, str | dict[str, str]] | None = None,
        initial_actions: list[dict[str, dict[str, Any]]] | None = None,
        # Callbacks
        register_new_step_callback: Callable | None = None,
        register_done_callback: Callable | None = None,
        register_external_agent_status_raise_error_callback: Callable | None = None,
        register_should_stop_callback: Callable | None = None,
        # Agent settings
        output_model_schema: type | None = None,
        use_vision: bool | Literal['auto'] = True,
        save_conversation_path: str | None = None,
        max_failures: int = 3,
        override_system_message: str | None = None,
        extend_system_message: str | None = None,
        generate_gif: bool | str = False,
        available_file_paths: list[str] | None = None,
        include_attributes: list[str] | None = None,
        max_actions_per_step: int = 3,
        use_thinking: bool = True,
        flash_mode: bool = False,
        demo_mode: bool | None = None,
        max_history_items: int | None = None,
        page_extraction_llm: "BaseChatModel | None" = None,
        use_judge: bool = True,
        ground_truth: str | None = None,
        judge_llm: "BaseChatModel | None" = None,
        injected_agent_state: "AgentState | None" = None,
        source: str | None = None,
        file_system_path: str | None = None,
        task_id: str | None = None,
        calculate_cost: bool = False,
        cloud_llm_enabled: bool | None = None,
        cloud_session: Any | None = None,
        cloud_token: str | None = None,
        cloud_endpoint: str | None = None,
        cloud_acct_site_id: str | None = None,
        cloud_agent_id: str | None = None,
        cloud_skill_id: str | None = None,
        cloud_node_id: str | None = None,
        cloud_system_prompt_id: str | None = None,
        cloud_user_prompt_id: str | None = None,
        cloud_work_type: str | None = None,
        # ── Hook system (PR 2/5/6) ─────────────────────────────────────
        hooks: list[Hook] | None = None,
        hook_bundles: list[Any] | None = None,  # PR 6: external bundle specs
        site_adapter: dict | None = None,
        skill_bundle_path: str | None = None,
        hooks_enabled: bool = False,  # opt-in: auto-register Tier-0 built-ins
        **kwargs,
    ):
        """
        Initialize PrivacyAgent.
        
        Args:
            task: The task description for the agent
            llm: Language model to use
            privacy_filter: Custom privacy filter. If None, creates default RegexMaskFilter
            privacy_config: Privacy configuration. If None, loads from default location
            privacy_enabled: If False, bypasses all privacy filtering (passthrough mode)
            **kwargs: All other arguments passed to browser-use Agent
        """
        if not BROWSER_USE_AVAILABLE:
            raise ImportError(
                "browser-use is not installed. Install it with: pip install browser-use"
            )

        if privacy_debug is None:
            privacy_debug = os.environ.get("EC_PRIVACY_AGENT_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}

        if privacy_step_delay_seconds is None:
            delay_raw = os.environ.get("EC_PRIVACY_AGENT_STEP_DELAY_SECONDS", "").strip()
            if delay_raw:
                try:
                    privacy_step_delay_seconds = float(delay_raw)
                except Exception:
                    privacy_step_delay_seconds = None

        self.privacy_debug = bool(privacy_debug)
        self.privacy_step_delay_seconds = privacy_step_delay_seconds

        if cloud_llm_enabled is None:
            cloud_llm_enabled = os.environ.get("EC_BROWSER_USE_CLOUD_LLM", "").strip().lower() in {"1", "true", "yes", "on"}

        self.cloud_llm_enabled = bool(cloud_llm_enabled)
        self.cloud_session = cloud_session
        self.cloud_token = cloud_token
        self.cloud_endpoint = cloud_endpoint
        self.cloud_acct_site_id = cloud_acct_site_id
        self.cloud_agent_id = cloud_agent_id
        self.cloud_skill_id = cloud_skill_id
        self.cloud_node_id = cloud_node_id
        self.cloud_system_prompt_id = cloud_system_prompt_id
        self.cloud_user_prompt_id = cloud_user_prompt_id
        self.cloud_work_type = cloud_work_type or "browser_use_next_action"
        
        # Privacy enabled flag - can be toggled at runtime
        self.privacy_enabled = privacy_enabled
        
        # Initialize privacy filter (even if disabled, for later use)
        if privacy_filter is not None:
            self.privacy_filter = privacy_filter
        else:
            config = privacy_config or load_privacy_config()
            self.privacy_filter = RegexMaskFilter(config)
        
        # Store filter results for debugging
        self._filter_results: list[FilterResult] = []
        
        # Create the underlying Agent
        self._agent = Agent(
            task=task,
            llm=llm,
            browser_profile=browser_profile,
            browser_session=browser_session,
            browser=browser,
            tools=tools,
            controller=controller,
            sensitive_data=sensitive_data,
            initial_actions=initial_actions,
            register_new_step_callback=register_new_step_callback,
            register_done_callback=register_done_callback,
            register_external_agent_status_raise_error_callback=register_external_agent_status_raise_error_callback,
            register_should_stop_callback=register_should_stop_callback,
            output_model_schema=output_model_schema,
            use_vision=use_vision,
            save_conversation_path=save_conversation_path,
            max_failures=max_failures,
            override_system_message=override_system_message,
            extend_system_message=extend_system_message,
            generate_gif=generate_gif,
            available_file_paths=available_file_paths,
            include_attributes=include_attributes,
            max_actions_per_step=max_actions_per_step,
            use_thinking=use_thinking,
            flash_mode=flash_mode,
            demo_mode=demo_mode,
            max_history_items=max_history_items,
            page_extraction_llm=page_extraction_llm,
            use_judge=use_judge,
            ground_truth=ground_truth,
            judge_llm=judge_llm,
            injected_agent_state=injected_agent_state,
            source=source,
            file_system_path=file_system_path,
            task_id=task_id,
            calculate_cost=calculate_cost,
            **kwargs,
        )
        
        # Patch the agent's _prepare_context method
        self._original_prepare_context = self._agent._prepare_context
        self._agent._prepare_context = self._privacy_prepare_context

        self._original_get_next_action = self._agent._get_next_action
        if self.cloud_llm_enabled:
            self._agent._get_next_action = self._cloud_get_next_action

        # ── Hook system plumbing (PR 2) ─────────────────────────────────
        # A dispatcher is always instantiated so downstream code doesn't
        # need to null-check.  With zero hooks registered it is a no-op on
        # every stage (dispatch returns CONTINUE without invoking anything).
        self._site_adapter: dict = dict(site_adapter or {})
        self._skill_bundle_path: str | None = skill_bundle_path
        self._hook_dispatcher: HookDispatcher = HookDispatcher(
            site_adapter=self._site_adapter,
            trace_id=task_id,
        )
        # Per-hook MemoryStateStore cache (one store per hook name).
        self._hook_state_stores: dict[str, MemoryStateStore] = {}
        # Monotonic span counter for tracing.
        self._hook_span_seq: int = 0

        # Register user-supplied hooks (Tier 1/2).
        for _h in (hooks or []):
            try:
                self._hook_dispatcher.register(_h)
            except Exception as _reg_err:
                logger.error(
                    f"[PrivacyAgent] Failed to register hook "
                    f"{getattr(getattr(_h, 'manifest', None), 'name', type(_h).__name__)!r}: "
                    f"{_reg_err}"
                )

        # ── External hook bundles (PR 6) ────────────────────────────────
        # ``hook_bundles`` is a list of (str | dict | HookBundleSpec) —
        # each entry describes one bundle directory (or pkg:) to load.
        # Loader failures are isolated per bundle and logged; they do NOT
        # abort agent construction.  An empty/None list is a no-op.
        self._hook_bundles_raw: list[Any] = list(hook_bundles or [])
        if self._hook_bundles_raw:
            try:
                _bundle_hooks = load_bundles(self._hook_bundles_raw, fail_fast=False)
            except Exception as _bundle_err:
                logger.error(
                    f"[PrivacyAgent] hook_bundles load failed: {_bundle_err}",
                    exc_info=True,
                )
                _bundle_hooks = []
            for _h in _bundle_hooks:
                try:
                    # Bundle hooks are Tier>=1; the dispatcher enforces
                    # Tier-0 comes only from the in-tree allowlist.
                    self._hook_dispatcher.register(_h)
                except Exception as _reg_err:
                    logger.error(
                        f"[PrivacyAgent] Bundle hook "
                        f"{getattr(getattr(_h, 'manifest', None), 'name', type(_h).__name__)!r} "
                        f"failed to register: {_reg_err}",
                        exc_info=True,
                    )

        # ── Tier-0 built-in hooks (PR 5) ────────────────────────────────
        # Opt-in via ``hooks_enabled=True``.  When enabled, the agent auto-
        # registers the crosstalk guard + typing lock hooks that replace the
        # inline HOT-PATH-B safety logic in build_node.py.  Legacy callers
        # (default) get identical behavior to PR 2 — dispatcher present but
        # no hooks registered → every stage is a no-op.
        self._hooks_enabled: bool = bool(hooks_enabled)
        if self._hooks_enabled:
            try:
                self._register_builtin_hooks()
            except Exception as _builtin_err:
                logger.error(
                    f"[PrivacyAgent] Failed to auto-register built-in hooks "
                    f"(continuing without them): {_builtin_err}",
                    exc_info=True,
                )

        # Patch step + multi_act so every stage has an insertion point.
        # These patches are no-ops when no hooks are registered.
        self._original_step = self._agent.step
        self._agent.step = self._hooked_step
        self._original_multi_act = self._agent.multi_act
        self._agent.multi_act = self._hooked_multi_act
        
        status = "enabled" if self.privacy_enabled else "DISABLED (passthrough mode)"
        debug_status = "debug=on" if self.privacy_debug else "debug=off"
        delay_status = (
            f"step_delay={self.privacy_step_delay_seconds}s"
            if (self.privacy_step_delay_seconds is not None and self.privacy_step_delay_seconds > 0)
            else "step_delay=off"
        )
        logger.info(f"[PrivacyAgent] Initialized with privacy filtering {status} ({debug_status}, {delay_status})")

        if self.cloud_llm_enabled:
            logger.info("[PrivacyAgent] Cloud LLM mode enabled")
    
    async def _privacy_prepare_context(
        self, 
        step_info: "AgentStepInfo | None" = None
    ) -> "BrowserStateSummary":
        """
        Intercept _prepare_context to apply privacy filtering.
        
        This method:
        1. Calls the original _prepare_context to get browser state
        2. Applies privacy filter to the browser state
        3. Updates the message manager with filtered state
        4. Returns the filtered state
        """
        t0 = time.perf_counter()
        if self.privacy_debug:
            logger.debug(
                f"[PrivacyAgent] _prepare_context start "
                f"(step_info={type(step_info).__name__ if step_info is not None else None})"
            )

        # Call original to get browser state and create messages
        browser_state_summary = await self._original_prepare_context(step_info)
        t_original = time.perf_counter()
        
        # Skip filtering if disabled
        if not self.privacy_enabled:
            if self.privacy_debug:
                logger.debug(
                    f"[PrivacyAgent] _prepare_context passthrough (privacy_enabled=False) "
                    f"elapsed={t_original - t0:.3f}s"
                )
            return browser_state_summary

        # Apply privacy filter
        url = browser_state_summary.url if browser_state_summary else ""
        if self.privacy_debug:
            logger.debug(
                f"[PrivacyAgent] Filtering browser state "
                f"url={url!r} "
                f"original_elapsed={t_original - t0:.3f}s"
            )
        filter_result = self.privacy_filter.filter_browser_state(
            browser_state_summary, url
        )
        t_filtered = time.perf_counter()

        # Store result for debugging
        self._filter_results.append(filter_result)

        if filter_result.was_filtered:
            # Get the filtered state
            filtered_state = filter_result.filtered_data

            # Re-create state messages with filtered data
            # This replaces the messages created by the original _prepare_context
            self._rebuild_state_messages_with_compacted_result(filtered_state, step_info)

            if self.privacy_debug:
                logger.debug(
                    f"[PrivacyAgent] Rebuilt state messages "
                    f"elapsed_filter={t_filtered - t_original:.3f}s "
                    f"elapsed_total={time.perf_counter() - t0:.3f}s"
                )

            logger.debug(
                f"[PrivacyAgent] Applied privacy filter, "
                f"redacted {sum(filter_result.stats.values())} items"
            )

            return filtered_state

        # Even when no privacy redaction happened, rebuild with compacted last_result
        # so historical context uses summaries instead of raw long outputs.
        self._rebuild_state_messages_with_compacted_result(browser_state_summary, step_info)

        if self.privacy_debug:
            logger.debug(
                f"[PrivacyAgent] No filtering applied "
                f"elapsed_filter={t_filtered - t_original:.3f}s "
                f"elapsed_total={time.perf_counter() - t0:.3f}s"
            )

        if self.privacy_step_delay_seconds is not None and self.privacy_step_delay_seconds > 0:
            if self.privacy_debug:
                logger.debug(f"[PrivacyAgent] Step delay sleep={self.privacy_step_delay_seconds}s")
            await asyncio.sleep(self.privacy_step_delay_seconds)

        return browser_state_summary

    def _truncate_text(self, text: Any, max_len: int) -> str:
        try:
            s = "" if text is None else str(text)
        except Exception:
            return ""
        if max_len <= 0:
            return ""
        if len(s) <= max_len:
            return s
        return s[:max_len]

    def _rebuild_state_messages_with_compacted_result(self, browser_state_summary: Any, step_info: Any) -> None:
        page_filtered_actions = None
        try:
            registry = getattr(getattr(self._agent, "tools", None), "registry", None)
            if registry and hasattr(registry, "get_prompt_description"):
                url = getattr(browser_state_summary, "url", "") if browser_state_summary else ""
                page_filtered_actions = registry.get_prompt_description(url) or None
        except Exception:
            page_filtered_actions = None

        self._agent._message_manager.create_state_messages(
            browser_state_summary=browser_state_summary,
            model_output=self._agent.state.last_model_output,
            result=self._get_compacted_last_result_for_memory(),
            step_info=step_info,
            use_vision=self._agent.settings.use_vision,
            page_filtered_actions=page_filtered_actions,
            sensitive_data=self._agent.sensitive_data,
            available_file_paths=self._agent.available_file_paths,
        )

    def _summarize_action_result_for_memory(self, result: Any) -> Any:
        if not BROWSER_USE_AVAILABLE:
            return result
        try:
            error_text = self._truncate_text(getattr(result, "error", ""), 240)
            extracted = self._truncate_text(getattr(result, "extracted_content", ""), 240)
            long_term = self._truncate_text(getattr(result, "long_term_memory", ""), 240)
            is_done = bool(getattr(result, "is_done", False))

            summary_parts: list[str] = []
            if is_done:
                summary_parts.append("done")
            if error_text:
                summary_parts.append(f"error={error_text}")
            elif long_term:
                summary_parts.append(long_term)
            elif extracted:
                summary_parts.append(extracted)
            else:
                summary_parts.append("action completed")

            summary_text = "; ".join(p for p in summary_parts if p).strip()
            return ActionResult(
                is_done=is_done,
                error=error_text or None,
                extracted_content=None,
                include_in_memory=True,
                long_term_memory=summary_text or None,
            )
        except Exception:
            return result

    def _get_compacted_last_result_for_memory(self) -> Any:
        last_result = getattr(self._agent.state, "last_result", None)
        if not last_result:
            return last_result
        try:
            return [self._summarize_action_result_for_memory(item) for item in last_result]
        except Exception:
            return last_result

    def _compact_selector_map(self, selector_map: Any, *, max_elems: int = 250) -> list[dict[str, Any]]:
        try:
            items = []
            if isinstance(selector_map, dict):
                iterable = list(selector_map.items())
            else:
                return []

            for k, v in iterable[:max_elems]:
                if hasattr(v, "model_dump"):
                    d = v.model_dump()
                elif hasattr(v, "dict"):
                    d = v.dict()
                elif hasattr(v, "__dict__"):
                    d = dict(v.__dict__)
                else:
                    d = {"value": str(v)}

                attrs = d.get("attributes")
                if isinstance(attrs, dict):
                    keep = {}
                    for kk in ("id", "name", "type", "role", "href", "placeholder", "aria-label", "aria_label", "value"):
                        if kk in attrs and attrs.get(kk) is not None:
                            keep[kk] = self._truncate_text(attrs.get(kk), 120)
                    d["attributes"] = keep

                if "text" in d:
                    d["text"] = self._truncate_text(d.get("text"), 200)
                if "xpath" in d:
                    d["xpath"] = self._truncate_text(d.get("xpath"), 400)
                if "css_selector" in d:
                    d["css_selector"] = self._truncate_text(d.get("css_selector"), 400)
                if "selector" in d:
                    d["selector"] = self._truncate_text(d.get("selector"), 400)

                items.append({"i": k, "e": d})
            return items
        except Exception:
            logger.error("[PrivacyAgent] Failed to compact selector_map", exc_info=True)
            return []

    def _build_compact_dom_payload(self, browser_state_summary: Any) -> dict[str, Any]:
        url = getattr(browser_state_summary, "url", None)
        title = getattr(browser_state_summary, "title", None)
        dom_state = getattr(browser_state_summary, "dom_state", None)
        selector_map = getattr(dom_state, "selector_map", None)
        return {
            "url": self._truncate_text(url, 1024),
            "title": self._truncate_text(title, 256),
            "selector_map": self._compact_selector_map(selector_map),
        }

    def _parse_structured_output(self, payload: Any) -> "AgentStructuredOutput":
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {"raw": payload}

        if hasattr(AgentStructuredOutput, "model_validate"):
            return AgentStructuredOutput.model_validate(payload)
        if hasattr(AgentStructuredOutput, "parse_obj"):
            return AgentStructuredOutput.parse_obj(payload)
        return AgentStructuredOutput(**payload)

    async def _cloud_get_next_action(self, *args, **kwargs) -> "AgentStructuredOutput":
        browser_state_summary = None
        if args:
            browser_state_summary = args[0]
        if browser_state_summary is None:
            browser_state_summary = kwargs.get("browser_state_summary")

        if not self.cloud_session or not self.cloud_token:
            raise ValueError("Cloud LLM mode enabled but cloud_session/cloud_token not provided")

        acct_site_id = self.cloud_acct_site_id
        agent_id = self.cloud_agent_id
        if not acct_site_id or not agent_id:
            raise ValueError("Cloud LLM mode enabled but cloud_acct_site_id/cloud_agent_id not provided")

        endpoint = self.cloud_endpoint or get_appsync_endpoint()
        step_number = int(getattr(getattr(self._agent, "state", None), "n_steps", 0) or 0)
        dom_payload = self._build_compact_dom_payload(browser_state_summary)

        task_data = {
            "skill_id": self.cloud_skill_id,
            "node_id": self.cloud_node_id,
            "system_prompt_id": self.cloud_system_prompt_id,
            "user_prompt_id": self.cloud_user_prompt_id,
            "step_number": step_number,
            "dom": dom_payload,
        }
        task_input = {
            "acct_site_id": acct_site_id,
            "agent_id": agent_id,
            "work_type": self.cloud_work_type,
            "task_data": task_data,
        }

        loop = asyncio.get_running_loop()
        start_resp = await loop.run_in_executor(
            None,
            lambda: send_start_long_llm_task_to_cloud(self.cloud_session, self.cloud_token, task_input, endpoint),
        )

        if isinstance(start_resp, dict) and start_resp.get("errors"):
            raise RuntimeError(f"Cloud startLongLLMTask error: {start_resp.get('errors')}")

        body = start_resp.get("body") if isinstance(start_resp, dict) else None
        if body is None:
            body = start_resp

        task_id = None
        if isinstance(body, dict):
            task_id = body.get("id") or body.get("taskID") or body.get("task_id")
        if not task_id:
            raise RuntimeError(f"Cloud startLongLLMTask missing task id: {start_resp}")

        fut: asyncio.Future = loop.create_future()
        register_long_llm_task_waiter(task_id, loop, fut)

        try:
            timeout_raw = os.environ.get("EC_BROWSER_USE_CLOUD_LLM_TIMEOUT_SECONDS", "").strip()
            timeout_seconds = float(timeout_raw) if timeout_raw else None
        except Exception:
            timeout_seconds = None

        try:
            if timeout_seconds is None:
                timeout_seconds = 120.0
            result_obj = await asyncio.wait_for(fut, timeout=timeout_seconds)
        finally:
            if not fut.done():
                cancel_long_llm_task_waiter(task_id)

        status = (result_obj or {}).get("status")
        if status and str(status).lower() not in {"success", "ok", "completed"}:
            raise RuntimeError(f"Cloud LLM task failed status={status} task_id={task_id} result={result_obj}")

        results = (result_obj or {}).get("results")
        if isinstance(results, str):
            try:
                results = json.loads(results)
            except Exception:
                results = {"raw": results}

        candidate = results
        if isinstance(results, dict):
            candidate = (
                results.get("completion")
                or results.get("model_output")
                or results.get("agent_output")
                or results.get("output")
                or results
            )

        return self._parse_structured_output(candidate)
    
    async def run(self, max_steps: int = 100, cancellation_event=None) -> Any:
        """
        Run the agent with privacy filtering.
        
        Args:
            max_steps: Maximum number of steps to run
            cancellation_event: Optional threading.Event for cooperative cancellation
            
        Returns:
            Agent result (AgentHistoryList)
        """
        # Forward cancellation_event only if the inner Agent.run supports it.
        # Vanilla browser_use.Agent.run() lacks the kwarg; passing it blindly
        # raises TypeError.
        kwargs: dict[str, Any] = {"max_steps": max_steps}
        if cancellation_event is not None:
            try:
                import inspect as _inspect
                _sig = _inspect.signature(self._agent.run)
                if "cancellation_event" in _sig.parameters or any(
                    p.kind == _inspect.Parameter.VAR_KEYWORD
                    for p in _sig.parameters.values()
                ):
                    kwargs["cancellation_event"] = cancellation_event
            except (TypeError, ValueError):
                # Signature inspection failed — safest to omit the kwarg.
                pass
        return await self._agent.run(**kwargs)
    
    def get_filter_results(self) -> list[FilterResult]:
        """
        Get all filter results from the current session.
        
        Useful for debugging and auditing what was filtered.
        
        Returns:
            List of FilterResult objects
        """
        return self._filter_results
    
    def get_filter_stats(self) -> dict[str, int]:
        """
        Get aggregated filter statistics.
        
        Returns:
            Dict of pattern name to total count of redactions
        """
        total_stats: dict[str, int] = {}
        for result in self._filter_results:
            for key, value in result.stats.items():
                total_stats[key] = total_stats.get(key, 0) + value
        return total_stats
    
    def clear_filter_results(self) -> None:
        """Clear stored filter results."""
        self._filter_results.clear()
    
    # ==================== Hook system public API (PR 2) ====================

    def register_hook(self, hook: Hook) -> None:
        """Register a hook at runtime.  Third-party hooks (Tier 1/2) only.

        Tier-0 hooks are registered by the app's own code paths and rejected
        when attempted from foreign packages (enforced structurally by
        ``HookDispatcher.register``).
        """
        self._hook_dispatcher.register(hook)

    def unregister_hook(self, name: str) -> bool:
        """Remove a previously registered non-Tier-0 hook by name."""
        return self._hook_dispatcher.unregister(name)

    def list_hooks(self, stage: Stage | None = None) -> list[HookManifest]:
        """Return manifests of currently registered hooks (in dispatch order)."""
        return self._hook_dispatcher.list_hooks(stage)

    async def shutdown_hooks(self) -> None:
        """Best-effort teardown for hooks that hold external resources.

        Primarily exists for the subprocess runtime lane (PR 9), which
        keeps a long-lived child process per hook.  Idempotent; safe to
        call multiple times.  Callers that construct a PrivacyAgent for
        a one-shot run should invoke this before the event loop closes.
        """
        for mf in self._hook_dispatcher.list_hooks():
            hook = self._hook_dispatcher.get_hook(mf.name)
            sd = getattr(hook, "shutdown", None) if hook is not None else None
            if sd is None:
                continue
            try:
                result = sd()
                if hasattr(result, "__await__"):
                    await result
            except Exception as e:
                logger.warning(
                    f"[PrivacyAgent] hook {mf.name!r} shutdown raised: {e!r}"
                )

    @property
    def hook_dispatcher(self) -> HookDispatcher:
        """The per-agent HookDispatcher.  Exposed for diagnostics/tests."""
        return self._hook_dispatcher

    @property
    def hooks_enabled(self) -> bool:
        """True when the opt-in built-in hook bundle has been registered."""
        return self._hooks_enabled

    # -------- Tier-0 built-in registration (PR 5) -----------------------

    # Class-level list of built-in factory callables.  Each callable must
    # take no args and return a ready-to-register Hook instance.  Kept as a
    # method-local list rather than a module-level constant so importing
    # privacy_agent doesn't eagerly import the hooks subpackage when the
    # opt-in is off — keeps legacy paths lean.
    def _register_builtin_hooks(self) -> None:
        """Register the Tier-0 built-in hooks that replace the inline
        HOT-PATH-B safety logic in build_node.py.

        Current bundle:
          * VerifyActiveSessionHook   — on_pre_action, crosstalk guard
          * TypingLockAcquireHook     — on_pre_action, typing serialization
          * TypingLockReleaseHook     — on_post_action, typing serialization

        BypassActionsHook is NOT registered here because it fires at
        ``on_event_normalized`` which is not triggered by the Agent loop
        (it belongs to build_node.py's event-dispatch path — future PR).
        """
        # Lazy imports so module load stays lean for non-opted-in callers.
        from .hooks.builtin.verify_active_session import VerifyActiveSessionHook
        from .hooks.builtin.typing_lock import (
            TypingLockAcquireHook,
            TypingLockReleaseHook,
        )

        builtins: list[Hook] = [
            VerifyActiveSessionHook(),
            TypingLockAcquireHook(),
            TypingLockReleaseHook(),
        ]
        registered: list[str] = []
        for h in builtins:
            try:
                # allow_tier0=True because privacy_agent.py lives under the
                # Tier-0 allowlist prefix, but being explicit is safer than
                # relying on stack-frame introspection across Python versions.
                self._hook_dispatcher.register(h, allow_tier0=True)
                registered.append(h.manifest.name)
            except Exception as _reg_err:
                logger.error(
                    f"[PrivacyAgent] Tier-0 hook {h.manifest.name!r} failed "
                    f"to register: {_reg_err}",
                    exc_info=True,
                )
        logger.info(
            f"[PrivacyAgent] Tier-0 built-ins registered: {registered}"
        )

    # -------- internal: hook context + tool proxy construction ----------

    async def _raw_hook_tool_call(self, name: str, /, **args: Any) -> Any:
        """Backend for ScopedToolProxy — dispatches via the Agent's Tools
        registry the same way ``multi_act`` does.  Permission gating is
        applied by the ScopedToolProxy before this is reached.
        """
        try:
            from browser_use.tools.registry.views import ActionModel  # type: ignore
        except Exception as _imp_err:
            raise RuntimeError(
                f"browser-use ActionModel unavailable: {_imp_err}"
            )
        if not self._agent.tools:
            raise RuntimeError("Agent has no Tools registry bound")
        # Build a one-off ActionModel with the single named field populated.
        # This mirrors how browser-use itself wraps LLM-chosen actions.
        try:
            action = ActionModel(**{name: args})  # type: ignore[arg-type]
        except Exception as _build_err:
            raise RuntimeError(
                f"Failed to build ActionModel for tool {name!r}: {_build_err}"
            )
        return await self._agent.tools.act(
            action=action,
            browser_session=self._agent.browser_session,
            file_system=getattr(self._agent, "file_system", None),
            page_extraction_llm=self._agent.settings.page_extraction_llm,
            sensitive_data=self._agent.sensitive_data,
            available_file_paths=self._agent.available_file_paths,
            extraction_schema=getattr(self._agent, "extraction_schema", None),
        )

    def _get_or_create_state_store(
        self, hook_name: str, *, namespace: str = ""
    ) -> MemoryStateStore:
        """Return a (shared or hook-local) state store.

        Hooks whose manifest sets ``state_namespace="foo"`` all receive the
        SAME store, keyed by ``ns:foo``.  Hooks without a namespace get
        their own store keyed by their name.  This lets paired hooks like
        ``typing_lock_acquire`` + ``typing_lock_release`` cooperate while
        keeping unrelated hooks isolated.
        """
        key = f"ns:{namespace}" if namespace else hook_name
        store = self._hook_state_stores.get(key)
        if store is None:
            # NOTE: manifest.state == "disk" is honored in a later PR alongside
            # the skill-bundle loader; for now all hooks get memory stores.
            store = MemoryStateStore()
            self._hook_state_stores[key] = store
        return store

    def _next_span_id(self) -> str:
        self._hook_span_seq += 1
        return f"{self._hook_dispatcher.trace_id[:8]}-{self._hook_span_seq:06d}"

    def _build_hook_context(self, manifest: HookManifest) -> HookContext:
        """Factory passed to ``HookDispatcher.dispatch``.  Builds a scoped
        ToolProxy + StateStore on every call; these are cheap.
        """
        agent_self = self

        class _Ctx:
            pass

        ctx = _Ctx()
        ctx.manifest = manifest
        ctx.trace_id = agent_self._hook_dispatcher.trace_id
        ctx.span_id = agent_self._next_span_id()
        ctx.step = int(getattr(getattr(agent_self._agent, "state", None), "n_steps", 0) or 0)
        ctx.site_adapter = agent_self._site_adapter
        ctx.tools = ScopedToolProxy(
            raw_call=agent_self._raw_hook_tool_call,
            allowed_globs=tuple(manifest.permissions.tools or ()),
            hook_name=manifest.name,
        )
        ctx.state = agent_self._get_or_create_state_store(
            manifest.name, namespace=manifest.state_namespace,
        )
        ctx.logger = logger
        ctx.config = dict(manifest.matches.get("config", {}) or {})
        # Raw BrowserSession handle — None in non-browser test contexts.
        # Hooks that need DOM access import helpers from
        # extension_tools_service (e.g. _evaluate_js) and pass this through.
        ctx.browser_session = getattr(agent_self._agent, "browser_session", None)
        ctx.emit_span = lambda *_a, **_k: None
        return ctx  # type: ignore[return-value]

    async def _dispatch_stage(self, stage: Stage, payload: Any) -> HookResult:
        """Thin wrapper so call-sites don't need the ctx_factory boilerplate."""
        try:
            return await self._hook_dispatcher.dispatch(
                stage, payload, ctx_factory=self._build_hook_context,
            )
        except Exception as _disp_err:
            # Dispatcher-level failures must never crash the agent loop.
            logger.exception(
                f"[PrivacyAgent] hook dispatcher failed at stage={stage.value}: "
                f"{_disp_err}"
            )
            return HookResult.cont(reason=f"dispatcher_error:{type(_disp_err).__name__}")

    # -------- patched Agent methods (hook insertion points) -------------

    async def _hooked_step(self, step_info: "AgentStepInfo | None" = None) -> None:
        """Wraps Agent.step to fire on_pre_step / on_step_end / on_error.

        Behavior with no hooks registered: identical to the original step().
        With hooks registered, a pre-step hook may DROP to skip the step; all
        other decisions at this stage degrade to CONTINUE in PR 2 (BYPASS /
        HANDOFF / ESCALATE from on_pre_step will arrive when the Agent-
        internal patches for them land in a later PR).
        """
        # on_pre_step
        pre = await self._dispatch_stage(Stage.ON_PRE_STEP, {"step_info": step_info})
        if pre.decision == Decision.DROP:
            logger.info(
                f"[PrivacyAgent] on_pre_step DROP — skipping step "
                f"(reason={pre.reason!r})"
            )
            return
        if pre.decision in (Decision.BYPASS, Decision.HANDOFF):
            logger.warning(
                f"[PrivacyAgent] on_pre_step decision {pre.decision.value!r} "
                f"not yet implemented at step-level; falling through to normal "
                f"step execution"
            )

        error: Exception | None = None
        try:
            await self._original_step(step_info)
        except Exception as _step_err:
            error = _step_err
            # Fire on_error but preserve original exception semantics by
            # re-raising after dispatch (unless the hook explicitly DROPs).
            err_res = await self._dispatch_stage(
                Stage.ON_ERROR,
                {"error_type": type(_step_err).__name__, "error": str(_step_err)},
            )
            if err_res.decision != Decision.DROP:
                raise
            logger.info(
                f"[PrivacyAgent] on_error DROP — suppressing step exception "
                f"{type(_step_err).__name__}: {_step_err}"
            )

        # on_step_end (informational in PR 2 — decision ignored)
        await self._dispatch_stage(
            Stage.ON_STEP_END,
            {
                "n_steps": int(getattr(self._agent.state, "n_steps", 0) or 0),
                "had_error": error is not None,
            },
        )

    async def _hooked_multi_act(self, actions: list) -> list:
        """Wraps Agent.multi_act to fire on_pre_action / on_post_action per
        action in the queue.  Preserves multi_act's built-in page-change
        guards by delegating to the original one action at a time.

        Supported decisions in PR 2:
          * on_pre_action  → Continue (default), Drop (skip this action)
          * on_post_action → Continue (default), Replace (swap the ActionResult)

        Bypass/Handoff/Escalate at action level will be added when HOT-PATH-B
        is rehomed in PR 4; for now they log and fall through.
        """
        if not actions:
            return await self._original_multi_act(actions)

        # Fast path: no pre/post-action hooks registered → delegate wholesale
        # so multi_act's internal page-change guards behave identically.
        has_pre = bool(self._hook_dispatcher.list_hooks(Stage.ON_PRE_ACTION))
        has_post = bool(self._hook_dispatcher.list_hooks(Stage.ON_POST_ACTION))
        if not has_pre and not has_post:
            return await self._original_multi_act(actions)

        # Slow path: run actions one-at-a-time to allow per-action hook
        # evaluation.  This changes multi_act's batch semantics slightly
        # (each call is its own batch of size 1), but preserves the
        # page-change guards per action.  Kept opt-in via hook presence.
        results: list = []
        for a in actions:
            try:
                action_name = next(iter(a.model_dump(exclude_unset=True).keys()))
            except Exception:
                action_name = "unknown"
            pre = await self._dispatch_stage(
                Stage.ON_PRE_ACTION, {"action_name": action_name, "action": a},
            )
            if pre.decision == Decision.DROP:
                logger.info(
                    f"[PrivacyAgent] on_pre_action DROP — skipping {action_name!r} "
                    f"(reason={pre.reason!r})"
                )
                continue
            if pre.decision in (Decision.BYPASS, Decision.HANDOFF, Decision.ESCALATE):
                logger.warning(
                    f"[PrivacyAgent] on_pre_action decision {pre.decision.value!r} "
                    f"on {action_name!r} not yet implemented at action-level; "
                    f"falling through to normal execution"
                )

            single_result = await self._original_multi_act([a])
            # Post-action hook: may Replace the ActionResult list.
            # Include ``action`` so hooks can inspect the same args they saw
            # at on_pre_action (e.g. TypingLockReleaseHook needs the
            # customer_name to decide whether to release the shared lock).
            post = await self._dispatch_stage(
                Stage.ON_POST_ACTION,
                {"action_name": action_name, "action": a, "result": single_result},
            )
            # The dispatcher collapses trailing Replace into Continue-with-
            # updated-payload, so inspect the payload shape rather than the
            # decision verb to decide whether to honor a replacement.
            if isinstance(post.payload, dict):
                replaced = post.payload.get("result")
                if isinstance(replaced, list):
                    single_result = replaced
            results.extend(single_result)

            # Honor multi_act's "done/error aborts the rest" semantics.
            if single_result and (
                getattr(single_result[-1], "is_done", False)
                or getattr(single_result[-1], "error", None)
            ):
                break
        return results

    # Proxy commonly used Agent properties and methods
    
    @property
    def task(self) -> str:
        return self._agent.task

    @task.setter
    def task(self, value: str) -> None:
        # Forward to the inner Agent so loop-mode round resets (which
        # reassign ``agent.task`` between iterations) work transparently.
        self._agent.task = value

    @property
    def state(self) -> "AgentState":
        return self._agent.state
    
    @property
    def history(self):
        return self._agent.history
    
    @property
    def browser_session(self) -> "BrowserSession | None":
        return self._agent.browser_session
    
    @property
    def browser_profile(self) -> "BrowserProfile":
        return self._agent.browser_profile
    
    def pause(self) -> None:
        """Pause the agent."""
        self._agent.pause()
    
    def resume(self) -> None:
        """Resume the agent."""
        self._agent.resume()
    
    def stop(self) -> None:
        """Stop the agent."""
        self._agent.stop()
    
    # ==================== Single-Step Execution ====================
    
    async def take_step(self, step_info: "AgentStepInfo | None" = None) -> tuple[bool, bool]:
        """
        Execute a single step of the workflow.
        
        This is the simplest way to run the agent step-by-step.
        Privacy filtering is automatically applied via the patched _prepare_context.
        
        Args:
            step_info: Optional step info. If None, uses current step count.
            
        Returns:
            Tuple[bool, bool]: (is_done, is_valid)
                - is_done: True if the task is complete
                - is_valid: True if the step executed successfully
        """
        return await self._agent.take_step(step_info)
    
    async def step(self, step_info: "AgentStepInfo | None" = None) -> None:
        """
        Execute one step of the task (lower-level than take_step).
        
        This directly calls the agent's step method without the
        initial actions and done callback handling that take_step provides.
        
        Args:
            step_info: Optional step info for this step.
        """
        await self._agent.step(step_info)
    
    async def initialize_for_stepping(self) -> None:
        """
        Initialize the browser session for step-by-step execution.
        
        Call this before using take_step() or step() in a manual loop.
        This starts the browser and executes any initial actions.
        
        Usage:
            agent = PrivacyAgent(task=..., llm=...)
            await agent.initialize_for_stepping()
            
            for step_num in range(max_steps):
                is_done, _ = await agent.take_step()
                if is_done:
                    break
                # Inspect state, pause for user input, etc.
        """
        # Start browser session
        await self._agent.browser_session.start()
        
        # Execute initial actions if any
        if self._agent.initial_actions:
            await self._agent._execute_initial_actions()
    
    async def run_with_step_callback(
        self,
        max_steps: int = 100,
        on_step_start: "Callable[['PrivacyAgent'], Awaitable[None]] | None" = None,
        on_step_end: "Callable[['PrivacyAgent'], Awaitable[None]] | None" = None,
    ) -> Any:
        """
        Run the agent with callbacks before/after each step.
        
        This allows inspection and control at each step while still
        using the standard run loop.
        
        Args:
            max_steps: Maximum number of steps to run.
            on_step_start: Async callback called before each step.
            on_step_end: Async callback called after each step.
                         Can call agent.pause() to pause execution.
        
        Returns:
            Agent result (AgentHistoryList)
        """
        # Wrap callbacks to pass self (PrivacyAgent) instead of inner Agent
        async def wrapped_start(agent):
            if on_step_start:
                await on_step_start(self)
        
        async def wrapped_end(agent):
            if on_step_end:
                await on_step_end(self)
        
        return await self._agent.run(
            max_steps=max_steps,
            on_step_start=wrapped_start if on_step_start else None,
            on_step_end=wrapped_end if on_step_end else None,
        )
    
    def get_step_state(self) -> dict:
        """
        Get current step state for debugging/inspection.
        
        Returns:
            Dict with current step information.
        """
        return {
            "step_number": self._agent.state.n_steps,
            "is_done": self._agent.history.is_done() if self._agent.history else False,
            "is_paused": self._agent.state.paused,
            "is_stopped": self._agent.state.stopped,
            "consecutive_failures": self._agent.state.consecutive_failures,
            "last_result": self._agent.state.last_result,
            "filter_stats": self.get_filter_stats(),
        }


# Forward-looking alias — the class began life as PrivacyAgent but has grown
# into a generic HookedAgent host.  New code should import ``HookedAgent``;
# ``PrivacyAgent`` remains for backward compatibility with build_node.py
# and any downstream that checks class_name.
HookedAgent = PrivacyAgent


# Convenience function to create a privacy-enabled agent
def create_privacy_agent(
    task: str,
    llm: "BaseChatModel | None" = None,
    config_path: str | None = None,
    privacy_enabled: bool = True,
    **kwargs,
) -> PrivacyAgent:
    """
    Create a PrivacyAgent with default configuration.
    
    Args:
        task: Task description
        llm: Language model
        config_path: Path to privacy config JSON. If None, uses default.
        privacy_enabled: If False, bypasses all privacy filtering
        **kwargs: Additional Agent arguments
        
    Returns:
        Configured PrivacyAgent
    """
    config = load_privacy_config(config_path)
    privacy_filter = RegexMaskFilter(config)
    
    return PrivacyAgent(
        task=task,
        llm=llm,
        privacy_filter=privacy_filter,
        privacy_enabled=privacy_enabled,
        **kwargs,
    )
