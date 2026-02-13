import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from browser_use.agent.service import Agent
from browser_use.agent.views import ActionResult, AgentHistory, AgentStepInfo, StepMetadata
from browser_use.browser.views import BrowserStateHistory, BrowserStateSummary, PageInfo, TabInfo

from agent.ec_skills.browser_use_extension.passive_protocol import PassiveBrowserCommand, PassiveBrowserStepResult


class PassivePubSubTransport(Protocol):
    async def publish_command(self, cmd: PassiveBrowserCommand) -> None:
        raise NotImplementedError

    async def wait_for_result(self, *, run_id: str, step_id: str, timeout_s: float) -> PassiveBrowserStepResult:
        raise NotImplementedError


class AsyncQueuePassivePubSubTransport:
    """Pub/sub transport backed by an async queue.

    A websocket/AppSync subscription callback should call `deliver_result(...)` whenever
    a PassiveBrowserStepResult is received.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[PassiveBrowserStepResult] = asyncio.Queue()
        self._pending: dict[tuple[str, str], PassiveBrowserStepResult] = {}

    async def publish_command(self, cmd: PassiveBrowserCommand) -> None:
        raise NotImplementedError('publish_command must be implemented for your pub endpoint')

    async def prepare_for_result(self, *, run_id: str, step_id: str) -> None:
        """No-op for queue-based transports — results arrive via deliver_result()."""
        pass

    def deliver_result(self, result: PassiveBrowserStepResult) -> None:
        # Log when result is delivered (L2C - Local to Cloud result)
        try:
            from utils.logger_helper import logger_helper as logger
            logger.debug(f"[L2C] 📥 deliver_result: run_id={result.run_id}, step_id={result.step_id}")
            from agent.cloud_worker.cloud_logger import get_skill_editor_logger
            se_logger = get_skill_editor_logger()
            if se_logger:
                results_count = len(result.action_results) if result.action_results else 0
                se_logger.log(f"[L2C] 📥 Received step result: stepId={result.step_id}, results={results_count}")
        except Exception:
            pass
        
        try:
            self._queue.put_nowait(result)
        except Exception:
            self._pending[(result.run_id, result.step_id)] = result

    async def wait_for_result(self, *, run_id: str, step_id: str, timeout_s: float) -> PassiveBrowserStepResult:
        key = (run_id, step_id)
        if key in self._pending:
            return self._pending.pop(key)

        deadline = time.time() + max(1.0, float(timeout_s))
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f'Timed out waiting for passive step result run_id={run_id} step_id={step_id}')

            try:
                res = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            except TimeoutError:
                raise TimeoutError(f'Timed out waiting for passive step result run_id={run_id} step_id={step_id}')

            if res.run_id == run_id and res.step_id == step_id:
                return res
            self._pending[(res.run_id, res.step_id)] = res


class CloudWorkerPassiveTransport(AsyncQueuePassivePubSubTransport):
    """
    Transport for CloudAgent running inside cloud worker.
    
    - publish_command: Sends commands to local client via AppSync mutation
    - wait_for_result: Receives results from the cloud worker's PassiveStepResultListener
      which delivers results via deliver_result()
    
    This transport does NOT start its own WebSocket subscription. Instead, the cloud worker's
    PassiveStepResultListener handles the subscription and calls deliver_result() when
    messages arrive.
    """
    
    def __init__(
        self,
        *,
        appsync_url: str,
        appsync_api_key: str,
        client_id: str,
    ) -> None:
        super().__init__()
        self.appsync_url = appsync_url
        self.appsync_api_key = appsync_api_key
        self.client_id = client_id
    
    async def publish_command(self, cmd: PassiveBrowserCommand) -> None:
        """Publish command to local client via AppSync mutation."""
        
        mutation = """
        mutation PublishPassiveCommand($input: PassiveBrowserCommandEnvelopeInput!) {
          publishPassiveCommand(input: $input) {
            runId
            clientId
            stepId
          }
        }
        """
        
        command_dict = cmd.model_dump()
        # AWSJSON scalar expects a JSON string, not a nested object
        command_json_str = json_module.dumps(command_dict)
        
        payload = {
            "runId": cmd.run_id,
            "clientId": self.client_id,
            "stepId": cmd.step_id,
            "command": command_json_str,  # JSON string for AWSJSON type
        }
        
        # Log the IDs being used for debugging
        print(f"[CloudWorkerPassiveTransport] publishPassiveCommand: clientId={self.client_id}, runId={cmd.run_id}, stepId={cmd.step_id}")
        
        # Log to skill editor console (C2L - Cloud to Local command)
        try:
            from agent.cloud_worker.cloud_logger import get_skill_editor_logger
            se_logger = get_skill_editor_logger()
            if se_logger:
                # Summarize actions for logging
                actions_summary = cmd.actions[:3] if cmd.actions else []  # First 3 actions
                actions_str = json_module.dumps(actions_summary, default=str)[:300]
                se_logger.log(
                    f"[C2L] 📤 publishPassiveCommand: clientId={self.client_id}, runId={cmd.run_id}, stepId={cmd.step_id}, actions={actions_str}"
                )
        except Exception:
            pass  # Don't fail if logging fails
        except Exception:
            pass  # Don't fail if logging fails
        
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.appsync_api_key,
            "cache-control": "no-cache",
        }
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.appsync_url,
                json={"query": mutation, "variables": {"input": payload}},
                headers=headers,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            print(f"[CloudWorkerPassiveTransport] AppSync response: {data}")
            if isinstance(data, dict) and data.get("errors"):
                raise RuntimeError(f"AppSync publishPassiveCommand failed: {data.get('errors')}")


class HttpPassivePubSubTransport:
    """Minimal HTTP-based pub + synchronous wait.

    This is intentionally generic. In production you can swap this transport for:
    - AppSync GraphQL mutation + realtime subscription
    - API Gateway websocket management API
    - Redis streams, SQS+callback, etc.
    """

    def __init__(
        self,
        *,
        publish_endpoint: str,
        wait_endpoint: str,
        auth_token: str | None = None,
    ) -> None:
        self.publish_endpoint = publish_endpoint
        self.wait_endpoint = wait_endpoint
        self.auth_token = auth_token

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.auth_token:
            h["Authorization"] = f"Bearer {self.auth_token}"
        return h

    async def publish_command(self, cmd: PassiveBrowserCommand) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.publish_endpoint, json=cmd.model_dump(), headers=self._headers(), timeout=30.0)
            resp.raise_for_status()

    async def wait_for_result(self, *, run_id: str, step_id: str, timeout_s: float) -> PassiveBrowserStepResult:
        deadline = time.time() + max(1.0, float(timeout_s))
        last_error: Exception | None = None
        async with httpx.AsyncClient() as client:
            while time.time() < deadline:
                try:
                    resp = await client.get(
                        self.wait_endpoint,
                        params={"run_id": run_id, "step_id": step_id},
                        headers=self._headers(),
                        timeout=30.0,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return PassiveBrowserStepResult.model_validate(data)
                except Exception as e:
                    last_error = e
                    await asyncio.sleep(0.5)
        raise TimeoutError(f"Timed out waiting for passive step result run_id={run_id} step_id={step_id} ({last_error})")


@dataclass
class RemoteDOMState:
    """Minimal dom_state compatible with browser-use AgentMessagePrompt."""

    dom_text: str
    selector_map: dict[int, Any]
    _root: Any = None

    def llm_representation(self, include_attributes: list[str] | None = None) -> str:
        return self.dom_text or ''


def _cloud_agent_log(msg: str, level: str = "info") -> None:
    """Log message to both local logger and skill editor console."""
    try:
        from utils.logger_helper import logger_helper as logger
        if level == "debug":
            logger.debug(msg)
        elif level == "warning":
            logger.warning(msg)
        elif level == "error":
            logger.error(msg)
        else:
            logger.info(msg)
    except Exception:
        pass
    try:
        from agent.cloud_worker.cloud_logger import get_skill_editor_logger
        se_logger = get_skill_editor_logger()
        if se_logger:
            se_logger.log(msg)
    except Exception:
        pass


class CloudAgent(Agent):
    """Cloud-side agent.

    Runs browser-use's normal LLM loop, but delegates all browser observation + action execution
    to a remote PassiveAgent (client).
    """

    def __init__(
        self,
        *,
        transport: PassivePubSubTransport,
        run_id: str,
        acct_site_id: str | None = None,
        agent_id: str | None = None,
        skill_id: str | None = None,
        node_id: str | None = None,
        bootstrap_url: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.transport = transport
        self.run_id = run_id
        self.acct_site_id = acct_site_id
        self.cloud_agent_id = agent_id
        self.skill_id = skill_id
        self.node_id = node_id
        self.bootstrap_url = bootstrap_url

        self._next_state_from_client: dict[str, Any] | None = None
        # Track the tab we expect to be focused on (for wrong-tab detection)
        self._expected_tab_url: str | None = None
        self._expected_tab_id: str | None = None
        self._wrong_tab_fix_attempts: int = 0
        self._max_wrong_tab_fixes: int = 2  # give up after this many attempts
        
        _cloud_agent_log(f"[CloudAgent] Initialized: run_id={run_id}, agent_id={agent_id}, skill_id={skill_id}")

    async def run(
        self,
        max_steps: int = 100,
        on_step_start=None,
        on_step_end=None,
    ):
        _cloud_agent_log(f"[CloudAgent] 🚀 Starting run: run_id={self.run_id}, max_steps={max_steps}")
        
        # Cloud agent must not start a local browser.
        # Prime an initial observation BEFORE the first step so each step iteration
        # only needs one remote round-trip (execute actions -> receive next observation).
        if self._next_state_from_client is None:
            actions: list[dict[str, dict[str, Any]]] = []

            url = self.bootstrap_url
            if not url and self.directly_open_url and not self.state.follow_up_task:
                try:
                    url = self._extract_start_url(self.task)
                except Exception:
                    url = None

            if url:
                actions = [{"navigate": {"url": url, "new_tab": False}}]
                _cloud_agent_log(f"[CloudAgent] 🌐 Bootstrap: navigating to {url}")
            else:
                _cloud_agent_log(f"[CloudAgent] 🌐 Bootstrap: no initial URL, getting current page state")

            bootstrap = await self._remote_step(
                actions=actions,
                include_screenshot=True,
                step_id="bootstrap",
            )
            browser_dict = bootstrap.browser or {}
            dom_tree = getattr(bootstrap, 'dom_tree', None)
            if dom_tree and isinstance(dom_tree, dict) and len(dom_tree) > 0:
                browser_dict['dom_tree'] = dom_tree
            self._next_state_from_client = browser_dict
            bootstrap_url = bootstrap.browser.get('url', 'N/A') if bootstrap.browser else 'N/A'
            # Track the initial tab for wrong-tab detection
            if bootstrap_url and bootstrap_url != 'N/A':
                self._expected_tab_url = bootstrap_url
            _cloud_agent_log(f"[CloudAgent] ✅ Bootstrap complete: url={bootstrap_url}")

        try:
            while self.state.n_steps <= max_steps:
                # Check consecutive failures like parent Agent.run() does
                max_total_failures = self.settings.max_failures + int(
                    getattr(self.settings, 'final_response_after_failure', False)
                )
                if self.state.consecutive_failures >= max_total_failures:
                    _cloud_agent_log(
                        f"[CloudAgent] ❌ Stopping due to {self.state.consecutive_failures} consecutive failures"
                    )
                    break

                current_step = self.state.n_steps - 1
                _cloud_agent_log(f"[CloudAgent] 📍 Step {current_step}/{max_steps} starting...")
                step_info = AgentStepInfo(step_number=current_step, max_steps=max_steps)
                is_done = await self._execute_step(current_step, max_steps, step_info, on_step_start, on_step_end)
                if is_done:
                    _cloud_agent_log(f"[CloudAgent] 🏁 Run completed at step {current_step}")
                    return self.history
            _cloud_agent_log(f"[CloudAgent] ⚠️ Run ended: max_steps ({max_steps}) reached")
            return self.history
        finally:
            # Close transport to prevent stale subscriptions from lingering
            if hasattr(self.transport, 'close') and callable(self.transport.close):
                try:
                    self.transport.close()
                except Exception:
                    pass

    async def _prepare_context(self, step_info: AgentStepInfo | None = None) -> BrowserStateSummary:
        # If we already have a post-action snapshot from previous step, use it.
        if self._next_state_from_client is None:
            raise RuntimeError(
                'CloudAgent requires a cached remote observation before calling step(). '
                'Call CloudAgent.run(...) which primes an initial observation, '
                'or set _next_state_from_client from a PassiveBrowserStepResult before stepping.'
            )

        browser_state_summary = self._browser_state_from_payload(self._next_state_from_client)
        # NOTE: Do NOT clear _next_state_from_client here.
        # _execute_actions() will replace it with the new state from the remote step.
        # If the LLM call fails before _execute_actions runs, keeping the cached
        # state allows the next retry step to reuse it instead of crashing.

        # Update action models based on URL for this page
        await self._update_action_models_for_page(browser_state_summary.url)

        page_filtered_actions = self.tools.registry.get_prompt_description(browser_state_summary.url)
        self._message_manager.create_state_messages(
            browser_state_summary=browser_state_summary,
            model_output=self.state.last_model_output,
            result=self.state.last_result,
            step_info=step_info,
            use_vision=self.settings.use_vision,
            page_filtered_actions=page_filtered_actions if page_filtered_actions else None,
            sensitive_data=self.sensitive_data,
            available_file_paths=self.available_file_paths,
            unavailable_skills_info=None,
        )

        await self._force_done_after_last_step(step_info)
        await self._force_done_after_failure()
        return browser_state_summary

    def _find_tab_id_by_url(self, tabs: list, expected_url: str) -> str | None:
        """Find tab_id whose URL best matches the expected URL.

        Priority (highest first):
        1. Exact hostname + path-prefix match
        2. Exact hostname match
        3. Base domain match (fallback — e.g. s.1688.com vs www.1688.com)

        This prevents flip-flopping between two tabs on the same base domain
        (e.g. homepage tab vs search-results tab).
        """
        if not tabs or not expected_url:
            return None
        from urllib.parse import urlparse
        expected_parsed = urlparse(expected_url)
        expected_host = expected_parsed.netloc.split(':')[0]
        expected_domain = self._base_domain(expected_url)
        if not expected_domain:
            return None

        best_id: str | None = None
        best_score = 0  # 1=domain, 2=host, 3=host+path

        for t in tabs:
            if not isinstance(t, dict):
                continue
            tab_url = t.get('url', '')
            tab_parsed = urlparse(tab_url)
            tab_host = tab_parsed.netloc.split(':')[0]
            tab_domain = self._base_domain(tab_url)
            tab_id = t.get('tab_id') or t.get('target_id', '')
            if not tab_id:
                continue

            if tab_domain != expected_domain:
                continue

            score = 1  # base domain match
            if tab_host == expected_host:
                score = 2  # exact hostname match
                # Bonus for path prefix match
                if expected_parsed.path and len(expected_parsed.path) > 1:
                    if tab_parsed.path.startswith(expected_parsed.path):
                        score = 3

            if score > best_score:
                best_score = score
                best_id = tab_id

        return best_id

    @staticmethod
    def _base_domain(url: str) -> str:
        """Extract base domain (eTLD+1) from a URL for subdomain-aware comparison.

        Examples:
            https://www.1688.com/  -> 1688.com
            https://s.1688.com/... -> 1688.com
            https://detail.1688.com/... -> 1688.com
            https://www.amazon.com/... -> amazon.com
            https://login.taobao.com/... -> taobao.com
        """
        from urllib.parse import urlparse
        netloc = urlparse(url).netloc
        if not netloc:
            return ''
        # Remove port if present
        host = netloc.split(':')[0]
        parts = host.split('.')
        # Handle common two-part TLDs: .com.cn, .co.uk, .co.jp, etc.
        if len(parts) >= 3 and parts[-2] in ('com', 'co', 'net', 'org', 'gov', 'edu', 'ac'):
            return '.'.join(parts[-3:])
        if len(parts) >= 2:
            return '.'.join(parts[-2:])
        return host

    async def _execute_actions(self) -> None:
        if self.state.last_model_output is None:
            raise ValueError('No model output to execute actions from')

        actions = []
        try:
            for a in (self.state.last_model_output.action or []):
                actions.append(a.model_dump(exclude_unset=True))
        except Exception:
            actions = []

        # --- Track expected tab from navigate/switch actions ---
        llm_has_explicit_switch = False
        for action_dict in actions:
            if 'navigate' in action_dict:
                nav = action_dict['navigate']
                nav_url = nav.get('url', '')
                if nav_url:
                    self._expected_tab_url = nav_url
                    _cloud_agent_log(f"[CloudAgent] 📌 Tracking expected tab URL: {nav_url[:80]}")
            elif 'switch' in action_dict:
                switch = action_dict['switch']
                tab_id = switch.get('tab_id', '')
                if tab_id:
                    llm_has_explicit_switch = True
                    self._expected_tab_id = tab_id
                    # Look up the URL for this tab from cached state
                    if self._next_state_from_client:
                        for t in (self._next_state_from_client.get('tabs') or []):
                            if isinstance(t, dict) and (t.get('tab_id') or t.get('target_id', '')) == tab_id:
                                self._expected_tab_url = t.get('url', '')
                                break
                    _cloud_agent_log(f"[CloudAgent] 📌 Tracking expected tab: id={tab_id}, url={self._expected_tab_url or 'unknown'}")

        # --- Intercept extract actions: split into extract_dom (local) + LLM (cloud) ---
        # Track which action indices are extract actions that need cloud-side LLM post-processing.
        # extract_dom on the local side simply extracts the page DOM/markdown with no params;
        # all query-specific processing (pagination, truncation, LLM) happens cloud-side.
        extract_indices: dict[int, dict] = {}  # index -> original extract params
        remote_actions = []
        for i, action_dict in enumerate(actions):
            if 'extract' in action_dict:
                extract_params = dict(action_dict['extract'])
                extract_indices[i] = extract_params
                # Send extract_dom with no params — local just extracts the full page DOM
                remote_actions.append({'extract_dom': {}})
                _cloud_agent_log(
                    f"[CloudAgent] 🔀 Splitting extract action[{i}] -> extract_dom (local) + LLM (cloud)"
                )
            else:
                remote_actions.append(action_dict)

        # --- Log click/input targets with element text for debugging ---
        # Extract from the dom_text (format: [INDEX]<tag /> text) so we know what the LLM intends to click/type on.
        cached_dom_text = ''
        if self._next_state_from_client:
            cached_dom_text = self._next_state_from_client.get('dom_text', '') or ''
            # If dom_text is empty, try dom_tree
            if not cached_dom_text and isinstance(self._next_state_from_client.get('dom_tree'), dict):
                cached_dom_text = self._next_state_from_client['dom_tree'].get('dom_text', '') or ''
        for action_dict in remote_actions:
            for act_type in ('click', 'input', 'send_keys'):
                if act_type not in action_dict:
                    continue
                act_params = action_dict[act_type]
                idx = act_params.get('index')
                if idx is not None and cached_dom_text:
                    # Find the element context in dom_text: look for [INDEX] and grab surrounding text
                    import re as _re
                    pattern = _re.compile(rf'\[{idx}\]<([^>]*)\s*/?>([^\[]*)', _re.DOTALL)
                    m = pattern.search(cached_dom_text)
                    if m:
                        tag = m.group(1).strip()[:30]
                        text_after = m.group(2).strip()[:80]
                        element_desc = f'<{tag}> "{text_after}"' if text_after else f'<{tag}>'
                    else:
                        element_desc = '(not found in dom_text)'
                    extra = ''
                    if act_type == 'input':
                        extra = f', text="{act_params.get("text", "")[:40]}"'
                    _cloud_agent_log(
                        f"[CloudAgent] 🎯 {act_type}(index={idx}) -> {element_desc}{extra}"
                    )

        # Log the actions being sent to local client
        actions_summary = str(remote_actions)[:500]

        # --- Pre-pend switch_tab to ensure correct tab focus ---
        # The client has a bug where focus reverts to another tab between steps.
        # Always prepend a switch_tab if we have a tracked expected tab to ensure
        # the interaction happens on the right tab.
        # Fix #3: Refresh tab_id from cached state by URL-domain match.
        # Tab IDs change every step (CDP sessions recreated), so never trust stale IDs.
        prepended_switch = False
        # Check if we're already on the correct tab (URL domain matches).
        # If so, skip auto-prepend — the unnecessary switch triggers a DOM refresh on the
        # local side which regenerates selector_map with DIFFERENT indices, breaking the
        # LLM's click/input targets that were chosen from the previous step's DOM.
        current_url = (self._next_state_from_client or {}).get('url', '') if self._next_state_from_client else ''
        already_on_correct_tab = False
        if self._expected_tab_url and current_url:
            already_on_correct_tab = (
                self._base_domain(current_url) == self._base_domain(self._expected_tab_url)
            )
        if self._expected_tab_url and remote_actions and not llm_has_explicit_switch:
            # Only auto-prepend when LLM did NOT explicitly request a switch.
            # If LLM wants to switch to a specific tab (e.g. search results), respect that.
            if already_on_correct_tab:
                _cloud_agent_log(
                    f"[CloudAgent] ✅ Already on correct tab (domain={self._base_domain(current_url)}, "
                    f"url={current_url[:60]}) — skipping auto-prepend to preserve element indices"
                )
            cached_tabs = (self._next_state_from_client or {}).get('tabs', [])
            fresh_id = self._find_tab_id_by_url(cached_tabs, self._expected_tab_url)
            if fresh_id and fresh_id != self._expected_tab_id:
                _cloud_agent_log(
                    f"[CloudAgent] 🔄 Tab ID refreshed from cached tabs: "
                    f"{self._expected_tab_id} -> {fresh_id} (domain-match for {self._expected_tab_url[:60]})"
                )
                self._expected_tab_id = fresh_id
            if self._expected_tab_id and not already_on_correct_tab:
                first_action = remote_actions[0]
                already_switching = (
                    'switch' in first_action
                    and first_action['switch'].get('tab_id') == self._expected_tab_id
                )
                if not already_switching:
                    remote_actions = [{'switch': {'tab_id': self._expected_tab_id}}] + remote_actions
                    prepended_switch = True
                    _cloud_agent_log(
                        f"[CloudAgent] 🔧 Auto-prepended switch_tab({self._expected_tab_id}) "
                        f"to ensure correct tab focus"
                    )
        elif llm_has_explicit_switch:
            _cloud_agent_log(
                f"[CloudAgent] ℹ️ LLM has explicit switch action — skipping auto-prepend to respect LLM's target tab"
            )

        _cloud_agent_log(f"[CloudAgent] 📤 Sending {len(remote_actions)} action(s) to local: {actions_summary}")

        result = await self._remote_step(
            actions=remote_actions, include_screenshot=False, step_id=f"step-{self.state.n_steps}"
        )

        # --- Fix #1 & #2: Detect switch_tab failure and refresh tab_id from fresh payload ---
        if prepended_switch and result.action_results and len(result.action_results) > 0:
            sw = result.action_results[0]
            sw_error = sw.get('error', '') if isinstance(sw, dict) else ''
            sw_content = sw.get('extracted_content', '') if isinstance(sw, dict) else ''
            switch_failed = (
                'switch failed' in sw_error.lower()
                or 'attempted to switch' in sw_content.lower()
            )
            if switch_failed:
                _cloud_agent_log(
                    f"[CloudAgent] ⚠️ Prepended switch_tab({self._expected_tab_id}) FAILED: "
                    f"error={sw_error[:120]}, content={sw_content[:120]}",
                    level='warning',
                )
                # Fix #2: Find correct tab by URL match from FRESH browser payload
                fresh_tabs = (result.browser or {}).get('tabs', [])
                new_id = self._find_tab_id_by_url(fresh_tabs, self._expected_tab_url)
                if new_id and new_id != self._expected_tab_id:
                    _cloud_agent_log(
                        f"[CloudAgent] 🔄 Corrected tab_id from fresh payload: "
                        f"{self._expected_tab_id} -> {new_id}"
                    )
                    self._expected_tab_id = new_id
                elif not new_id:
                    tab_urls = [t.get('url','')[:60] for t in fresh_tabs if isinstance(t, dict)]
                    _cloud_agent_log(
                        f"[CloudAgent] ⚠️ No tab matches expected domain. Tabs: {tab_urls}",
                        level='warning',
                    )
            else:
                _cloud_agent_log(
                    f"[CloudAgent] ✅ Prepended switch_tab({self._expected_tab_id}) succeeded"
                )

        # Strip the prepended switch_tab result so the LLM only sees results for its own actions
        if prepended_switch and result.action_results and len(result.action_results) > 0:
            _cloud_agent_log(
                f"[CloudAgent] 🔧 Stripping prepended switch_tab result (had {len(result.action_results)} results)"
            )
            result.action_results = result.action_results[1:]

        parsed_results: list[ActionResult] = []

        # --- Handle client-side errors (ok=false) ---
        # When the local client returns ok=false with errors, the action_results will be
        # empty. Surface the errors as ActionResult entries so the LLM knows what happened
        # instead of silently proceeding with empty state.
        if not result.ok and result.errors:
            error_msg = '; '.join(result.errors)
            # Truncate very long tracebacks for the LLM
            if len(error_msg) > 500:
                error_msg = error_msg[:500] + '...[truncated]'
            _cloud_agent_log(
                f"[CloudAgent] ❌ Client returned ok=false with {len(result.errors)} error(s): {error_msg[:200]}",
                level='error',
            )
            # Create one error ActionResult per original action so the LLM sees the failure
            for i in range(len(remote_actions)):
                parsed_results.append(ActionResult(error=f'Client error: {error_msg}'))
        else:
            for i, r in enumerate(result.action_results or []):
                try:
                    ar = ActionResult.model_validate(r)
                except Exception:
                    ar = ActionResult(error=str(r))

                if i in extract_indices and not ar.error:
                    # This was an extract_dom result — do cloud-side LLM post-processing
                    _cloud_agent_log(
                        f"[CloudAgent] 🧠 Running cloud-side LLM extraction for action[{i}]..."
                    )
                    try:
                        ar = await self._cloud_extract_llm(
                            raw_markdown=ar.extracted_content or '',
                            extract_params=extract_indices[i],
                        )
                    except Exception as e:
                        _cloud_agent_log(
                            f"[CloudAgent] ❌ Cloud LLM extraction failed: {e}", level="error"
                        )
                        ar = ActionResult(error=f'Cloud extract LLM failed: {e}')

                parsed_results.append(ar)

        # If we still have no results (e.g. ok=true but empty action_results), create placeholder
        if not parsed_results and remote_actions:
            _cloud_agent_log(
                f"[CloudAgent] ⚠️ No action results received for {len(remote_actions)} action(s), creating placeholders",
                level='warning',
            )
            for _ in remote_actions:
                parsed_results.append(ActionResult(error='No result received from client'))

        # Log results received from local client
        results_summary = [{'done': r.is_done, 'error': r.error[:100] if r.error else None} for r in parsed_results]
        _cloud_agent_log(f"[CloudAgent] 📥 Received {len(parsed_results)} result(s) from local: {results_summary}")

        self.state.last_result = parsed_results
        browser_dict = result.browser or {}
        # Inject dom_tree into browser_dict if present and non-empty.
        # dom_tree carries unmasked dom_text and selector_map for reconstruction.
        dom_tree = getattr(result, 'dom_tree', None)
        if dom_tree and isinstance(dom_tree, dict) and len(dom_tree) > 0:
            browser_dict['dom_tree'] = dom_tree

        # When client returns error with empty browser state, preserve previous state
        # so the LLM still has context (URL, DOM, selectors) to make informed decisions
        if not browser_dict and not result.ok and self._next_state_from_client:
            _cloud_agent_log(
                f"[CloudAgent] ⚠️ Client error with empty browser state, preserving previous state",
                level='warning',
            )
            browser_dict = dict(self._next_state_from_client)

        # --- Wrong-tab detection and auto-correction ---
        # The local client has a bug where after click/type actions, the state capture
        # reverts to a different tab's DOM. Detect this and auto-switch back.
        result_url = browser_dict.get('url', '')
        if self._expected_tab_id and result_url and self._expected_tab_url:
            # Check if the returned URL's base domain matches what we expect
            expected_domain = self._base_domain(self._expected_tab_url)
            actual_domain = self._base_domain(result_url)
            if expected_domain and actual_domain and expected_domain != actual_domain:
                self._wrong_tab_fix_attempts += 1
                _cloud_agent_log(
                    f"[CloudAgent] 🔄 WRONG-TAB DETECTED (attempt {self._wrong_tab_fix_attempts}/{self._max_wrong_tab_fixes}): "
                    f"expected domain={expected_domain} but got domain={actual_domain} (url={result_url[:80]}). ",
                    level='warning',
                )

                if self._wrong_tab_fix_attempts > self._max_wrong_tab_fixes:
                    # Give up — clear tracking so LLM sees real DOM and can decide
                    _cloud_agent_log(
                        f"[CloudAgent] ⛔ Giving up on wrong-tab auto-fix after {self._max_wrong_tab_fixes} attempts. "
                        f"Clearing tab tracking. LLM will see actual DOM and navigate itself.",
                        level='warning',
                    )
                    self._expected_tab_url = None
                    self._expected_tab_id = None
                    self._wrong_tab_fix_attempts = 0
                else:
                    # Attempt fix
                    try:
                        if self._wrong_tab_fix_attempts == 1:
                            # Attempt 1: switch_tab + wait
                            _cloud_agent_log(f"[CloudAgent] 🔄 Fix attempt 1: switch_tab({self._expected_tab_id}) + wait(2)")
                            fix_actions = [
                                {'switch': {'tab_id': self._expected_tab_id}},
                                {'wait': {'seconds': 2}},
                            ]
                        else:
                            # Attempt 2: navigate directly to the expected URL in current tab
                            _cloud_agent_log(f"[CloudAgent] 🔄 Fix attempt 2: go_to_url({self._expected_tab_url[:80]})")
                            fix_actions = [
                                {'navigate': {'url': self._expected_tab_url, 'new_tab': False}},
                                {'wait': {'seconds': 2}},
                            ]
                        fix_result = await self._remote_step(
                            actions=fix_actions,
                            include_screenshot=False,
                            step_id=f"fix-tab-{self.state.n_steps}-a{self._wrong_tab_fix_attempts}",
                        )
                        fix_browser = fix_result.browser or {}
                        fix_dom_tree = getattr(fix_result, 'dom_tree', None)
                        if fix_dom_tree and isinstance(fix_dom_tree, dict) and len(fix_dom_tree) > 0:
                            fix_browser['dom_tree'] = fix_dom_tree
                        fix_url = fix_browser.get('url', '')
                        _cloud_agent_log(
                            f"[CloudAgent] 🔄 Auto-switch result: url={fix_url[:80]}"
                        )
                        # Check if fix worked
                        fix_domain = self._base_domain(fix_url) if fix_url else ''
                        if fix_domain == expected_domain:
                            _cloud_agent_log(f"[CloudAgent] ✅ Wrong-tab fix succeeded!")
                            self._wrong_tab_fix_attempts = 0
                        # Use the fix result state regardless (may still be wrong, next step will re-detect)
                        browser_dict = fix_browser
                    except Exception as e:
                        _cloud_agent_log(
                            f"[CloudAgent] ❌ Auto-switch failed: {e}", level='error'
                        )
            else:
                # Domain matches — reset the counter
                if self._wrong_tab_fix_attempts > 0:
                    _cloud_agent_log(f"[CloudAgent] ✅ Tab domain matches expected, resetting fix counter")
                    self._wrong_tab_fix_attempts = 0

        # --- Update _expected_tab_url to track the actual current URL ---
        # After each step the browser may have navigated within the same site
        # (e.g. homepage -> search results on a subdomain). Keep tracking the
        # REAL current URL so _find_tab_id_by_url matches the correct tab and
        # the "already on correct tab" check uses an up-to-date URL.
        result_url_now = browser_dict.get('url', '')
        if result_url_now and self._expected_tab_url:
            if result_url_now != self._expected_tab_url:
                if self._base_domain(result_url_now) == self._base_domain(self._expected_tab_url):
                    _cloud_agent_log(
                        f"[CloudAgent] 📌 Updated expected tab URL: "
                        f"{self._expected_tab_url[:60]} -> {result_url_now[:60]}"
                    )
                    self._expected_tab_url = result_url_now

        # --- Detect new tabs opened by actions and auto-follow ---
        # E.g. clicking a product link that opens in a new tab, or search-submit
        # that opens results in a new tab.  Detect the new tab and update tracking
        # so the next step interacts with it (or prepends a switch_tab).
        pre_tabs = (
            (self._next_state_from_client or {}).get('tabs', [])
            if self._next_state_from_client else []
        )
        post_tabs = browser_dict.get('tabs', [])
        if len(post_tabs) > len(pre_tabs) and self._expected_tab_url:
            pre_ids = set()
            for t in pre_tabs:
                if isinstance(t, dict):
                    pre_ids.add(t.get('tab_id') or t.get('target_id', ''))
            new_tabs = [
                t for t in post_tabs
                if isinstance(t, dict)
                and (t.get('tab_id') or t.get('target_id', '')) not in pre_ids
            ]
            if new_tabs:
                expected_domain = self._base_domain(self._expected_tab_url)
                for nt in new_tabs:
                    nt_url = nt.get('url', '')
                    nt_id = nt.get('tab_id') or nt.get('target_id', '')
                    nt_domain = self._base_domain(nt_url)
                    if nt_domain == expected_domain and nt_id:
                        _cloud_agent_log(
                            f"[CloudAgent] 🆕 New tab detected on same domain: "
                            f"{nt_url[:80]} (id={nt_id}) — updating tracking"
                        )
                        self._expected_tab_url = nt_url
                        self._expected_tab_id = nt_id
                        break
                    elif nt_url and nt_id:
                        _cloud_agent_log(
                            f"[CloudAgent] 🆕 New tab detected on different domain: "
                            f"{nt_url[:80]} (id={nt_id}) — ignoring"
                        )

        self._next_state_from_client = browser_dict

    async def _make_history_item(
        self,
        model_output,
        browser_state_summary: BrowserStateSummary,
        result: list[ActionResult],
        metadata: StepMetadata | None = None,
        state_message: str | None = None,
    ) -> None:
        # CloudAgent cannot reliably reconstruct EnhancedDOMTreeNode instances on the server,
        # so we avoid calling AgentHistory.get_interacted_element().
        state_history = BrowserStateHistory(
            url=browser_state_summary.url,
            title=browser_state_summary.title,
            tabs=browser_state_summary.tabs,
            interacted_element=[None],
            screenshot_path=None,
        )

        history_item = AgentHistory(
            model_output=model_output,
            result=result,
            state=state_history,
            metadata=metadata,
            state_message=state_message,
        )
        self.history.add_item(history_item)

    async def _cloud_extract_llm(
        self,
        raw_markdown: str,
        extract_params: dict,
    ) -> ActionResult:
        """Perform LLM post-processing on raw markdown extracted by the local client.

        The local extract_dom returns the full page markdown. This method handles
        pagination (start_from_char), truncation, and LLM post-processing — all cloud-side.
        """
        from browser_use.llm.messages import SystemMessage, UserMessage

        page_extraction_llm = self.settings.page_extraction_llm
        if page_extraction_llm is None:
            return ActionResult(error='No page_extraction_llm configured for cloud-side extraction')

        query = extract_params.get('query', '')
        output_schema = extract_params.get('output_schema')
        start_from_char = int(extract_params.get('start_from_char', 0) or 0)

        # Get current_url from cached browser state
        current_url = ''
        if self._next_state_from_client and isinstance(self._next_state_from_client, dict):
            current_url = self._next_state_from_client.get('url', '')

        content = raw_markdown
        if not content:
            return ActionResult(error='extract_dom returned empty content')

        # --- Pagination: apply start_from_char cloud-side ---
        full_length = len(content)
        if start_from_char > 0:
            if start_from_char >= len(content):
                return ActionResult(
                    error=f'start_from_char ({start_from_char}) exceeds content length {full_length} characters.'
                )
            content = content[start_from_char:]

        # --- Smart truncation with context preservation ---
        MAX_CHAR_LIMIT = 100000
        truncated = False
        next_start = None
        if len(content) > MAX_CHAR_LIMIT:
            truncate_at = MAX_CHAR_LIMIT
            paragraph_break = content.rfind('\n\n', MAX_CHAR_LIMIT - 500, MAX_CHAR_LIMIT)
            if paragraph_break > 0:
                truncate_at = paragraph_break
            else:
                sentence_break = content.rfind('.', MAX_CHAR_LIMIT - 200, MAX_CHAR_LIMIT)
                if sentence_break > 0:
                    truncate_at = sentence_break + 1
            content = content[:truncate_at]
            truncated = True
            next_start = start_from_char + truncate_at

        # Build stats summary for LLM context
        stats_summary = f'Content: {full_length:,} chars total'
        if start_from_char > 0:
            stats_summary += f' (started from char {start_from_char:,})'
        if truncated:
            stats_summary += f' → {len(content):,} chars (truncated, use start_from_char={next_start} to continue)'
        stats_summary += f' from {current_url}' if current_url else ''

        # If the LLM didn't provide output_schema, use the agent-injected extraction_schema
        if output_schema is None and getattr(self, 'extraction_schema', None) is not None:
            output_schema = self.extraction_schema

        # Attempt to convert output_schema to a pydantic model
        structured_model = None
        if output_schema is not None:
            try:
                from browser_use.tools.extraction.schema_utils import schema_dict_to_pydantic_model
                structured_model = schema_dict_to_pydantic_model(output_schema)
            except (ValueError, TypeError) as exc:
                _cloud_agent_log(
                    f'[CloudAgent] Invalid output_schema, falling back to free-text: {exc}',
                    level='warning',
                )
                output_schema = None

        # --- Structured extraction path ---
        if structured_model is not None:
            system_prompt = (
                'You are an expert at extracting structured data from the markdown of a webpage.\n\n'
                '<input>\n'
                'You will be given a query, a JSON Schema, and the markdown of a webpage that has been '
                'filtered to remove noise and advertising content.\n'
                '</input>\n\n'
                '<instructions>\n'
                '- Extract ONLY information present in the webpage. Do not guess or fabricate values.\n'
                '- Your response MUST conform to the provided JSON Schema exactly.\n'
                '- If a required field\'s value cannot be found on the page, use null (if the schema allows it) '
                'or an empty string / empty array as appropriate.\n'
                '- If the content was truncated, extract what is available from the visible portion.\n'
                '</instructions>'
            )

            schema_json = json.dumps(output_schema, indent=2)
            prompt = (
                f'<query>\n{query}\n</query>\n\n'
                f'<output_schema>\n{schema_json}\n</output_schema>\n\n'
                f'<content_stats>\n{stats_summary}\n</content_stats>\n\n'
                f'<webpage_content>\n{content}\n</webpage_content>'
            )

            response = await asyncio.wait_for(
                page_extraction_llm.ainvoke(
                    [SystemMessage(content=system_prompt), UserMessage(content=prompt)],
                    output_format=structured_model,
                ),
                timeout=120.0,
            )

            result_data = response.completion.model_dump(mode='json')
            result_json = json.dumps(result_data)

            extracted_content = (
                f'<url>\n{current_url}\n</url>\n'
                f'<query>\n{query}\n</query>\n'
                f'<structured_result>\n{result_json}\n</structured_result>'
            )

            MAX_MEMORY_LENGTH = 10000
            if len(extracted_content) < MAX_MEMORY_LENGTH:
                memory = extracted_content
                include_once = False
            else:
                memory = f'Query: {query}\nExtracted structured data ({len(result_json)} chars) from {current_url}'
                include_once = True

            _cloud_agent_log(f'[CloudAgent] 📄 Structured extraction complete: {len(result_json)} chars')
            return ActionResult(
                extracted_content=extracted_content,
                include_extracted_content_only_once=include_once,
                long_term_memory=memory,
                metadata={'structured_extraction': True},
            )

        # --- Free-text extraction path (default) ---
        system_prompt = (
            'You are an expert at extracting data from the markdown of a webpage.\n\n'
            '<input>\n'
            'You will be given a query and the markdown of a webpage that has been filtered '
            'to remove noise and advertising content.\n'
            '</input>\n\n'
            '<instructions>\n'
            '- You are tasked to extract information from the webpage that is relevant to the query.\n'
            '- You should ONLY use the information available in the webpage to answer the query. '
            'Do not make up information or provide guess from your own knowledge.\n'
            '- If the information relevant to the query is not available in the page, '
            'your response should mention that.\n'
            '- If the query asks for all items, products, etc., make sure to directly list all of them.\n'
            '- If the content was truncated and you need more information, note that the user can use '
            'start_from_char parameter to continue from where truncation occurred.\n'
            '</instructions>\n\n'
            '<output>\n'
            '- Your output should present ALL the information relevant to the query in a concise way.\n'
            '- Do not answer in conversational format - directly output the relevant information '
            'or that the information is unavailable.\n'
            '</output>'
        )

        prompt = (
            f'<query>\n{query}\n</query>\n\n'
            f'<content_stats>\n{stats_summary}\n</content_stats>\n\n'
            f'<webpage_content>\n{content}\n</webpage_content>'
        )

        response = await asyncio.wait_for(
            page_extraction_llm.ainvoke(
                [SystemMessage(content=system_prompt), UserMessage(content=prompt)]
            ),
            timeout=120.0,
        )

        extracted_content = (
            f'<url>\n{current_url}\n</url>\n'
            f'<query>\n{query}\n</query>\n'
            f'<result>\n{response.completion}\n</result>'
        )

        MAX_MEMORY_LENGTH = 10000
        if len(extracted_content) < MAX_MEMORY_LENGTH:
            memory = extracted_content
            include_once = False
        else:
            memory = f'Query: {query}\nExtracted content ({len(str(response.completion))} chars) from {current_url}'
            include_once = True

        _cloud_agent_log(f'[CloudAgent] 📄 Free-text extraction complete: {len(str(response.completion))} chars')
        return ActionResult(
            extracted_content=extracted_content,
            include_extracted_content_only_once=include_once,
            long_term_memory=memory,
        )

    async def _post_process(self) -> None:
        # Cloud agent doesn't manage downloads locally.
        if self.state.last_result and len(self.state.last_result) == 1 and self.state.last_result[-1].error:
            self.state.consecutive_failures += 1
            return
        if self.state.consecutive_failures > 0:
            self.state.consecutive_failures = 0

    async def _remote_step(
        self,
        *,
        actions: list[dict[str, dict[str, Any]]],
        include_screenshot: bool,
        step_id: str,
        _max_retries: int = 1,
    ) -> PassiveBrowserStepResult:
        timeout_s = float(getattr(self.settings, 'step_timeout', 180) or 180)

        for attempt in range(_max_retries + 1):
            retry_step_id = step_id if attempt == 0 else f"{step_id}-r{attempt}"
            cmd = PassiveBrowserCommand(
                run_id=self.run_id,
                step_id=retry_step_id,
                acct_site_id=self.acct_site_id,
                agent_id=self.cloud_agent_id,
                skill_id=self.skill_id,
                node_id=self.node_id,
                actions=actions,
                include_screenshot=include_screenshot,
                stop_on_error=True,
            )

            if attempt > 0:
                _cloud_agent_log(
                    f"[CloudAgent] 🔁 Retry {attempt}/{_max_retries} for stepId={step_id}",
                    level="warning",
                )

            _cloud_agent_log(f"[CloudAgent] 🔄 _remote_step: stepId={retry_step_id}, actions={len(actions)}, screenshot={include_screenshot}", level="debug")

            # Start subscription + register waiter BEFORE publishing command
            # to avoid race where local client responds before subscription is ready
            await self.transport.prepare_for_result(run_id=self.run_id, step_id=retry_step_id)

            await self.transport.publish_command(cmd)
            _cloud_agent_log(f"[CloudAgent] ⏳ Waiting for local client response (stepId={retry_step_id})...", level="debug")

            try:
                result = await self.transport.wait_for_result(
                    run_id=self.run_id, step_id=retry_step_id, timeout_s=timeout_s
                )
                _cloud_agent_log(f"[CloudAgent] ✅ Received response for stepId={retry_step_id}", level="debug")
                return result
            except (TimeoutError, asyncio.TimeoutError) as e:
                _cloud_agent_log(
                    f"[CloudAgent] ⏰ Timeout waiting for stepId={retry_step_id} "
                    f"(attempt {attempt + 1}/{_max_retries + 1}, timeout={timeout_s}s): {e}",
                    level="error",
                )
                if attempt >= _max_retries:
                    raise

        # Should not reach here, but just in case
        raise TimeoutError(f"All retries exhausted for step {step_id}")

    def _browser_state_from_payload(self, browser_payload: dict[str, Any] | None) -> BrowserStateSummary:
        browser_payload = browser_payload or {}

        # --- Diagnostic logging: what does the LLM actually see? ---
        _bp_keys = list(browser_payload.keys()) if browser_payload else []
        _has_dom_tree = 'dom_tree' in browser_payload
        _raw_dom_text = browser_payload.get('dom_text')
        _dom_text_type = type(_raw_dom_text).__name__
        _dom_text_len = len(_raw_dom_text) if isinstance(_raw_dom_text, str) else 0
        _dom_text_preview = (_raw_dom_text[:300] if isinstance(_raw_dom_text, str) else str(_raw_dom_text)[:300])
        _cloud_agent_log(
            f"[CloudAgent] 🔍 browser_payload keys={_bp_keys}, "
            f"dom_text type={_dom_text_type} len={_dom_text_len}, has_dom_tree={_has_dom_tree}, "
            f"url={browser_payload.get('url', 'N/A')[:100]}"
        )
        _cloud_agent_log(
            f"[CloudAgent] 🔍 dom_text preview: {_dom_text_preview!r}",
            level='debug',
        )

        dom_text = browser_payload.get('dom_text') or ''
        # If dom_text is empty/masked but we have dom_tree, reconstruct from dom_tree.
        # This covers:
        #   1. dom_text masked by client: "[MASKED:N chars]"
        #   2. dom_text moved to dom_tree by client (dom_text empty, dom_tree has content)
        #   3. dom_text absent/None
        needs_reconstruction = (
            not dom_text
            or (isinstance(dom_text, str) and dom_text.startswith('[MASKED:'))
        )
        if needs_reconstruction and browser_payload.get('dom_tree'):
            _cloud_agent_log(
                f"[CloudAgent] ⚠️ dom_text is empty/masked (len={len(dom_text) if dom_text else 0}, "
                f"preview={dom_text[:80]!r}), attempting reconstruction from dom_tree",
                level='warning',
            )
            reconstructed = self._reconstruct_dom_text_from_tree(browser_payload)
            if reconstructed:
                dom_text = reconstructed
                _cloud_agent_log(
                    f"[CloudAgent] ✅ Reconstructed dom_text from dom_tree: {len(dom_text)} chars"
                )
                _cloud_agent_log(
                    f"[CloudAgent] 📝 dom_text content: {dom_text[:500]!r}",
                    level='debug',
                )
            else:
                _cloud_agent_log(
                    '[CloudAgent] ❌ Could not reconstruct dom_text from dom_tree — LLM will have limited page context',
                    level='error',
                )
        selector_map: dict[int, Any] = {}
        try:
            sm = browser_payload.get('selector_map')
            _cloud_agent_log(
                f"[CloudAgent] 🗺️ selector_map debug: top-level type={type(sm).__name__}, "
                f"value_preview={str(sm)[:200] if sm else 'None/empty'}"
            )
            # If top-level selector_map is missing/masked, try dom_tree
            if (not sm or isinstance(sm, str)) and isinstance(browser_payload.get('dom_tree'), dict):
                dt = browser_payload['dom_tree']
                dt_sm = dt.get('selector_map')
                _cloud_agent_log(
                    f"[CloudAgent] 🗺️ dom_tree selector_map: type={type(dt_sm).__name__}, "
                    f"len={len(dt_sm) if hasattr(dt_sm, '__len__') else '?'}, "
                    f"value_preview={str(dt_sm)[:300] if dt_sm else 'None/empty'}"
                )
                if dt_sm and not isinstance(dt_sm, str):
                    sm = dt_sm
                    _cloud_agent_log(
                        f"[CloudAgent] 🗺️ Extracted selector_map from dom_tree: "
                        f"type={type(sm).__name__}, len={len(sm) if hasattr(sm, '__len__') else '?'}"
                    )
            if isinstance(sm, list):
                for item in sm:
                    if not isinstance(item, dict):
                        continue
                    i = item.get('i')
                    e = item.get('e')
                    if isinstance(i, int):
                        selector_map[i] = e
            elif isinstance(sm, dict):
                selector_map = sm
        except Exception:
            selector_map = {}

        tabs: list[TabInfo] = []
        try:
            for t in (browser_payload.get('tabs') or []):
                if not isinstance(t, dict):
                    continue
                tabs.append(
                    TabInfo.model_validate(
                        {
                            'url': t.get('url') or '',
                            'title': t.get('title') or '',
                            'tab_id': t.get('tab_id') or t.get('target_id') or '----',
                        }
                    )
                )
        except Exception:
            tabs = []

        page_info = None
        try:
            pi = browser_payload.get('page_info')
            if isinstance(pi, dict) and pi.get('viewport_width') and pi.get('viewport_height'):
                page_info = PageInfo(
                    viewport_width=int(pi.get('viewport_width') or 0),
                    viewport_height=int(pi.get('viewport_height') or 0),
                    page_width=int(pi.get('page_width') or 0),
                    page_height=int(pi.get('page_height') or 0),
                    scroll_x=int(pi.get('scroll_x') or 0),
                    scroll_y=int(pi.get('scroll_y') or 0),
                    pixels_above=int(pi.get('pixels_above') or 0),
                    pixels_below=int(pi.get('pixels_below') or 0),
                    pixels_left=int(pi.get('pixels_left') or 0),
                    pixels_right=int(pi.get('pixels_right') or 0),
                )
        except Exception:
            page_info = None

        dom_state = RemoteDOMState(dom_text=dom_text, selector_map=selector_map)
        _cloud_agent_log(
            f"[CloudAgent] 📊 Final browser state: url={browser_payload.get('url', 'N/A')[:80]}, "
            f"dom_text={len(dom_text)} chars, tabs={len(tabs)}, selectors={len(selector_map)}"
        )

        return BrowserStateSummary(
            dom_state=dom_state,  # type: ignore[arg-type]
            url=browser_payload.get('url') or '',
            title=browser_payload.get('title') or '',
            tabs=tabs,
            screenshot=browser_payload.get('screenshot_base64'),
            page_info=page_info,
        )

    @staticmethod
    def _reconstruct_dom_text_from_tree(browser_payload: dict[str, Any]) -> str | None:
        """Best-effort extraction of dom_text from dom_tree.

        Supports multiple formats the client may send:
          1. {"dom_text": "...actual page content..."} — direct string wrapper
          2. {"dom_text": "...", ...other keys...} — wrapper with extra metadata
          3. Nested node tree with 'tag', 'children', 'text' — walk to reconstruct
        """
        dom_tree = browser_payload.get('dom_tree')
        if not dom_tree or not isinstance(dom_tree, dict):
            return None

        # Format 1 & 2: dom_tree is a wrapper dict containing 'dom_text' string
        if 'dom_text' in dom_tree:
            dt = dom_tree['dom_text']
            if isinstance(dt, str) and dt.strip():
                _cloud_agent_log(
                    f"[CloudAgent] 🌳 dom_tree contains dom_text string directly: {len(dt)} chars"
                )
                return dt

        # Format 3: Nested node tree — walk to reconstruct text
        lines: list[str] = []

        def _walk(node: Any, depth: int = 0) -> None:
            if not isinstance(node, dict):
                return
            tag = node.get('tag') or node.get('tagName') or ''
            text = (node.get('text') or '').strip()
            attrs = node.get('attributes') or {}
            highlight_index = node.get('highlightIndex')
            is_visible = node.get('isVisible', True)

            if not is_visible and not node.get('children'):
                return

            indent = '  ' * depth
            if highlight_index is not None:
                idx_str = f'[{highlight_index}]'
            else:
                idx_str = ''

            attr_parts = []
            for k, v in (attrs.items() if isinstance(attrs, dict) else []):
                if k in ('href', 'src', 'placeholder', 'aria-label', 'role', 'type', 'value', 'alt', 'title', 'name'):
                    attr_parts.append(f'{k}="{v}"')

            attr_str = ' ' + ' '.join(attr_parts) if attr_parts else ''

            if tag:
                lines.append(f'{indent}{idx_str}<{tag}{attr_str}>{" " + text if text else ""}')
            elif text:
                lines.append(f'{indent}{text}')

            for child in (node.get('children') or []):
                _walk(child, depth + 1)

        root = dom_tree.get('root') or dom_tree.get('node') or dom_tree
        _walk(root)

        if not lines:
            return None
        return '\n'.join(lines)


def make_default_cloud_transport_from_env() -> PassivePubSubTransport:
    transport_kind = os.environ.get('EC_BROWSER_PASSIVE_TRANSPORT', '').strip().lower()
    if transport_kind in {'appsync', 'aws_appsync'}:
        from agent.ec_skills.browser_use_extension.appsync_passive_transport import make_appsync_passive_transport_from_env

        return make_appsync_passive_transport_from_env()

    publish_endpoint = os.environ.get('EC_BROWSER_PASSIVE_PUB_ENDPOINT', '').strip()
    wait_endpoint = os.environ.get('EC_BROWSER_PASSIVE_WAIT_ENDPOINT', '').strip()
    token = os.environ.get('EC_BROWSER_PASSIVE_TOKEN', '').strip() or None
    if not publish_endpoint or not wait_endpoint:
        raise ValueError('Missing EC_BROWSER_PASSIVE_PUB_ENDPOINT / EC_BROWSER_PASSIVE_WAIT_ENDPOINT')
    return HttpPassivePubSubTransport(publish_endpoint=publish_endpoint, wait_endpoint=wait_endpoint, auth_token=token)