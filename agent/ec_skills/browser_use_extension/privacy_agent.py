"""
PrivacyAgent & PrivacyControllableAgent - Privacy-preserving browser-use Agents.

This module provides:
1. PrivacyAgent - Composition-based wrapper (original, for backward compatibility)
2. PrivacyControllableAgent - Inheritance-based subclass with:
   - Single-step control (step_once, run_with_control)
   - Context injection points (RAG, custom context)
   - Privacy filtering
   - History extraction for episodic memory

Usage (PrivacyAgent - original):
    from agent.ec_skills.browser_use_extension.privacy_agent import PrivacyAgent
    
    agent = PrivacyAgent(
        task="Navigate to bank website",
        llm=my_llm,
        privacy_enabled=True,
    )
    result = await agent.run()

Usage (PrivacyControllableAgent - with step control):
    from agent.ec_skills.browser_use_extension.privacy_agent import (
        PrivacyControllableAgent,
        StepControl,
    )
    
    async def my_step_controller(agent, step_num, browser_state, action):
        # Query RAG, decide to continue, inject context, etc.
        return StepControl(inject_context="relevant knowledge here")
    
    agent = PrivacyControllableAgent(
        task="Navigate to website",
        llm=my_llm,
        step_control_callback=my_step_controller,
        privacy_enabled=True,
    )
    
    # Run with step-by-step control
    result = await agent.run_with_control(max_steps=50)
    
    # Or run single steps manually
    step_data = await agent.step_once()
"""

import asyncio
import copy
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Literal, TYPE_CHECKING

from utils.logger_helper import logger_helper as logger

# Import browser-use components
try:
    from browser_use import Agent, BrowserSession, BrowserProfile
    from browser_use.agent.views import (
        AgentStepInfo,
        AgentState,
        AgentStructuredOutput,
        AgentHistoryList,
        AgentOutput,
        ActionResult,
    )
    from browser_use.browser.views import BrowserStateSummary
    from browser_use.llm.base import BaseChatModel
    from browser_use.tools.service import Tools
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    Agent = object  # Fallback for type hints
    logger.warning("browser-use not available, PrivacyAgent will not work")

if TYPE_CHECKING:
    from browser_use.agent.views import AgentHistoryList, AgentOutput, ActionResult

# Import privacy components
from .privacy import (
    PrivacyFilter,
    RegexMaskFilter,
    FilterResult,
    PrivacyConfig,
    load_privacy_config,
)


# =============================================================================
# Type definitions for step control
# =============================================================================

@dataclass
class StepData:
    """Data returned after each step for control decisions."""
    is_done: bool
    step_number: int
    browser_state: "BrowserStateSummary | None"
    action: "AgentOutput | None"
    result: "list[ActionResult] | None"
    url: str | None
    title: str | None
    thinking: str | None
    next_goal: str | None
    error: str | None = None


@dataclass
class StepControl:
    """Control signals returned from step callback."""
    stop: bool = False
    new_task: str | None = None
    inject_context: str | None = None
    handoff_to: str | None = None
    metadata: dict = field(default_factory=dict)


# Type for step control callback
StepControlCallback = Callable[
    ["PrivacyControllableAgent", int, "BrowserStateSummary | None", "AgentOutput | None"],
    Awaitable[StepControl | dict | None]
]


# =============================================================================
# PrivacyControllableAgent - Inheritance-based with single-step control
# =============================================================================

class PrivacyControllableAgent(Agent):
    """
    Privacy-preserving, single-step controllable browser-use Agent.
    
    Combines:
    - Privacy filtering (regex-based, extensible)
    - Single-step control (step_once, run_with_control)
    - Context injection (RAG, custom knowledge)
    - History extraction (for episodic memory/reflection)
    
    Key features:
    - Inherits from browser-use Agent (full access to internals)
    - step_once() for manual single-step execution
    - run_with_control() for callback-based step control
    - Context injection via _injected_context
    - Privacy filtering in _prepare_context override
    """
    
    def __init__(
        self,
        task: str,
        llm: "BaseChatModel | None" = None,
        # Privacy settings
        privacy_filter: "PrivacyFilter | None" = None,
        privacy_config: "PrivacyConfig | None" = None,
        privacy_enabled: bool = True,
        # Control settings
        step_control_callback: StepControlCallback | None = None,
        context_builder: Any = None,  # Your ContextBuilder instance
        rag_client: Any = None,  # Your RAG client (e.g., LightRAG)
        history_recorder: Any = None,  # Your history recorder
        # All other Agent parameters
        **kwargs,
    ):
        """
        Initialize PrivacyControllableAgent.
        
        Args:
            task: The task description
            llm: Language model to use
            privacy_filter: Custom privacy filter (default: RegexMaskFilter)
            privacy_config: Privacy configuration
            privacy_enabled: If False, bypasses privacy filtering
            step_control_callback: Async callback called after each step
            context_builder: Your ContextBuilder for structured context
            rag_client: Your RAG client for knowledge retrieval
            history_recorder: Your recorder for episodic memory
            **kwargs: All other browser-use Agent arguments
        """
        if not BROWSER_USE_AVAILABLE:
            raise ImportError(
                "browser-use is not installed. Install it with: pip install browser-use"
            )
        
        # Initialize parent Agent
        super().__init__(task=task, llm=llm, **kwargs)
        
        # Privacy settings
        self.privacy_enabled = privacy_enabled
        if privacy_filter is not None:
            self.privacy_filter = privacy_filter
        else:
            config = privacy_config or load_privacy_config()
            self.privacy_filter = RegexMaskFilter(config)
        
        # Control settings
        self.step_control_callback = step_control_callback
        self.context_builder = context_builder
        self.rag_client = rag_client
        self.history_recorder = history_recorder
        
        # Internal state
        self._should_continue = True
        self._injected_context: str | None = None
        self._filter_results: list[FilterResult] = []
        self._last_browser_state: "BrowserStateSummary | None" = None
        
        status = "enabled" if self.privacy_enabled else "DISABLED (passthrough)"
        logger.info(f"[PrivacyControllableAgent] Initialized with privacy {status}")
    
    # =========================================================================
    # SINGLE-STEP CONTROL
    # =========================================================================
    
    async def step_once(self, step_info: "AgentStepInfo | None" = None) -> StepData:
        """
        Execute exactly ONE step and return control to caller.
        
        This gives you full control between steps to:
        - Query RAG for relevant knowledge
        - Consult another agent
        - Modify the task
        - Stop early
        
        Args:
            step_info: Optional step info (created automatically if None)
            
        Returns:
            StepData with step results and state
        """
        # Create step_info if not provided
        if step_info is None:
            step_info = AgentStepInfo(
                step_number=self.state.n_steps - 1,
                max_steps=100
            )
        
        # Pre-step: Inject context if available
        await self._pre_step_inject_context()
        
        # Execute browser-use's step
        error = None
        try:
            await self.step(step_info)
        except Exception as e:
            error = str(e)
            logger.error(f"[PrivacyControllableAgent] Step error: {e}")
        
        # Post-step: Extract data
        step_data = self._extract_step_data(error)
        
        # Record to history if recorder provided
        if self.history_recorder:
            try:
                await self.history_recorder.record_step(step_data)
            except Exception as e:
                logger.warning(f"[PrivacyControllableAgent] History recording failed: {e}")
        
        return step_data
    
    async def run_with_control(
        self,
        max_steps: int = 100,
    ) -> "AgentHistoryList":
        """
        Run with step-by-step control via callback.
        
        Your callback receives (agent, step_num, browser_state, action)
        and can return StepControl or dict with:
        - stop: bool - Stop execution
        - new_task: str - Add new task instructions
        - inject_context: str - Inject context for next step
        - handoff_to: str - Signal handoff to another agent
        
        Args:
            max_steps: Maximum steps to run
            
        Returns:
            AgentHistoryList with full history
        """
        self._should_continue = True
        
        # Start browser session
        await self.browser_session.start()
        
        # Execute initial actions if any
        try:
            await self._execute_initial_actions()
        except InterruptedError:
            pass
        
        # Main control loop
        while self.state.n_steps <= max_steps and self._should_continue:
            step_info = AgentStepInfo(
                step_number=self.state.n_steps - 1,
                max_steps=max_steps
            )
            
            # Execute single step
            step_data = await self.step_once(step_info)
            
            # Call control callback if provided
            if self.step_control_callback:
                try:
                    control = await self.step_control_callback(
                        self,
                        self.state.n_steps,
                        step_data.browser_state,
                        step_data.action,
                    )
                    
                    # Process control signals
                    if control:
                        if isinstance(control, dict):
                            control = StepControl(**control)
                        
                        if control.stop:
                            self._should_continue = False
                            logger.info("[PrivacyControllableAgent] Stop requested by callback")
                        
                        if control.new_task:
                            self.add_new_task(control.new_task)
                            logger.info(f"[PrivacyControllableAgent] New task added: {control.new_task[:50]}...")
                        
                        if control.inject_context:
                            self._injected_context = control.inject_context
                            logger.debug("[PrivacyControllableAgent] Context injected for next step")
                        
                        if control.handoff_to:
                            logger.info(f"[PrivacyControllableAgent] Handoff requested to: {control.handoff_to}")
                            self._should_continue = False
                
                except Exception as e:
                    logger.error(f"[PrivacyControllableAgent] Control callback error: {e}")
            
            # Check if done
            if step_data.is_done:
                break
        
        return self.history
    
    # =========================================================================
    # CONTEXT INJECTION
    # =========================================================================
    
    async def _pre_step_inject_context(self):
        """Inject context before step execution."""
        
        # Query RAG if client provided and no context already injected
        if self.rag_client and not self._injected_context:
            try:
                rag_context = await self._query_rag()
                if rag_context:
                    self._injected_context = rag_context
            except Exception as e:
                logger.warning(f"[PrivacyControllableAgent] RAG query failed: {e}")
    
    async def _query_rag(self) -> str | None:
        """Query RAG for relevant knowledge."""
        if not self.rag_client:
            return None
        
        # Build query from current state
        query_parts = [self.task]
        
        if self.state.last_model_output:
            if self.state.last_model_output.current_state.next_goal:
                query_parts.append(self.state.last_model_output.current_state.next_goal)
        
        if self._last_browser_state:
            query_parts.append(f"on page: {self._last_browser_state.url}")
        
        query = " ".join(query_parts)
        
        # Query RAG (assumes LightRAG-compatible interface)
        try:
            if hasattr(self.rag_client, 'query'):
                result = await self.rag_client.query(
                    query,
                    {"mode": "mix", "only_need_context": True, "top_k": 3}
                )
                if isinstance(result, dict) and result.get("status") == "success":
                    return result.get("data", {}).get("response", "")
        except Exception as e:
            logger.debug(f"[PrivacyControllableAgent] RAG query error: {e}")
        
        return None
    
    # =========================================================================
    # OVERRIDE: _prepare_context with privacy + context injection
    # =========================================================================
    
    async def _prepare_context(self, step_info: "AgentStepInfo | None" = None) -> "BrowserStateSummary":
        """
        Override to add privacy filtering and context injection.
        
        Flow:
        1. Call parent's _prepare_context (gets browser state, creates messages)
        2. Apply privacy filter if enabled
        3. Inject custom context if available
        4. Return (possibly filtered) browser state
        """
        # Call parent's prepare_context
        browser_state_summary = await super()._prepare_context(step_info)
        
        # Store for later use
        self._last_browser_state = browser_state_summary
        
        # Apply privacy filter if enabled
        if self.privacy_enabled and self.privacy_filter:
            browser_state_summary = await self._apply_privacy_filter(
                browser_state_summary, step_info
            )
        
        # Inject custom context if available
        if self._injected_context:
            self._inject_context_to_messages(self._injected_context)
            self._injected_context = None  # Clear after use
        
        return browser_state_summary
    
    async def _apply_privacy_filter(
        self,
        browser_state: "BrowserStateSummary",
        step_info: "AgentStepInfo | None"
    ) -> "BrowserStateSummary":
        """Apply privacy filter to browser state."""
        url = browser_state.url if browser_state else ""
        filter_result = self.privacy_filter.filter_browser_state(browser_state, url)
        
        # Store result for debugging
        self._filter_results.append(filter_result)
        
        if filter_result.was_filtered:
            filtered_state = filter_result.filtered_data
            
            # Re-create state messages with filtered data
            self._message_manager.create_state_messages(
                browser_state_summary=filtered_state,
                model_output=self.state.last_model_output,
                result=self.state.last_result,
                step_info=step_info,
                use_vision=self.settings.use_vision,
                page_filtered_actions=None,
                sensitive_data=self.sensitive_data,
                available_file_paths=self.available_file_paths,
            )
            
            logger.debug(
                f"[PrivacyControllableAgent] Privacy filter applied, "
                f"redacted {sum(filter_result.stats.values())} items"
            )
            
            return filtered_state
        
        return browser_state
    
    def _inject_context_to_messages(self, context: str):
        """Inject context into the message manager."""
        try:
            context_block = f"\n\n<relevant_knowledge>\n{context}\n</relevant_knowledge>"
            
            # Access message manager's state and append context
            if hasattr(self._message_manager, 'add_context_message'):
                self._message_manager.add_context_message(context_block)
            else:
                # Fallback: modify the agent history description
                current_desc = getattr(self._message_manager, 'agent_history_description', '')
                self._message_manager.agent_history_description = current_desc + context_block
            
            logger.debug(f"[PrivacyControllableAgent] Injected {len(context)} chars of context")
        except Exception as e:
            logger.warning(f"[PrivacyControllableAgent] Context injection failed: {e}")
    
    # =========================================================================
    # DATA EXTRACTION
    # =========================================================================
    
    def _extract_step_data(self, error: str | None = None) -> StepData:
        """Extract step data for control decisions and history."""
        last_history = self.history.history[-1] if self.history.history else None
        
        return StepData(
            is_done=self.history.is_done(),
            step_number=self.state.n_steps,
            browser_state=self._last_browser_state,
            action=self.state.last_model_output,
            result=self.state.last_result,
            url=last_history.state.url if last_history and last_history.state else None,
            title=last_history.state.title if last_history and last_history.state else None,
            thinking=self.state.last_model_output.current_state.thinking if self.state.last_model_output else None,
            next_goal=self.state.last_model_output.current_state.next_goal if self.state.last_model_output else None,
            error=error,
        )
    
    def get_structured_history(self) -> list[dict]:
        """
        Extract history in structured format for episodic memory.
        
        Returns:
            List of dicts with action records
        """
        records = []
        for i, item in enumerate(self.history.history):
            record = {
                "step_number": i,
                "timestamp": time.time(),
                "url": item.state.url if item.state else None,
                "title": item.state.title if item.state else None,
                "action_type": "browser_action",
                "action_name": self._extract_action_name(item.model_output),
                "action_input": self._extract_action_params(item.model_output),
                "success": not any(r.error for r in item.result) if item.result else True,
                "error": next((r.error for r in item.result if r.error), None) if item.result else None,
                "thinking": item.model_output.current_state.thinking if item.model_output else None,
                "next_goal": item.model_output.current_state.next_goal if item.model_output else None,
            }
            records.append(record)
        return records
    
    def _extract_action_name(self, output: "AgentOutput | None") -> str:
        """Extract action name from model output."""
        if not output or not output.action:
            return "none"
        action = output.action[0] if output.action else None
        if not action:
            return "none"
        action_data = action.model_dump(exclude_unset=True)
        return next(iter(action_data.keys()), "unknown")
    
    def _extract_action_params(self, output: "AgentOutput | None") -> dict:
        """Extract action parameters from model output."""
        if not output or not output.action:
            return {}
        action = output.action[0] if output.action else None
        if not action:
            return {}
        action_data = action.model_dump(exclude_unset=True)
        action_name = next(iter(action_data.keys()), None)
        return action_data.get(action_name, {}) if action_name else {}
    
    # =========================================================================
    # PRIVACY UTILITIES
    # =========================================================================
    
    def get_filter_results(self) -> list[FilterResult]:
        """Get all filter results from the current session."""
        return self._filter_results
    
    def get_filter_stats(self) -> dict[str, int]:
        """Get aggregated filter statistics."""
        total_stats: dict[str, int] = {}
        for result in self._filter_results:
            for key, value in result.stats.items():
                total_stats[key] = total_stats.get(key, 0) + value
        return total_stats
    
    def clear_filter_results(self) -> None:
        """Clear stored filter results."""
        self._filter_results.clear()


# =============================================================================
# PrivacyAgent - Original composition-based wrapper (backward compatibility)
# =============================================================================

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
        logger.info(f"[PrivacyAgent] Initialized with privacy filtering {status}")
    
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
        # Call original to get browser state and create messages
        browser_state_summary = await self._original_prepare_context(step_info)
        
        # Skip filtering if disabled
        if not self.privacy_enabled:
            return browser_state_summary
        
        # Apply privacy filter
        url = browser_state_summary.url if browser_state_summary else ""
        filter_result = self.privacy_filter.filter_browser_state(
            browser_state_summary, url
        )
        
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
            
            logger.debug(
                f"[PrivacyAgent] Applied privacy filter, "
                f"redacted {sum(filter_result.stats.values())} items"
            )
            
            return filtered_state
        
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


def create_controllable_agent(
    task: str,
    llm: "BaseChatModel | None" = None,
    config_path: str | None = None,
    privacy_enabled: bool = True,
    step_control_callback: StepControlCallback | None = None,
    rag_client: Any = None,
    context_builder: Any = None,
    history_recorder: Any = None,
    **kwargs,
) -> PrivacyControllableAgent:
    """
    Create a PrivacyControllableAgent with default configuration.
    
    Args:
        task: Task description
        llm: Language model
        config_path: Path to privacy config JSON
        privacy_enabled: If False, bypasses privacy filtering
        step_control_callback: Callback for step-by-step control
        rag_client: RAG client for knowledge retrieval
        context_builder: Your ContextBuilder instance
        history_recorder: Your history recorder for episodic memory
        **kwargs: Additional Agent arguments
        
    Returns:
        Configured PrivacyControllableAgent
    """
    config = load_privacy_config(config_path)
    privacy_filter = RegexMaskFilter(config)
    
    return PrivacyControllableAgent(
        task=task,
        llm=llm,
        privacy_filter=privacy_filter,
        privacy_enabled=privacy_enabled,
        step_control_callback=step_control_callback,
        rag_client=rag_client,
        context_builder=context_builder,
        history_recorder=history_recorder,
        **kwargs,
    )
