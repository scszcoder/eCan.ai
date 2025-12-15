"""
Privacy Agent & Controllable Agent Examples

Demonstrates various ways to use:
1. PrivacyAgent - Privacy filtering modes
2. PrivacyControllableAgent - Single-step control with RAG/context injection
3. ContextBuilder - Modular context engineering

Examples:
1. Default passthrough (no filtering)
2. Regex-based filtering
3. LLM-based filtering (local LLM - placeholder)
4. Runtime toggle
5. Per-domain rules
6. Single-step control with callback
7. RAG integration
8. Context builder usage
"""

import asyncio
from langchain_openai import ChatOpenAI

from agent.ec_skills.browser_use_extension.privacy_agent import (
    # Original wrapper
    PrivacyAgent,
    create_privacy_agent,
    # New controllable agent
    PrivacyControllableAgent,
    create_controllable_agent,
    StepData,
    StepControl,
)
from agent.ec_skills.browser_use_extension.privacy import (
    RegexMaskFilter,
    CompositeFilter,
    PrivacyConfig,
    PatternConfig,
    get_default_config,
    get_example_config,
    load_privacy_config,
)
from agent.ec_skills.browser_use_extension.privacy.filters import LLMRedactFilter

# Context engineering imports
from agent.ec_skills.context_utils.context_utils import (
    ContextBuilder,
    ContextBuilderConfig,
    PRESET_BROWSER_HEAVY,
    PRESET_RAG_HEAVY,
    PRESET_MINIMAL,
    build_context_for_state,
    query_rag_for_context,
)


# =============================================================================
# Example 1: Default Passthrough (No Filtering)
# =============================================================================
async def example_passthrough():
    """
    Default mode - privacy_enabled=True but all patterns disabled.
    Data passes through unchanged unless you configure patterns.
    """
    llm = ChatOpenAI(model="gpt-4o")
    
    # Option A: Using create_privacy_agent with defaults
    agent = create_privacy_agent(
        task="Navigate to example.com and extract the page title",
        llm=llm,
    )
    
    # Option B: Explicitly disable privacy filtering
    agent_no_privacy = PrivacyAgent(
        task="Navigate to example.com",
        llm=llm,
        privacy_enabled=False,  # Complete bypass
    )
    
    result = await agent.run()
    print(f"Result: {result}")
    print(f"Filter stats (should be empty): {agent.get_filter_stats()}")


# =============================================================================
# Example 2: Regex-Based Filtering
# =============================================================================
async def example_regex_filtering():
    """
    Enable regex-based PII filtering with predefined patterns.
    """
    llm = ChatOpenAI(model="gpt-4o")
    
    # Option A: Use example config (has common patterns enabled)
    config = get_example_config()
    
    # Option B: Start from default and enable specific patterns
    # config = get_default_config()
    # for p in config.global_patterns:
    #     if p.name in ["email", "phone_us", "ssn", "credit_card"]:
    #         p.enabled = True
    
    # Option C: Load from JSON file
    # config = load_privacy_config("path/to/privacy_config.json")
    
    # Option D: Create custom config programmatically
    # config = PrivacyConfig(
    #     global_patterns=[
    #         PatternConfig(
    #             name="custom_id",
    #             pattern=r'\bID-\d{6}\b',
    #             replacement="[ID_REDACTED]",
    #             enabled=True,
    #         ),
    #     ],
    # )
    
    privacy_filter = RegexMaskFilter(config)
    
    agent = PrivacyAgent(
        task="Navigate to bank website and check account balance",
        llm=llm,
        privacy_filter=privacy_filter,
    )
    
    result = await agent.run()
    
    # Check what was filtered
    stats = agent.get_filter_stats()
    print(f"Redacted items: {stats}")
    
    # Access detailed filter results for debugging
    for i, filter_result in enumerate(agent.get_filter_results()):
        if filter_result.was_filtered:
            print(f"Step {i}: Filtered {sum(filter_result.stats.values())} items")
            # Original data is kept if config.keep_original=True
            # filter_result.original_data contains unfiltered state


# =============================================================================
# Example 3: LLM-Based Filtering (Local LLM)
# =============================================================================
async def example_llm_filtering():
    """
    Use a local LLM for intelligent PII detection and redaction.
    
    This uses the same LLM interface but points to a local server.
    Supported backends:
    - vLLM: http://localhost:8000/v1
    - SGLang: http://localhost:30000/v1
    - Ollama: http://localhost:11434/v1
    - llama.cpp: http://localhost:8080/v1
    
    NOTE: LLMRedactFilter is a placeholder - implementation pending.
    The interface is ready for when local LLM support is added.
    """
    # Main LLM for browser-use agent (can be cloud or local)
    main_llm = ChatOpenAI(model="gpt-4o")
    
    # Local LLM for privacy filtering
    # Uses OpenAI-compatible API pointing to local server
    local_llm_endpoint = "http://localhost:8000/v1"  # vLLM default
    # local_llm_endpoint = "http://localhost:30000/v1"  # SGLang default
    # local_llm_endpoint = "http://localhost:11434/v1"  # Ollama
    
    local_privacy_llm = ChatOpenAI(
        model="meta-llama/Llama-3.1-8B-Instruct",  # or your local model name
        openai_api_base=local_llm_endpoint,
        openai_api_key="not-needed",  # Local servers typically don't need keys
    )
    
    # Create LLM-based filter (placeholder implementation)
    llm_filter = LLMRedactFilter(
        endpoint=local_llm_endpoint,
        model="meta-llama/Llama-3.1-8B-Instruct",
    )
    
    # Option: Chain regex + LLM filters for defense in depth
    config = get_example_config()
    regex_filter = RegexMaskFilter(config)
    
    composite_filter = CompositeFilter([
        regex_filter,   # Fast regex pass first
        llm_filter,     # Then LLM for anything regex missed
    ])
    
    agent = PrivacyAgent(
        task="Navigate to healthcare portal and review medical records",
        llm=main_llm,
        privacy_filter=composite_filter,
        # Or just use LLM filter alone:
        # privacy_filter=llm_filter,
    )
    
    result = await agent.run()
    print(f"Filter stats: {agent.get_filter_stats()}")


# =============================================================================
# Example 4: Runtime Toggle
# =============================================================================
async def example_runtime_toggle():
    """
    Toggle privacy filtering on/off during execution.
    """
    llm = ChatOpenAI(model="gpt-4o")
    config = get_example_config()
    
    agent = PrivacyAgent(
        task="Multi-step task with varying privacy needs",
        llm=llm,
        privacy_filter=RegexMaskFilter(config),
        privacy_enabled=True,
    )
    
    # Start with privacy enabled
    print(f"Privacy enabled: {agent.privacy_enabled}")
    
    # Disable mid-execution if needed
    agent.privacy_enabled = False
    print(f"Privacy enabled: {agent.privacy_enabled}")
    
    # Re-enable
    agent.privacy_enabled = True
    
    result = await agent.run()


# =============================================================================
# Example 5: Per-Domain Configuration
# =============================================================================
async def example_per_domain():
    """
    Different filtering rules for different domains.
    """
    from agent.ec_skills.browser_use_extension.privacy.config import DomainRule
    
    llm = ChatOpenAI(model="gpt-4o")
    
    config = PrivacyConfig(
        global_patterns=[
            PatternConfig(
                name="email",
                pattern=r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                replacement="[EMAIL]",
                enabled=True,
            ),
        ],
        domain_rules=[
            # Extra strict for banking sites
            DomainRule(
                domain_pattern="*.bank.com",
                additional_patterns=[
                    PatternConfig(
                        name="account_number",
                        pattern=r'\b\d{10,12}\b',
                        replacement="[ACCOUNT]",
                        enabled=True,
                    ),
                ],
            ),
            # Disable email filtering for mail sites (we need to see emails)
            DomainRule(
                domain_pattern="mail.google.com",
                disabled_patterns=["email"],
            ),
            # URL path-based rules
            DomainRule(
                domain_pattern="example.com/checkout/*",
                additional_patterns=[
                    PatternConfig(
                        name="cvv",
                        pattern=r'\b\d{3,4}\b',
                        replacement="[CVV]",
                        enabled=True,
                    ),
                ],
            ),
        ],
    )
    
    agent = PrivacyAgent(
        task="Process orders across multiple sites",
        llm=llm,
        privacy_filter=RegexMaskFilter(config),
    )
    
    result = await agent.run()


# =============================================================================
# Example 6: Single-Step Control with Callback
# =============================================================================
async def example_single_step_control():
    """
    Use PrivacyControllableAgent with step-by-step control.
    
    The callback is called after each step, allowing you to:
    - Inject context (RAG knowledge, instructions)
    - Stop execution
    - Add new tasks
    - Hand off to another agent
    """
    llm = ChatOpenAI(model="gpt-4o")
    
    # Track steps for demo
    step_count = 0
    
    async def my_step_controller(
        agent: PrivacyControllableAgent,
        step_num: int,
        browser_state,
        action,
    ) -> StepControl:
        """
        Called after each step - you have full control here.
        
        Args:
            agent: The agent instance (access to all internals)
            step_num: Current step number
            browser_state: Current browser state (URL, DOM, etc.)
            action: The action that was just taken
            
        Returns:
            StepControl with signals for next step
        """
        nonlocal step_count
        step_count += 1
        
        print(f"\n[Callback] Step {step_num} completed")
        
        if browser_state:
            print(f"  URL: {browser_state.url}")
        
        if action:
            print(f"  Thinking: {action.current_state.thinking[:100] if action.current_state.thinking else 'N/A'}...")
            print(f"  Next goal: {action.current_state.next_goal}")
        
        # Example: Inject context based on current page
        if browser_state and "checkout" in browser_state.url.lower():
            return StepControl(
                inject_context="Remember: Always verify the total before confirming payment."
            )
        
        # Example: Stop after 10 steps
        if step_count >= 10:
            return StepControl(stop=True)
        
        # Example: Hand off to specialist agent
        if browser_state and "error" in browser_state.url.lower():
            return StepControl(
                stop=True,
                handoff_to="error_handler_agent",
            )
        
        # Continue normally
        return StepControl()
    
    # Create controllable agent
    agent = PrivacyControllableAgent(
        task="Navigate to example.com and explore the site",
        llm=llm,
        step_control_callback=my_step_controller,
        privacy_enabled=True,
    )
    
    # Run with control
    history = await agent.run_with_control(max_steps=20)
    
    print(f"\nCompleted {step_count} steps")
    print(f"Final result: {history.final_result()}")
    
    # Get structured history for your episodic memory
    structured = agent.get_structured_history()
    print(f"Structured history: {len(structured)} records")


# =============================================================================
# Example 7: RAG Integration
# =============================================================================
async def example_rag_integration():
    """
    Use PrivacyControllableAgent with RAG for knowledge-augmented browsing.
    
    The agent queries RAG before each step to get relevant knowledge.
    """
    llm = ChatOpenAI(model="gpt-4o")
    
    # Mock RAG client (replace with your actual LightRAG client)
    class MockRAGClient:
        async def query(self, query: str, options: dict) -> dict:
            """Mock RAG query - replace with actual implementation."""
            print(f"[RAG] Query: {query[:50]}...")
            
            # Simulate RAG response based on query
            if "checkout" in query.lower():
                return {
                    "status": "success",
                    "data": {
                        "response": "Checkout best practices: 1) Verify cart items, 2) Check shipping address, 3) Review payment method"
                    }
                }
            elif "login" in query.lower():
                return {
                    "status": "success",
                    "data": {
                        "response": "Login procedure: Use saved credentials from password manager. Check for 2FA prompt."
                    }
                }
            return {"status": "success", "data": {"response": ""}}
    
    rag_client = MockRAGClient()
    
    # Create agent with RAG client
    agent = create_controllable_agent(
        task="Navigate to example.com, log in, and complete checkout",
        llm=llm,
        rag_client=rag_client,
        privacy_enabled=True,
    )
    
    # The agent will automatically query RAG before each step
    history = await agent.run_with_control(max_steps=15)
    
    print(f"Completed with RAG assistance")
    print(f"Filter stats: {agent.get_filter_stats()}")


# =============================================================================
# Example 8: Context Builder Usage
# =============================================================================
async def example_context_builder():
    """
    Use ContextBuilder for modular context engineering.
    
    This shows how to build structured context from various sources.
    """
    # Create context builder with default config
    builder = ContextBuilder()
    
    # Or use a preset
    # builder = ContextBuilder(PRESET_BROWSER_HEAVY)
    # builder = ContextBuilder(PRESET_RAG_HEAVY)
    # builder = ContextBuilder(PRESET_MINIMAL)
    
    # Or customize
    custom_config = ContextBuilderConfig(
        total_token_budget=16000,
        enabled_providers=["task", "browser", "history", "rag"],
        output_format="xml",  # or "json", "markdown", "plain"
        browser_config={
            "max_dom_elements": 100,
            "include_tabs": True,
        },
        rag_config={
            "enabled": True,
            "mode": "mix",
            "top_k": 5,
        },
    )
    builder = ContextBuilder(custom_config)
    
    # Build context from state
    state = {
        "input": "Find and purchase the cheapest flight to Tokyo",
        "n_steps": 5,
        "max_steps": 50,
        "history": [
            {"action_name": "navigate", "result": "success", "error": None},
            {"action_name": "click", "result": "success", "error": None},
            {"action_name": "input_text", "result": "success", "error": None},
        ],
        "attributes": {
            "browser_state": None,  # Would be BrowserStateSummary in real use
            "rag_context": "Flight booking tips: Compare prices across multiple dates. Check baggage policies.",
            "available_tools": [
                {"name": "click", "description": "Click on an element"},
                {"name": "input_text", "description": "Enter text into a field"},
                {"name": "scroll", "description": "Scroll the page"},
            ],
        },
    }
    
    context = builder.build_context(state)
    
    print("=" * 60)
    print("Built Context (XML format):")
    print("=" * 60)
    print(context)
    
    # Try different formats
    print("\n" + "=" * 60)
    print("Markdown format:")
    print("=" * 60)
    custom_config.output_format = "markdown"
    builder = ContextBuilder(custom_config)
    print(builder.build_context(state))


# =============================================================================
# Example 9: Manual Single-Step Execution
# =============================================================================
async def example_manual_steps():
    """
    Manually execute single steps for maximum control.
    
    Useful when you need to:
    - Integrate with external systems between steps
    - Implement custom retry logic
    - Coordinate multiple agents
    """
    llm = ChatOpenAI(model="gpt-4o")
    
    agent = PrivacyControllableAgent(
        task="Navigate to example.com and find the contact page",
        llm=llm,
        privacy_enabled=True,
    )
    
    # Start browser session manually
    await agent.browser_session.start()
    
    # Execute steps manually
    for i in range(10):
        print(f"\n--- Executing step {i + 1} ---")
        
        # Execute single step
        step_data: StepData = await agent.step_once()
        
        print(f"URL: {step_data.url}")
        print(f"Action: {agent._extract_action_name(step_data.action)}")
        print(f"Done: {step_data.is_done}")
        
        if step_data.error:
            print(f"Error: {step_data.error}")
            # Implement custom retry logic here
            break
        
        if step_data.is_done:
            print("Task completed!")
            break
        
        # Do something between steps
        # e.g., query external API, update database, notify user
        await asyncio.sleep(0.5)
    
    # Get final history
    structured_history = agent.get_structured_history()
    print(f"\nTotal steps: {len(structured_history)}")


# =============================================================================
# Main
# =============================================================================
async def main():
    """Run examples."""
    print("=" * 60)
    print("Example 1: Passthrough (no filtering)")
    print("=" * 60)
    # await example_passthrough()
    
    print("\n" + "=" * 60)
    print("Example 2: Regex filtering")
    print("=" * 60)
    # await example_regex_filtering()
    
    print("\n" + "=" * 60)
    print("Example 3: LLM filtering (local)")
    print("=" * 60)
    # await example_llm_filtering()
    
    print("\n" + "=" * 60)
    print("Example 4: Runtime toggle")
    print("=" * 60)
    # await example_runtime_toggle()
    
    print("\n" + "=" * 60)
    print("Example 5: Per-domain rules")
    print("=" * 60)
    # await example_per_domain()
    
    print("\n" + "=" * 60)
    print("Example 6: Single-step control with callback")
    print("=" * 60)
    # await example_single_step_control()
    
    print("\n" + "=" * 60)
    print("Example 7: RAG integration")
    print("=" * 60)
    # await example_rag_integration()
    
    print("\n" + "=" * 60)
    print("Example 8: Context builder")
    print("=" * 60)
    await example_context_builder()  # This one doesn't need browser
    
    print("\n" + "=" * 60)
    print("Example 9: Manual single steps")
    print("=" * 60)
    # await example_manual_steps()
    
    print("\nUncomment the examples you want to run!")


if __name__ == "__main__":
    asyncio.run(main())
