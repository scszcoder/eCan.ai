"""
Privacy Agent Examples

Demonstrates various ways to use PrivacyAgent with different filtering modes:
1. Default passthrough (no filtering)
2. Regex-based filtering
3. LLM-based filtering (local LLM - placeholder for future)
"""

import asyncio
from langchain_openai import ChatOpenAI

from agent.ec_skills.browser_use_extension.privacy_agent import (
    PrivacyAgent,
    create_privacy_agent,
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
    
    print("\nUncomment the examples you want to run!")


if __name__ == "__main__":
    asyncio.run(main())
