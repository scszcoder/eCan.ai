import asyncio
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
        self._last_focus_target_id: str | None = None  # Track tab from previous step
        self._file_system = None  # Lazy-init on first action that needs it

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

    @staticmethod
    def _describe_element(node: Any, max_text: int = 120) -> str:
        """Extract a short human-readable description from an EnhancedDOMTreeNode."""
        try:
            tag = getattr(node, "node_name", "?") or "?"
            attrs = getattr(node, "attributes", {}) or {}
            href = attrs.get("href", "")
            title = attrs.get("title", "")
            aria_label = attrs.get("aria-label", "")
            placeholder = attrs.get("placeholder", "")

            # Collect visible text from the node and its immediate children
            texts: list[str] = []
            nv = getattr(node, "node_value", None)
            if nv and str(nv).strip():
                texts.append(str(nv).strip())
            for child in (getattr(node, "children_nodes", None) or []):
                cv = getattr(child, "node_value", None)
                if cv and str(cv).strip():
                    texts.append(str(cv).strip())
                # one level deeper for nested text
                for gc in (getattr(child, "children_nodes", None) or []):
                    gv = getattr(gc, "node_value", None)
                    if gv and str(gv).strip():
                        texts.append(str(gv).strip())
            inner_text = " ".join(texts)[:max_text] if texts else ""

            parts = [f"<{tag}>"]
            if inner_text:
                parts.append(f'text="{inner_text}"')
            if href:
                parts.append(f'href="{href[:200]}"')
            if title:
                parts.append(f'title="{title[:100]}"')
            if aria_label:
                parts.append(f'aria-label="{aria_label[:100]}"')
            if placeholder:
                parts.append(f'placeholder="{placeholder[:100]}"')
            target_attr = attrs.get("target", "")
            if target_attr:
                parts.append(f'target="{target_attr}"')
            return " ".join(parts)
        except Exception:
            return "<unknown>"

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

        # --- Fix E: Tab-focus stabilisation ---
        # browser-use's _click_element_node_impl has a `finally` block that calls
        # get_or_create_cdp_session(focus=True) with no target_id.  If the click
        # triggers a page navigation that briefly detaches the CDP session, the
        # recovery mechanism picks the *first* available page target (e.g. Amazon)
        # instead of the intended tab (e.g. Taobao).  This corrupts
        # agent_focus_target_id, and capture_state then returns the wrong tab's DOM.
        #
        # We fix this by:
        #   1. Recording the "intended" focus target before actions run.
        #   2. Updating it when actions explicitly change tabs (switch_tab, go_to_url).
        #   3. Force-restoring focus to the intended target *after* all actions,
        #      right before capture_state.
        #   4. Saving _last_focus_target_id from the intended target, not from the
        #      potentially-corrupted agent_focus_target_id.

        from browser_use.browser.events import SwitchTabEvent

        # Restore tab focus from previous step before ANY actions.
        # Between steps, browser focus can drift to other tabs (session recreation
        # resets agent_focus_target_id to the first page target, user interaction, JS popups).
        # We always restore focus first, then optionally refresh DOM for element actions.
        if actions and self._last_focus_target_id and self.browser_session.agent_focus_target_id != self._last_focus_target_id:
            try:
                current_short = self.browser_session.agent_focus_target_id[-4:] if self.browser_session.agent_focus_target_id else "None"
                target_short = self._last_focus_target_id[-4:]
                logger.info(f"[PassiveAgent] Tab drift detected: current=...{current_short} → restoring to ...{target_short}")
                await self.browser_session.event_bus.dispatch(SwitchTabEvent(target_id=self._last_focus_target_id))
                logger.info(f"[PassiveAgent] Tab focus restored to ...{target_short}")
            except Exception as e:
                logger.warning(f"[PassiveAgent] Failed to restore tab focus: {e}, continuing on current tab")

        # Refresh DOM before element actions to repopulate selector_map from the (now correct) tab.
        if actions:
            has_element_actions = any(
                action_name in ("click", "input", "input_text", "scroll", "scroll_to_element", "drag_drop", "select_option", "select_dropdown", "dropdown_options")
                for action_dict in actions
                if isinstance(action_dict, dict)
                for action_name in action_dict.keys()
            )
            if has_element_actions:
                try:
                    logger.debug("[PassiveAgent] Refreshing DOM before element actions to repopulate selector_map")
                    await self.browser_session.get_browser_state_summary(include_screenshot=False)
                    logger.debug("[PassiveAgent] DOM refresh complete, selector_map repopulated")
                except Exception as e:
                    logger.warning(f"[PassiveAgent] DOM refresh failed: {e}, continuing with potentially stale selector_map")

        # Track the focus target that actions set.  After each action we snapshot
        # agent_focus_target_id so we know the *intended* tab.  If a background CDP
        # event reverts focus between the last action and capture_state, we re-assert.
        # Initialize from _last_focus_target_id so actions that don't change tabs
        # (e.g. scroll, wait) still preserve the correct intended tab.
        intended_focus_target_id: str | None = self._last_focus_target_id
        logger.debug(
            f"[PassiveAgent] Pre-action focus: agent=...{self.browser_session.agent_focus_target_id[-4:] if self.browser_session.agent_focus_target_id else 'None'}, "
            f"intended=...{intended_focus_target_id[-4:] if intended_focus_target_id else 'None'}"
        )

        results: list[ActionResult] = []
        errors: list[str] = []

        for i, action_dict in enumerate(actions or []):
            if not isinstance(action_dict, dict) or not action_dict:
                continue

            action_name = next(iter(action_dict.keys()))
            params = action_dict.get(action_name) or {}

            # Normalize switch action: cloud agent may send full 32-char target_id
            # but browser_use's SwitchActionModel expects max 4-char tab_id suffix.
            # Truncate to last 4 chars so validation passes.
            if action_name == "switch" and isinstance(params, dict):
                raw_tab_id = params.get("tab_id", "")
                if isinstance(raw_tab_id, str) and len(raw_tab_id) > 4:
                    short_id = raw_tab_id[-4:]
                    logger.info(f"[PassiveAgent] Truncating switch tab_id: {raw_tab_id} → ...{short_id}")
                    params["tab_id"] = short_id
                    action_dict[action_name] = params

            # Log element details for actions that target an element index
            # Also capture href + target for click actions so we can fall back to
            # explicit navigation when the JS click doesn't honour target="_blank".
            click_href: str = ""
            click_target: str = ""
            if action_name in ("click", "input", "scroll", "input_text", "scroll_to_element", "drag_drop", "select_option", "select_dropdown") and isinstance(params, dict):
                elem_index = params.get("index")
                if elem_index is not None:
                    try:
                        node = self.browser_session._cached_selector_map.get(int(elem_index))
                        if node:
                            desc = self._describe_element(node)
                            logger.info(f"[PassiveAgent] 🎯 {action_name}(index={elem_index}): {desc}")
                            # Capture href/target for click fallback
                            if action_name == "click":
                                node_attrs = getattr(node, "attributes", {}) or {}
                                click_href = node_attrs.get("href", "") or ""
                                click_target = node_attrs.get("target", "") or ""
                        else:
                            map_size = len(self.browser_session._cached_selector_map) if self.browser_session._cached_selector_map else 0
                            logger.warning(f"[PassiveAgent] ⚠️ {action_name}(index={elem_index}): NOT FOUND in selector_map (size={map_size})")
                    except Exception as e:
                        logger.debug(f"[PassiveAgent] Could not describe element {elem_index}: {e}")

            # Snapshot tab IDs before the action so we can detect new tabs opened
            # by JS (e.g. send_keys(Enter) on 1688.com opens search results in a new tab).
            tabs_before: set[str] = set()
            if action_name in ("send_keys", "click", "input", "input_text"):
                try:
                    sm = self.browser_session.session_manager
                    if sm:
                        all_targets = sm.get_all_targets()
                        tabs_before = {
                            tid for tid, t in all_targets.items()
                            if getattr(t, "target_type", "") in ("page", "tab")
                        }
                        logger.debug(
                            f"[PassiveAgent] Pre-action tab snapshot for '{action_name}': "
                            f"{len(tabs_before)} page/tab targets out of {len(all_targets)} total"
                        )
                    else:
                        logger.debug(f"[PassiveAgent] session_manager is None, skipping tab snapshot for '{action_name}'")
                except Exception as e:
                    logger.debug(f"[PassiveAgent] Tab snapshot failed for '{action_name}': {e}")

            # Keep action schema in sync with current page
            try:
                page_url = await self.browser_session.get_current_page_url()
            except Exception:
                page_url = None

            try:
                ActionModelType = self.tools.registry.create_action_model(page_url=page_url)
                action_model = ActionModelType.model_validate(action_dict) if hasattr(ActionModelType, "model_validate") else ActionModelType(**action_dict)

                # Lazy-init FileSystem so done/write_file/read_file actions work
                if self._file_system is None:
                    try:
                        from browser_use.filesystem.file_system import FileSystem
                        import tempfile
                        fs_dir = os.path.join(tempfile.gettempdir(), "passive_agent_fs")
                        self._file_system = FileSystem(base_dir=fs_dir)
                        logger.debug(f"[PassiveAgent] FileSystem initialized at {fs_dir}")
                    except Exception as fs_e:
                        logger.warning(f"[PassiveAgent] Could not init FileSystem: {fs_e}")

                r = await self.tools.act(
                    action=action_model,
                    browser_session=self.browser_session,
                    page_extraction_llm=None,
                    sensitive_data=None,
                    available_file_paths=None,
                    file_system=self._file_system,
                )

            except Exception as e:
                msg = f"action[{i}] '{action_name}' failed: {type(e).__name__}: {e}"
                logger.error(f"[PassiveAgent] {msg}", exc_info=True)
                r = ActionResult(error=msg)

            # Detect new tabs opened by JS after the action (e.g. send_keys Enter
            # on 1688.com opens search results in a new tab, or click on a product
            # link with target="_blank" via tracking redirect).  Poll for up to 2s
            # because some sites (1688) route clicks through tracking URLs that
            # add latency before the new tab actually appears in CDP.
            if tabs_before and r and not r.error:
                try:
                    new_tabs: set[str] = set()
                    sm = self.browser_session.session_manager
                    if sm:
                        for _poll in range(4):  # 4 × 0.5s = 2s max
                            await asyncio.sleep(0.5)
                            tabs_after = {
                                tid for tid, t in sm.get_all_targets().items()
                                if getattr(t, "target_type", "") in ("page", "tab")
                            }
                            new_tabs = tabs_after - tabs_before
                            if new_tabs:
                                break
                        if new_tabs:
                            new_tab_id = next(iter(new_tabs))
                            new_tab_target = sm.get_target(new_tab_id)
                            new_tab_url = getattr(new_tab_target, "url", "") if new_tab_target else ""
                            logger.info(
                                f"[PassiveAgent] 🆕 New tab detected after '{action_name}': "
                                f"...{new_tab_id[-4:]} url={new_tab_url[:120]}"
                            )
                            await self.browser_session.event_bus.dispatch(SwitchTabEvent(target_id=new_tab_id))
                            logger.info(f"[PassiveAgent] Auto-switched focus to new tab ...{new_tab_id[-4:]}")
                        else:
                            logger.debug(f"[PassiveAgent] No new tab after '{action_name}' (polled 2s)")
                            # Fallback: if we clicked a target="_blank" link but no new
                            # tab appeared (because the JS this.click() fallback doesn't
                            # honour target="_blank"), explicitly navigate to the href
                            # in a new tab so the user ends up on the right page.
                            if action_name == "click" and click_target == "_blank" and click_href:
                                try:
                                    from browser_use.browser.events import NavigateToUrlEvent
                                    logger.info(
                                        f"[PassiveAgent] 🔗 Fallback: navigating to href in new tab "
                                        f"(target=_blank click didn't open tab): {click_href[:200]}"
                                    )
                                    nav_event = NavigateToUrlEvent(url=click_href, new_tab=True)
                                    await self.browser_session.event_bus.dispatch(nav_event)
                                    # Wait briefly for the navigation to complete
                                    await asyncio.sleep(1.0)
                                    # Re-check for new tabs after explicit navigation
                                    tabs_after_nav = {
                                        tid for tid, t in sm.get_all_targets().items()
                                        if getattr(t, "target_type", "") in ("page", "tab")
                                    }
                                    nav_new_tabs = tabs_after_nav - tabs_before
                                    if nav_new_tabs:
                                        nav_tab_id = next(iter(nav_new_tabs))
                                        nav_target = sm.get_target(nav_tab_id)
                                        nav_url = getattr(nav_target, "url", "") if nav_target else ""
                                        logger.info(
                                            f"[PassiveAgent] 🆕 Fallback nav opened tab: "
                                            f"...{nav_tab_id[-4:]} url={nav_url[:120]}"
                                        )
                                        await self.browser_session.event_bus.dispatch(SwitchTabEvent(target_id=nav_tab_id))
                                        logger.info(f"[PassiveAgent] Auto-switched focus to fallback tab ...{nav_tab_id[-4:]}")
                                except Exception as nav_e:
                                    logger.warning(f"[PassiveAgent] Fallback navigation failed: {nav_e}")
                except Exception as e:
                    logger.debug(f"[PassiveAgent] New-tab detection failed: {e}")

            # Detect silently-failed switch actions.
            # browser_use's switch handler catches ValueError (tab_id not found) and
            # returns ActionResult with "Attempted to switch" but NO error field.
            # Convert to a real error so the cloud agent knows the switch failed.
            if action_name == "switch" and r and not r.error:
                content = getattr(r, "extracted_content", "") or ""
                if "Attempted to switch" in content:
                    tab_id_param = params.get("tab_id", "?") if isinstance(params, dict) else "?"
                    r = ActionResult(
                        error=f"Switch failed: tab_id '{tab_id_param}' not found (target may have changed between sessions)",
                        extracted_content=content,
                    )
                    logger.warning(f"[PassiveAgent] Switch action silently failed for tab_id={tab_id_param}, converting to error")

            # After a successful switch, refresh DOM so subsequent element actions
            # (input, click, etc.) in the same batch get the correct selector_map
            # for the newly-focused tab.  Without this, indices from the old tab's
            # DOM cause "Element index N not available" errors.
            if action_name == "switch" and r and not r.error:
                try:
                    logger.info("[PassiveAgent] Post-switch DOM refresh to update selector_map for new tab")
                    await self.browser_session.get_browser_state_summary(include_screenshot=False)
                    logger.info("[PassiveAgent] Post-switch DOM refresh complete")
                except Exception as e:
                    logger.warning(f"[PassiveAgent] Post-switch DOM refresh failed: {e}, subsequent element actions may fail")

            results.append(r)

            # After every action, snapshot the current focus as the "intended" tab.
            # This captures focus changes from switch, navigate, click-opens-new-tab, etc.
            new_focus = self.browser_session.agent_focus_target_id
            if new_focus and new_focus != intended_focus_target_id:
                if intended_focus_target_id is not None:
                    logger.info(
                        f"[PassiveAgent] Action '{action_name}' changed focus: "
                        f"...{intended_focus_target_id[-4:]} → ...{new_focus[-4:]}"
                    )
                intended_focus_target_id = new_focus

            if r.error:
                errors.append(r.error)
                if stop_on_error:
                    break
            if r.is_done:
                break

        # --- Fix E (cont.): Force-restore focus before capture_state ---
        # After actions, agent_focus_target_id may have silently reverted to the
        # wrong tab due to CDP session detach/reattach recovery.  Re-assert the
        # intended focus so capture_state returns the correct tab's DOM.
        if intended_focus_target_id and self.browser_session.agent_focus_target_id != intended_focus_target_id:
            try:
                cur_short = self.browser_session.agent_focus_target_id[-4:] if self.browser_session.agent_focus_target_id else "None"
                want_short = intended_focus_target_id[-4:]
                logger.warning(
                    f"[PassiveAgent] Focus reverted after actions: current=...{cur_short}, "
                    f"intended=...{want_short}. Re-asserting focus."
                )
                await self.browser_session.event_bus.dispatch(SwitchTabEvent(target_id=intended_focus_target_id))
                logger.info(f"[PassiveAgent] Focus re-asserted to ...{want_short}")
            except Exception as e:
                logger.warning(f"[PassiveAgent] Failed to re-assert focus: {e}, capture_state may use wrong tab")

        # Capture state AFTER action(s) (or capture-only if actions is empty)
        # Always capture without screenshot — screenshot data is too large for
        # local state/logs and the cloud agent doesn't need it from the local side.
        browser_state = await self.capture_state(include_screenshot=False)

        # Save the *intended* focus target (not the potentially-corrupted agent_focus_target_id)
        # so the next step's restore logic uses the correct tab.
        self._last_focus_target_id = intended_focus_target_id or self.browser_session.agent_focus_target_id
        logger.debug(f"[PassiveAgent] Saved focus target_id: ...{self._last_focus_target_id[-4:] if self._last_focus_target_id else 'None'}")

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
                "screenshot_base64": None,
            },
        }

        return payload
