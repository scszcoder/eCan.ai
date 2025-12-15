"""
Context Engineering Framework for LLM Context Building.

This module provides a modular, configurable context building system that:
- Gathers context from multiple providers (browser, tools, history, RAG, task)
- Manages token budgets across providers
- Formats output in various styles (XML, JSON, Markdown)
- Supports experimentation and A/B testing of configurations

Usage:
    from agent.ec_skills.context_utils import ContextBuilder, ContextBuilderConfig
    
    # Create with default config
    builder = ContextBuilder()
    
    # Or with custom config
    config = ContextBuilderConfig(
        total_token_budget=32000,
        enabled_providers=["browser", "history", "rag"],
        output_format="xml",
    )
    builder = ContextBuilder(config)
    
    # Build context from state
    context = builder.build_context(state)
"""

import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, TYPE_CHECKING

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback

if TYPE_CHECKING:
    from browser_use.browser.views import BrowserStateSummary


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class ContextBuilderConfig:
    """Configuration for context engineering."""
    
    # Token budget management
    total_token_budget: int = 32000
    budget_allocation: dict = field(default_factory=lambda: {
        "system_prompt": 0.15,      # 15% for system instructions
        "browser_state": 0.30,      # 30% for DOM/page state
        "action_history": 0.20,     # 20% for what's been done
        "tool_context": 0.10,       # 10% for available tools
        "task_context": 0.10,       # 10% for task/goal info
        "rag_knowledge": 0.10,      # 10% for RAG-retrieved knowledge
        "conversation": 0.05,       # 5% for recent messages
    })
    
    # Provider toggles
    enabled_providers: list = field(default_factory=lambda: [
        "task", "browser", "history", "tool", "rag"
    ])
    
    # Content formatting
    output_format: Literal["xml", "json", "markdown", "plain"] = "xml"
    section_order: list = field(default_factory=lambda: [
        "task_context", "relevant_knowledge", "browser_state", 
        "action_history", "tool_context"
    ])
    
    # Browser-specific settings
    browser_config: dict = field(default_factory=lambda: {
        "max_dom_elements": 200,
        "include_screenshot": False,
        "include_tabs": True,
        "dom_detail_level": "interactive",  # "full", "interactive", "minimal"
        "privacy_filter_enabled": True,
    })
    
    # History settings
    history_config: dict = field(default_factory=lambda: {
        "max_actions": 20,
        "include_failed": True,
        "summarize_old": True,
        "summary_threshold": 10,
    })
    
    # Tool context settings
    tool_config: dict = field(default_factory=lambda: {
        "include_schemas": True,
        "filter_by_page": True,
        "max_tools": 50,
    })
    
    # RAG settings
    rag_config: dict = field(default_factory=lambda: {
        "enabled": True,
        "mode": "mix",
        "top_k": 5,
        "min_score": 0.7,
    })
    
    # Experimental/tuning parameters
    tuning: dict = field(default_factory=lambda: {
        "dom_truncation_strategy": "priority",
        "history_recency_weight": 0.8,
        "include_step_info": True,
        "include_timing_info": False,
        "verbose_errors": True,
    })


# =============================================================================
# Context Chunk - Output from providers
# =============================================================================

@dataclass
class ContextChunk:
    """A piece of context from a provider."""
    provider_name: str
    section_name: str
    content: str
    token_estimate: int
    priority: float  # 0.0 - 1.0, higher = more important
    metadata: dict = field(default_factory=dict)


# =============================================================================
# Context Provider Interface
# =============================================================================

class ContextProvider(ABC):
    """Base class for context providers."""
    
    name: str = "base"
    
    @abstractmethod
    def get_context(
        self, 
        state: dict, 
        config: ContextBuilderConfig,
        token_budget: int
    ) -> ContextChunk:
        """
        Gather context from this provider.
        
        Args:
            state: Current node state (includes attributes, history, etc.)
            config: Builder configuration
            token_budget: Max tokens allocated to this provider
            
        Returns:
            ContextChunk with content and metadata
        """
        pass
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count (~4 chars per token)."""
        return len(text) // 4 if text else 0


# =============================================================================
# Provider Implementations
# =============================================================================

class TaskContextProvider(ContextProvider):
    """Provides task/goal context."""
    
    name = "task"
    
    def get_context(self, state: dict, config: ContextBuilderConfig, token_budget: int) -> ContextChunk:
        sections = []
        
        # Task description
        task = state.get("input", "")
        if task:
            sections.append(f"Task: {task}")
        
        # Step info
        if config.tuning.get("include_step_info"):
            n_steps = state.get("n_steps", 0)
            max_steps = state.get("max_steps", 100)
            sections.append(f"Progress: Step {n_steps} of {max_steps}")
        
        # Goals if defined
        goals = state.get("goals", [])
        if goals:
            goals_str = "\n".join(f"- {g.get('name', '')}: {g.get('description', '')}" for g in goals[:5])
            sections.append(f"Goals:\n{goals_str}")
        
        content = "\n".join(sections)
        
        return ContextChunk(
            provider_name=self.name,
            section_name="task_context",
            content=content,
            token_estimate=self.estimate_tokens(content),
            priority=1.0,  # Highest priority
            metadata={}
        )


class BrowserContextProvider(ContextProvider):
    """Provides browser state context."""
    
    name = "browser"
    
    def get_context(self, state: dict, config: ContextBuilderConfig, token_budget: int) -> ContextChunk:
        # Get browser state from state attributes
        browser_state = state.get("attributes", {}).get("browser_state")
        
        if not browser_state:
            return ContextChunk(
                provider_name=self.name,
                section_name="browser_state",
                content="[No browser state available]",
                token_estimate=10,
                priority=0.0,
                metadata={}
            )
        
        # Format browser state
        content = self._format_browser_state(browser_state, config.browser_config, token_budget)
        
        return ContextChunk(
            provider_name=self.name,
            section_name="browser_state",
            content=content,
            token_estimate=self.estimate_tokens(content),
            priority=0.9,
            metadata={
                "url": getattr(browser_state, 'url', None),
                "has_dom": bool(getattr(browser_state, 'dom_state', None)),
            }
        )
    
    def _format_browser_state(self, state: Any, browser_config: dict, budget: int) -> str:
        """Format browser state within token budget."""
        sections = []
        
        # URL and title
        url = getattr(state, 'url', None)
        title = getattr(state, 'title', None)
        if url:
            sections.append(f"URL: {url}")
        if title:
            sections.append(f"Title: {title}")
        
        # Tabs
        if browser_config.get("include_tabs"):
            tabs = getattr(state, 'tabs', [])
            if tabs:
                tabs_str = ", ".join(f"[{i}] {getattr(t, 'title', '')[:30]}" for i, t in enumerate(tabs[:5]))
                sections.append(f"Tabs: {tabs_str}")
        
        # DOM representation
        dom_state = getattr(state, 'dom_state', None)
        if dom_state:
            dom_repr = ""
            if hasattr(dom_state, 'llm_representation'):
                dom_repr = dom_state.llm_representation()
            elif hasattr(dom_state, 'element_tree_str'):
                dom_repr = dom_state.element_tree_str
            
            # Truncate to fit budget
            max_dom_chars = (budget - 100) * 4  # Reserve 100 tokens for headers
            if len(dom_repr) > max_dom_chars:
                dom_repr = dom_repr[:max_dom_chars] + "\n[... truncated]"
            
            if dom_repr:
                sections.append(f"Interactive Elements:\n{dom_repr}")
        
        return "\n".join(sections)


class HistoryContextProvider(ContextProvider):
    """Provides action history context."""
    
    name = "history"
    
    def get_context(self, state: dict, config: ContextBuilderConfig, token_budget: int) -> ContextChunk:
        history = state.get("history", [])
        
        if not history:
            return ContextChunk(
                provider_name=self.name,
                section_name="action_history",
                content="[No previous actions]",
                token_estimate=10,
                priority=0.0,
                metadata={"action_count": 0}
            )
        
        # Format history
        max_actions = config.history_config.get("max_actions", 20)
        include_failed = config.history_config.get("include_failed", True)
        
        content = self._format_history(history[-max_actions:], include_failed, token_budget)
        
        return ContextChunk(
            provider_name=self.name,
            section_name="action_history",
            content=content,
            token_estimate=self.estimate_tokens(content),
            priority=0.8,
            metadata={"action_count": len(history)}
        )
    
    def _format_history(self, history: list, include_failed: bool, budget: int) -> str:
        """Format action history."""
        lines = []
        
        for i, item in enumerate(history):
            # Handle different history item formats
            if hasattr(item, 'content'):
                # LangChain message format
                content = item.content[:100] if len(item.content) > 100 else item.content
                msg_type = getattr(item, 'type', 'message')
                lines.append(f"[{i+1}] {msg_type}: {content}")
            elif isinstance(item, dict):
                # Dict format
                action = item.get('action_name', item.get('action', 'unknown'))
                result = item.get('result', item.get('success', ''))
                error = item.get('error', '')
                
                if error and not include_failed:
                    continue
                
                status = "❌" if error else "✓"
                lines.append(f"[{i+1}] {status} {action}: {result or error}")
            else:
                lines.append(f"[{i+1}] {str(item)[:80]}")
        
        content = "\n".join(lines)
        
        # Truncate if needed
        max_chars = budget * 4
        if len(content) > max_chars:
            content = content[:max_chars] + "\n[... truncated]"
        
        return content


class ToolContextProvider(ContextProvider):
    """Provides available tools context."""
    
    name = "tool"
    
    def get_context(self, state: dict, config: ContextBuilderConfig, token_budget: int) -> ContextChunk:
        # Get tools from state
        tools = state.get("attributes", {}).get("available_tools", [])
        mcp_tools = state.get("attributes", {}).get("mcp_tools", [])
        
        all_tools = tools + mcp_tools
        
        if not all_tools:
            return ContextChunk(
                provider_name=self.name,
                section_name="available_tools",
                content="[No tools available]",
                token_estimate=10,
                priority=0.0,
                metadata={"tool_count": 0}
            )
        
        # Limit tools
        max_tools = config.tool_config.get("max_tools", 50)
        all_tools = all_tools[:max_tools]
        
        # Format tools
        content = self._format_tools(all_tools, config.tool_config, token_budget)
        
        return ContextChunk(
            provider_name=self.name,
            section_name="available_tools",
            content=content,
            token_estimate=self.estimate_tokens(content),
            priority=0.7,
            metadata={"tool_count": len(all_tools)}
        )
    
    def _format_tools(self, tools: list, tool_config: dict, budget: int) -> str:
        """Format tools list."""
        lines = []
        include_schemas = tool_config.get("include_schemas", True)
        
        for tool in tools:
            if isinstance(tool, dict):
                name = tool.get("name", "unknown")
                desc = tool.get("description", "")[:100]
                lines.append(f"- {name}: {desc}")
            elif hasattr(tool, 'name'):
                name = tool.name
                desc = getattr(tool, 'description', '')[:100]
                lines.append(f"- {name}: {desc}")
            else:
                lines.append(f"- {str(tool)[:80]}")
        
        return "\n".join(lines)


class RAGContextProvider(ContextProvider):
    """Provides RAG-retrieved knowledge context."""
    
    name = "rag"
    
    def __init__(self, rag_client: Any = None):
        self.rag_client = rag_client
    
    def get_context(self, state: dict, config: ContextBuilderConfig, token_budget: int) -> ContextChunk:
        # Check if RAG is enabled and client available
        if not config.rag_config.get("enabled", True):
            return ContextChunk(
                provider_name=self.name,
                section_name="relevant_knowledge",
                content="",
                token_estimate=0,
                priority=0.0,
                metadata={}
            )
        
        # Get pre-fetched RAG context from state (async query should happen before)
        rag_context = state.get("attributes", {}).get("rag_context", "")
        
        if not rag_context:
            return ContextChunk(
                provider_name=self.name,
                section_name="relevant_knowledge",
                content="",
                token_estimate=0,
                priority=0.0,
                metadata={}
            )
        
        # Truncate if needed
        max_chars = token_budget * 4
        if len(rag_context) > max_chars:
            rag_context = rag_context[:max_chars] + "\n[... truncated]"
        
        return ContextChunk(
            provider_name=self.name,
            section_name="relevant_knowledge",
            content=rag_context,
            token_estimate=self.estimate_tokens(rag_context),
            priority=0.85,
            metadata={"source": "rag"}
        )


# =============================================================================
# Context Builder - Main Orchestrator
# =============================================================================

class ContextBuilder:
    """
    Orchestrates context gathering from multiple providers.
    Manages token budget allocation and output formatting.
    """
    
    def __init__(self, config: ContextBuilderConfig | None = None):
        self.config = config or ContextBuilderConfig()
        self.providers: dict[str, ContextProvider] = {}
        self._register_default_providers()
    
    def _register_default_providers(self):
        """Register default context providers."""
        self.providers["task"] = TaskContextProvider()
        self.providers["browser"] = BrowserContextProvider()
        self.providers["history"] = HistoryContextProvider()
        self.providers["tool"] = ToolContextProvider()
        self.providers["rag"] = RAGContextProvider()
    
    def register_provider(self, provider: ContextProvider):
        """Register a custom context provider."""
        self.providers[provider.name] = provider
    
    def build_context(self, state: dict) -> str:
        """
        Build complete context from all enabled providers.
        
        Args:
            state: Current node state
            
        Returns:
            Formatted context string ready for LLM
        """
        chunks: list[ContextChunk] = []
        
        # Calculate token budgets per provider
        budgets = self._allocate_budgets()
        
        # Gather context from each enabled provider
        for provider_name in self.config.enabled_providers:
            if provider_name not in self.providers:
                logger.debug(f"[ContextBuilder] Provider '{provider_name}' not found, skipping")
                continue
            
            provider = self.providers[provider_name]
            budget = budgets.get(provider_name, 1000)
            
            try:
                chunk = provider.get_context(state, self.config, budget)
                if chunk.content:  # Only add non-empty chunks
                    chunks.append(chunk)
            except Exception as e:
                logger.warning(f"[ContextBuilder] Provider {provider_name} failed: {e}")
        
        # Sort by configured section order
        chunks = self._sort_chunks(chunks)
        
        # Merge and format
        return self._format_output(chunks)
    
    def _allocate_budgets(self) -> dict[str, int]:
        """Allocate token budgets based on config."""
        total = self.config.total_token_budget
        allocation = self.config.budget_allocation
        
        budgets = {}
        for key, ratio in allocation.items():
            # Map allocation keys to provider names
            provider_key = key.replace("_state", "").replace("_context", "").replace("_knowledge", "")
            if provider_key == "action":
                provider_key = "history"
            budgets[provider_key] = int(total * ratio)
        
        return budgets
    
    def _sort_chunks(self, chunks: list[ContextChunk]) -> list[ContextChunk]:
        """Sort chunks by configured section order."""
        order_map = {name: i for i, name in enumerate(self.config.section_order)}
        
        def sort_key(chunk: ContextChunk) -> int:
            return order_map.get(chunk.section_name, 999)
        
        return sorted(chunks, key=sort_key)
    
    def _format_output(self, chunks: list[ContextChunk]) -> str:
        """Format chunks according to output_format config."""
        fmt = self.config.output_format
        
        if fmt == "xml":
            return self._format_xml(chunks)
        elif fmt == "json":
            return self._format_json(chunks)
        elif fmt == "markdown":
            return self._format_markdown(chunks)
        else:
            return self._format_plain(chunks)
    
    def _format_xml(self, chunks: list[ContextChunk]) -> str:
        """Browser-use style XML formatting."""
        sections = []
        for chunk in chunks:
            if chunk.content.strip():
                sections.append(f"<{chunk.section_name}>\n{chunk.content}\n</{chunk.section_name}>")
        return "\n\n".join(sections)
    
    def _format_json(self, chunks: list[ContextChunk]) -> str:
        """JSON formatting."""
        data = {}
        for chunk in chunks:
            if chunk.content.strip():
                data[chunk.section_name] = chunk.content
        return json.dumps(data, indent=2)
    
    def _format_markdown(self, chunks: list[ContextChunk]) -> str:
        """Markdown formatting."""
        sections = []
        for chunk in chunks:
            if chunk.content.strip():
                title = chunk.section_name.replace("_", " ").title()
                sections.append(f"## {title}\n\n{chunk.content}")
        return "\n\n".join(sections)
    
    def _format_plain(self, chunks: list[ContextChunk]) -> str:
        """Plain text formatting."""
        sections = []
        for chunk in chunks:
            if chunk.content.strip():
                title = chunk.section_name.replace("_", " ").upper()
                sections.append(f"=== {title} ===\n{chunk.content}")
        return "\n\n".join(sections)
    
    def get_stats(self, chunks: list[ContextChunk]) -> dict:
        """Get statistics about built context."""
        return {
            "total_tokens": sum(c.token_estimate for c in chunks),
            "chunk_count": len(chunks),
            "by_provider": {c.provider_name: c.token_estimate for c in chunks},
        }


# =============================================================================
# Configuration Presets
# =============================================================================

PRESET_BROWSER_HEAVY = ContextBuilderConfig(
    total_token_budget=32000,
    budget_allocation={
        "system_prompt": 0.10,
        "browser_state": 0.45,
        "action_history": 0.20,
        "tool_context": 0.10,
        "task_context": 0.10,
        "rag_knowledge": 0.05,
    },
    browser_config={
        "max_dom_elements": 300,
        "dom_detail_level": "full",
        "include_tabs": True,
    }
)

PRESET_RAG_HEAVY = ContextBuilderConfig(
    total_token_budget=32000,
    budget_allocation={
        "system_prompt": 0.10,
        "browser_state": 0.20,
        "action_history": 0.15,
        "tool_context": 0.10,
        "task_context": 0.10,
        "rag_knowledge": 0.35,
    },
    rag_config={
        "enabled": True,
        "mode": "mix",
        "top_k": 10,
    }
)

PRESET_MINIMAL = ContextBuilderConfig(
    total_token_budget=8000,
    enabled_providers=["task", "browser"],
    browser_config={
        "max_dom_elements": 50,
        "dom_detail_level": "minimal",
        "include_tabs": False,
    }
)

PRESET_CONVERSATION = ContextBuilderConfig(
    total_token_budget=32000,
    budget_allocation={
        "system_prompt": 0.15,
        "browser_state": 0.15,
        "action_history": 0.15,
        "tool_context": 0.10,
        "task_context": 0.10,
        "rag_knowledge": 0.10,
        "conversation": 0.25,
    }
)


# =============================================================================
# Experiment Tracking
# =============================================================================

@dataclass
class ContextExperiment:
    """Track context configuration experiments."""
    experiment_id: str
    config: ContextBuilderConfig
    
    # Metrics to track
    metrics: dict = field(default_factory=lambda: {
        "llm_accuracy": [],
        "token_usage": [],
        "latency_ms": [],
        "truncation_rate": [],
        "action_success_rate": [],
    })
    
    def record(self, metric_name: str, value: float):
        """Record a metric value."""
        if metric_name in self.metrics:
            self.metrics[metric_name].append(value)
    
    def summary(self) -> dict:
        """Get summary statistics."""
        return {
            name: {
                "mean": sum(vals) / len(vals) if vals else 0,
                "min": min(vals) if vals else 0,
                "max": max(vals) if vals else 0,
                "count": len(vals),
            }
            for name, vals in self.metrics.items()
        }


# =============================================================================
# Helper Functions
# =============================================================================

def build_context_for_state(state: dict, config: ContextBuilderConfig | None = None) -> str:
    """
    Convenience function to build context from state.
    
    Args:
        state: Node state dict
        config: Optional config (uses default if None)
        
    Returns:
        Formatted context string
    """
    builder = ContextBuilder(config)
    return builder.build_context(state)


async def query_rag_for_context(
    rag_client: Any,
    task: str,
    url: str | None = None,
    last_action: str | None = None,
    config: dict | None = None,
) -> str:
    """
    Query RAG for relevant knowledge.
    
    Args:
        rag_client: RAG client with query() method
        task: Current task description
        url: Current page URL
        last_action: Last action taken
        config: RAG query config
        
    Returns:
        RAG response text
    """
    if not rag_client:
        return ""
    
    config = config or {"mode": "mix", "only_need_context": True, "top_k": 5}
    
    # Build query
    query_parts = [task]
    if url:
        query_parts.append(f"on page: {url}")
    if last_action:
        query_parts.append(f"after: {last_action}")
    
    query = " ".join(query_parts)
    
    try:
        if hasattr(rag_client, 'query'):
            result = await rag_client.query(query, config)
            if isinstance(result, dict) and result.get("status") == "success":
                return result.get("data", {}).get("response", "")
    except Exception as e:
        logger.warning(f"[query_rag_for_context] RAG query failed: {e}")
    
    return ""


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Main classes
    "ContextBuilder",
    "ContextBuilderConfig",
    "ContextChunk",
    "ContextProvider",
    # Providers
    "TaskContextProvider",
    "BrowserContextProvider",
    "HistoryContextProvider",
    "ToolContextProvider",
    "RAGContextProvider",
    # Presets
    "PRESET_BROWSER_HEAVY",
    "PRESET_RAG_HEAVY",
    "PRESET_MINIMAL",
    "PRESET_CONVERSATION",
    # Experiment
    "ContextExperiment",
    # Helpers
    "build_context_for_state",
    "query_rag_for_context",
]