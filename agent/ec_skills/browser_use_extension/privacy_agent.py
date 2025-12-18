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
from typing import Any, Callable, Awaitable, Literal

from utils.logger_helper import logger_helper as logger

# Import browser-use components
try:
    from browser_use import Agent, BrowserSession, BrowserProfile
    from browser_use.agent.views import (
        AgentStepInfo,
        AgentState,
        AgentStructuredOutput,
    )
    from browser_use.browser.views import BrowserStateSummary
    from browser_use.llm.base import BaseChatModel
    from browser_use.tools.service import Tools
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    logger.warning("browser-use not available, PrivacyAgent will not work")

# Import privacy components
from .privacy import (
    PrivacyFilter,
    RegexMaskFilter,
    FilterResult,
    PrivacyConfig,
    load_privacy_config,
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
        
        status = "enabled" if self.privacy_enabled else "DISABLED (passthrough mode)"
        debug_status = "debug=on" if self.privacy_debug else "debug=off"
        delay_status = (
            f"step_delay={self.privacy_step_delay_seconds}s"
            if (self.privacy_step_delay_seconds is not None and self.privacy_step_delay_seconds > 0)
            else "step_delay=off"
        )
        logger.info(f"[PrivacyAgent] Initialized with privacy filtering {status} ({debug_status}, {delay_status})")
    
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
            self._agent._message_manager.create_state_messages(
                browser_state_summary=filtered_state,
                model_output=self._agent.state.last_model_output,
                result=self._agent.state.last_result,
                step_info=step_info,
                use_vision=self._agent.settings.use_vision,
                page_filtered_actions=None,  # Will be re-added if needed
                sensitive_data=self._agent.sensitive_data,
                available_file_paths=self._agent.available_file_paths,
            )

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
    
    async def run(self, max_steps: int = 100) -> Any:
        """
        Run the agent with privacy filtering.
        
        Args:
            max_steps: Maximum number of steps to run
            
        Returns:
            Agent result (AgentHistoryList)
        """
        return await self._agent.run(max_steps=max_steps)
    
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
    
    # Proxy commonly used Agent properties and methods
    
    @property
    def task(self) -> str:
        return self._agent.task
    
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
