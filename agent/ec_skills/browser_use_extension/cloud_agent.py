import asyncio
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

    def deliver_result(self, result: PassiveBrowserStepResult) -> None:
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

    async def run(
        self,
        max_steps: int = 100,
        on_step_start=None,
        on_step_end=None,
    ):
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

            bootstrap = await self._remote_step(
                actions=actions,
                include_screenshot=True,
                step_id="bootstrap",
            )
            self._next_state_from_client = bootstrap.browser

        while self.state.n_steps <= max_steps:
            current_step = self.state.n_steps - 1
            step_info = AgentStepInfo(step_number=current_step, max_steps=max_steps)
            is_done = await self._execute_step(current_step, max_steps, step_info, on_step_start, on_step_end)
            if is_done:
                return self.history
        return self.history

    async def _prepare_context(self, step_info: AgentStepInfo | None = None) -> BrowserStateSummary:
        # If we already have a post-action snapshot from previous step, use it.
        if self._next_state_from_client is None:
            raise RuntimeError(
                'CloudAgent requires a cached remote observation before calling step(). '
                'Call CloudAgent.run(...) which primes an initial observation, '
                'or set _next_state_from_client from a PassiveBrowserStepResult before stepping.'
            )

        browser_state_summary = self._browser_state_from_payload(self._next_state_from_client)
        self._next_state_from_client = None

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

    async def _execute_actions(self) -> None:
        if self.state.last_model_output is None:
            raise ValueError('No model output to execute actions from')

        actions = []
        try:
            for a in (self.state.last_model_output.action or []):
                actions.append(a.model_dump(exclude_unset=True))
        except Exception:
            actions = []

        result = await self._remote_step(actions=actions, include_screenshot=False, step_id=f"step-{self.state.n_steps}")

        parsed_results: list[ActionResult] = []
        for r in (result.action_results or []):
            try:
                parsed_results.append(ActionResult.model_validate(r))
            except Exception:
                parsed_results.append(ActionResult(error=str(r)))

        self.state.last_result = parsed_results
        self._next_state_from_client = result.browser

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
    ) -> PassiveBrowserStepResult:
        cmd = PassiveBrowserCommand(
            run_id=self.run_id,
            step_id=step_id,
            acct_site_id=self.acct_site_id,
            agent_id=self.cloud_agent_id,
            skill_id=self.skill_id,
            node_id=self.node_id,
            actions=actions,
            include_screenshot=include_screenshot,
            stop_on_error=True,
        )

        await self.transport.publish_command(cmd)
        timeout_s = float(getattr(self.settings, 'step_timeout', 180) or 180)
        return await self.transport.wait_for_result(run_id=self.run_id, step_id=step_id, timeout_s=timeout_s)

    def _browser_state_from_payload(self, browser_payload: dict[str, Any] | None) -> BrowserStateSummary:
        browser_payload = browser_payload or {}

        dom_text = browser_payload.get('dom_text') or ''
        selector_map: dict[int, Any] = {}
        try:
            sm = browser_payload.get('selector_map')
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

        return BrowserStateSummary(
            dom_state=dom_state,  # type: ignore[arg-type]
            url=browser_payload.get('url') or '',
            title=browser_payload.get('title') or '',
            tabs=tabs,
            screenshot=browser_payload.get('screenshot_base64'),
            page_info=page_info,
        )


def make_default_cloud_transport_from_env() -> HttpPassivePubSubTransport:
    publish_endpoint = os.environ.get('EC_BROWSER_PASSIVE_PUB_ENDPOINT', '').strip()
    wait_endpoint = os.environ.get('EC_BROWSER_PASSIVE_WAIT_ENDPOINT', '').strip()
    token = os.environ.get('EC_BROWSER_PASSIVE_TOKEN', '').strip() or None
    if not publish_endpoint or not wait_endpoint:
        raise ValueError('Missing EC_BROWSER_PASSIVE_PUB_ENDPOINT / EC_BROWSER_PASSIVE_WAIT_ENDPOINT')
    return HttpPassivePubSubTransport(publish_endpoint=publish_endpoint, wait_endpoint=wait_endpoint, auth_token=token)