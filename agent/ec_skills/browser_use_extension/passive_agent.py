import os
import time
from typing import Any, Optional

from utils.logger_helper import logger_helper as logger

from agent.ec_skills.browser_use_extension.privacy import RegexMaskFilter, PrivacyFilter, load_privacy_config

try:
    from browser_use import BrowserSession, BrowserProfile
    from browser_use.browser.views import BrowserStateSummary
    from browser_use.tools.service import Tools
    from browser_use.agent.views import ActionResult
except Exception:
    BrowserSession = None  # type: ignore
    BrowserProfile = None  # type: ignore
    BrowserStateSummary = None  # type: ignore
    Tools = None  # type: ignore
    ActionResult = None  # type: ignore


class PassiveAgent:
    """A minimal/passive browser-use runner.

    This agent does *not* call an LLM and does *not* build any browser-use message history.

    It only:
    - starts/owns a BrowserSession
    - executes provided action dicts (single or multi action list)
    - captures the browser state (already pruned by browser-use's DOM serializer)
    - optionally applies privacy filtering (RegexMaskFilter / custom PrivacyFilter)

    Cloud transport is intentionally left undefined: you can later send the returned payload via
    websocket/HTTP.
    """

    def __init__(
        self,
        *,
        browser_profile: "BrowserProfile | None" = None,
        browser_session: "BrowserSession | None" = None,
        tools: "Tools | None" = None,
        privacy_enabled: bool = True,
        privacy_filter: "PrivacyFilter | None" = None,
        include_attributes: list[str] | None = None,
    ) -> None:
        if BrowserSession is None or Tools is None:
            raise ImportError("browser-use is not available in this environment")

        self.include_attributes = include_attributes

        self.browser_session: BrowserSession = browser_session or BrowserSession(
            browser_profile=browser_profile or BrowserProfile(),
        )
        self.tools: Tools = tools or Tools()

        self.privacy_enabled = bool(privacy_enabled)
        if privacy_filter is not None:
            self.privacy_filter = privacy_filter
        else:
            self.privacy_filter = RegexMaskFilter(load_privacy_config())

        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await self.browser_session.start()
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        try:
            await self.browser_session.stop()
        finally:
            self._started = False

    def _action_result_to_dict(self, r: Any) -> dict[str, Any]:
        if r is None:
            return {}
        if hasattr(r, "model_dump"):
            return r.model_dump()
        if hasattr(r, "dict"):
            return r.dict()
        if isinstance(r, dict):
            return r
        return {"raw": str(r)}

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

    def _compact_selector_map(self, selector_map: Any, *, max_elems: int = 250) -> list[dict[str, Any]]:
        try:
            items: list[dict[str, Any]] = []
            if not isinstance(selector_map, dict):
                return items

            for k, v in list(selector_map.items())[:max_elems]:
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
                    keep: dict[str, Any] = {}
                    for kk in (
                        "id",
                        "name",
                        "type",
                        "role",
                        "href",
                        "placeholder",
                        "aria-label",
                        "aria_label",
                        "value",
                    ):
                        if kk in attrs and attrs.get(kk) is not None:
                            keep[kk] = self._truncate_text(attrs.get(kk), 120)
                    d["attributes"] = keep

                if "text" in d:
                    d["text"] = self._truncate_text(d.get("text"), 200)
                if "xpath" in d:
                    d["xpath"] = self._truncate_text(d.get("xpath"), 400)

                items.append({"i": k, "e": d})

            return items
        except Exception:
            logger.error("[PassiveAgent] Failed to compact selector_map", exc_info=True)
            return []

    def _build_dom_payload(self, browser_state_summary: Any) -> dict[str, Any]:
        url = getattr(browser_state_summary, "url", None)
        title = getattr(browser_state_summary, "title", None)
        dom_state = getattr(browser_state_summary, "dom_state", None)

        dom_text = None
        try:
            if dom_state is not None and hasattr(dom_state, "llm_representation"):
                dom_text = dom_state.llm_representation(include_attributes=self.include_attributes)
        except Exception:
            dom_text = None

        selector_map = getattr(dom_state, "selector_map", None) if dom_state is not None else None

        return {
            "url": self._truncate_text(url, 1024),
            "title": self._truncate_text(title, 256),
            "dom_text": self._truncate_text(dom_text, 200000) if dom_text else None,
            "selector_map": self._compact_selector_map(selector_map),
        }

    async def capture_state(self, *, include_screenshot: bool = False) -> "BrowserStateSummary":
        await self.start()
        return await self.browser_session.get_browser_state_summary(
            include_screenshot=include_screenshot,
            include_recent_events=False,
        )

    async def execute_actions(
        self,
        actions: list[dict[str, dict[str, Any]]] | None = None,
        *,
        stop_on_error: bool = True,
        include_screenshot: bool = False,
    ) -> dict[str, Any]:
        """Execute an externally-provided list of actions and return a payload.

        `actions` format example:
            [{"click": {"index": 5}}, {"input": {"index": 5, "text": "hello"}}]

        This does NOT call LLM.
        """
        await self.start()

        t0 = time.perf_counter()

        results: list[ActionResult] = []
        errors: list[str] = []

        for i, action_dict in enumerate(actions or []):
            if not isinstance(action_dict, dict) or not action_dict:
                continue

            action_name = next(iter(action_dict.keys()))
            params = action_dict.get(action_name) or {}

            # Keep action schema in sync with current page
            try:
                page_url = await self.browser_session.get_current_page_url()
            except Exception:
                page_url = None

            try:
                ActionModelType = self.tools.registry.create_action_model(page_url=page_url)
                action_model = ActionModelType.model_validate(action_dict) if hasattr(ActionModelType, "model_validate") else ActionModelType(**action_dict)

                r = await self.tools.act(
                    action=action_model,
                    browser_session=self.browser_session,
                    page_extraction_llm=None,
                    sensitive_data=None,
                    available_file_paths=None,
                    file_system=None,
                )

            except Exception as e:
                msg = f"action[{i}] '{action_name}' failed: {type(e).__name__}: {e}"
                logger.error(f"[PassiveAgent] {msg}", exc_info=True)
                r = ActionResult(error=msg)

            results.append(r)

            if r.error:
                errors.append(r.error)
                if stop_on_error:
                    break
            if r.is_done:
                break

        # Capture state AFTER action(s) (or capture-only if actions is empty)
        browser_state = await self.capture_state(include_screenshot=include_screenshot)

        # Apply privacy filtering (redacts dom_state/_root/selector_map + url/title)
        filtered_state = browser_state
        if self.privacy_enabled and self.privacy_filter is not None:
            try:
                fr = self.privacy_filter.filter_browser_state(browser_state, getattr(browser_state, "url", "") or "")
                filtered_state = fr.filtered_data
            except Exception:
                logger.error("[PassiveAgent] privacy filtering failed", exc_info=True)
                filtered_state = browser_state

        tabs_payload = None
        try:
            tabs_payload = []
            for t in (getattr(filtered_state, "tabs", None) or []):
                try:
                    tabs_payload.append(
                        {
                            "tab_id": getattr(t, "target_id", None) or getattr(t, "tab_id", None),
                            "url": getattr(t, "url", None),
                            "title": getattr(t, "title", None),
                        }
                    )
                except Exception:
                    continue
        except Exception:
            tabs_payload = None

        page_info_payload = None
        try:
            pi = getattr(filtered_state, "page_info", None)
            if pi is not None:
                page_info_payload = {
                    "viewport_width": getattr(pi, "viewport_width", None),
                    "viewport_height": getattr(pi, "viewport_height", None),
                    "page_width": getattr(pi, "page_width", None),
                    "page_height": getattr(pi, "page_height", None),
                    "scroll_x": getattr(pi, "scroll_x", None),
                    "scroll_y": getattr(pi, "scroll_y", None),
                    "pixels_above": getattr(pi, "pixels_above", None),
                    "pixels_below": getattr(pi, "pixels_below", None),
                    "pixels_left": getattr(pi, "pixels_left", None),
                    "pixels_right": getattr(pi, "pixels_right", None),
                }
        except Exception:
            page_info_payload = None

        payload = {
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "actions": actions or [],
            "action_results": [self._action_result_to_dict(r) for r in results],
            "errors": errors,
            "browser": {
                **self._build_dom_payload(filtered_state),
                "tabs": tabs_payload,
                "page_info": page_info_payload,
                "screenshot_base64": getattr(filtered_state, "screenshot", None) if include_screenshot else None,
            },
        }

        return payload
