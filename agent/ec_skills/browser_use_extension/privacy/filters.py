"""
Privacy filters for browser-use integration.

These filters intercept BrowserStateSummary before it's sent to the LLM,
masking or redacting sensitive information.
"""

import re
import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from utils.logger_helper import logger_helper as logger

from .patterns import PIIPattern
from .config import PrivacyConfig, PatternConfig, load_privacy_config


@dataclass
class FilterResult:
    """Result of applying privacy filters."""
    # The filtered data (safe to send to LLM)
    filtered_data: Any
    
    # Original data (kept for debugging if config.keep_original is True)
    original_data: Any | None = None
    
    # Statistics about what was filtered
    stats: dict[str, int] = field(default_factory=dict)
    
    # Whether any filtering was applied
    was_filtered: bool = False
    
    # URL that was filtered
    url: str = ""
    
    def log_stats(self) -> None:
        """Log filtering statistics."""
        if not self.was_filtered:
            logger.debug(f"[PrivacyFilter] No sensitive data found for {self.url}")
            return
        
        total = sum(self.stats.values())
        details = ", ".join(f"{k}: {v}" for k, v in self.stats.items() if v > 0)
        logger.info(f"[PrivacyFilter] Redacted {total} items for {self.url} ({details})")


class PrivacyFilter(ABC):
    """
    Abstract base class for privacy filters.
    
    Filters can be composed using CompositeFilter for layered filtering.
    """
    
    @abstractmethod
    def filter_text(self, text: str, url: str = "") -> tuple[str, dict[str, int]]:
        """
        Filter sensitive data from text.
        
        Args:
            text: Text to filter
            url: URL context for per-domain rules
            
        Returns:
            tuple: (filtered_text, stats_dict)
        """
        pass
    
    @abstractmethod
    def filter_browser_state(self, browser_state: Any, url: str = "") -> FilterResult:
        """
        Filter sensitive data from BrowserStateSummary.
        
        Args:
            browser_state: BrowserStateSummary object
            url: URL context (usually from browser_state.url)
            
        Returns:
            FilterResult with filtered data and stats
        """
        pass
    
    def filter_screenshot(self, screenshot_b64: str, url: str = "") -> tuple[str, dict[str, int]]:
        """
        Filter sensitive data from screenshot (placeholder for OCR-based filtering).
        
        Args:
            screenshot_b64: Base64-encoded screenshot
            url: URL context
            
        Returns:
            tuple: (filtered_screenshot_b64, stats_dict)
        """
        # TODO: Implement OCR-based screenshot filtering
        # This would:
        # 1. Decode base64 to image
        # 2. Run OCR to detect text regions
        # 3. Apply regex patterns to detected text
        # 4. Blur/redact matching regions in the image
        # 5. Re-encode to base64
        #
        # For now, return unchanged
        return screenshot_b64, {}


class RegexMaskFilter(PrivacyFilter):
    """
    Regex-based privacy filter.
    
    Uses configurable patterns to detect and mask PII in text content.
    Supports global and per-domain patterns.
    """
    
    def __init__(self, config: PrivacyConfig | None = None):
        """
        Initialize the filter.
        
        Args:
            config: Privacy configuration. If None, loads from default location.
        """
        self.config = config or load_privacy_config()
        self._compiled_patterns: dict[str, re.Pattern] = {}
    
    def _get_compiled_pattern(self, pattern_config: PatternConfig) -> re.Pattern:
        """Get or compile a regex pattern."""
        key = f"{pattern_config.name}:{pattern_config.pattern}"
        if key not in self._compiled_patterns:
            flags = 0 if pattern_config.case_sensitive else re.IGNORECASE
            self._compiled_patterns[key] = re.compile(pattern_config.pattern, flags)
        return self._compiled_patterns[key]
    
    def filter_text(self, text: str, url: str = "") -> tuple[str, dict[str, int]]:
        """
        Filter sensitive data from text using regex patterns.
        
        Args:
            text: Text to filter
            url: URL context for per-domain rules
            
        Returns:
            tuple: (filtered_text, stats_dict)
        """
        if not text:
            return text, {}
        
        stats: dict[str, int] = {}
        filtered = text
        
        # Get applicable patterns for this URL
        patterns = self.config.get_patterns_for_url(url)
        
        for pattern_config in patterns:
            if not pattern_config.enabled:
                continue
            
            try:
                compiled = self._get_compiled_pattern(pattern_config)
                filtered, count = compiled.subn(pattern_config.replacement, filtered)
                if count > 0:
                    stats[pattern_config.name] = stats.get(pattern_config.name, 0) + count
            except Exception as e:
                logger.warning(f"Error applying pattern {pattern_config.name}: {e}")
        
        return filtered, stats
    
    def filter_browser_state(self, browser_state: Any, url: str = "") -> FilterResult:
        """
        Filter sensitive data from BrowserStateSummary.
        
        Filters:
        - dom_state text representation
        - url (query parameters)
        - title
        - tab titles
        - screenshot (placeholder)
        
        Args:
            browser_state: BrowserStateSummary object
            url: URL context (defaults to browser_state.url)
            
        Returns:
            FilterResult with filtered data and stats
        """
        if browser_state is None:
            return FilterResult(filtered_data=None, was_filtered=False)
        
        # Use URL from browser_state if not provided
        if not url:
            url = getattr(browser_state, "url", "")
        
        # Keep original if configured
        original = None
        if self.config.keep_original:
            original = copy.deepcopy(browser_state)
        
        # Create a copy to modify
        filtered_state = copy.deepcopy(browser_state)
        total_stats: dict[str, int] = {}
        
        # Filter URL (especially query parameters)
        if hasattr(filtered_state, "url") and filtered_state.url:
            filtered_state.url, stats = self.filter_text(filtered_state.url, url)
            self._merge_stats(total_stats, stats)
        
        # Filter title
        if hasattr(filtered_state, "title") and filtered_state.title:
            filtered_state.title, stats = self.filter_text(filtered_state.title, url)
            self._merge_stats(total_stats, stats)
        
        # Filter DOM state
        if hasattr(filtered_state, "dom_state") and filtered_state.dom_state:
            self._filter_dom_state(filtered_state.dom_state, url, total_stats)
        
        # Filter tabs
        if hasattr(filtered_state, "tabs") and filtered_state.tabs:
            for tab in filtered_state.tabs:
                if hasattr(tab, "title") and tab.title:
                    tab.title, stats = self.filter_text(tab.title, url)
                    self._merge_stats(total_stats, stats)
                if hasattr(tab, "url") and tab.url:
                    tab.url, stats = self.filter_text(tab.url, url)
                    self._merge_stats(total_stats, stats)
        
        # Filter screenshot (placeholder)
        if self.config.filter_screenshots:
            if hasattr(filtered_state, "screenshot") and filtered_state.screenshot:
                filtered_state.screenshot, stats = self.filter_screenshot(
                    filtered_state.screenshot, url
                )
                self._merge_stats(total_stats, stats)
        
        result = FilterResult(
            filtered_data=filtered_state,
            original_data=original,
            stats=total_stats,
            was_filtered=bool(total_stats),
            url=url,
        )
        
        if self.config.log_stats:
            result.log_stats()
        
        return result
    
    def _filter_dom_state(
        self, 
        dom_state: Any, 
        url: str, 
        stats: dict[str, int]
    ) -> None:
        """
        Filter DOM state in-place.
        
        The DOM state contains the serialized DOM tree that gets sent to the LLM.
        We need to filter text content within it.
        """
        # SerializedDOMState has a selector_map and _root
        # The LLM sees the result of llm_representation()
        # We need to filter the underlying node text
        
        if hasattr(dom_state, "_root") and dom_state._root:
            self._filter_dom_node(dom_state._root, url, stats)
        
        # Also filter selector_map values if they contain text
        if hasattr(dom_state, "selector_map") and dom_state.selector_map:
            for key, node in dom_state.selector_map.items():
                self._filter_dom_node(node, url, stats)
    
    def _filter_dom_node(
        self, 
        node: Any, 
        url: str, 
        stats: dict[str, int]
    ) -> None:
        """Recursively filter a DOM node and its children."""
        if node is None:
            return
        
        # Filter node_value (text content)
        if hasattr(node, "node_value") and node.node_value:
            node.node_value, node_stats = self.filter_text(node.node_value, url)
            self._merge_stats(stats, node_stats)
        
        # Filter attributes that might contain sensitive data
        if hasattr(node, "attributes") and node.attributes:
            for attr_name in ["value", "placeholder", "title", "alt", "aria-label"]:
                if attr_name in node.attributes and node.attributes[attr_name]:
                    node.attributes[attr_name], attr_stats = self.filter_text(
                        node.attributes[attr_name], url
                    )
                    self._merge_stats(stats, attr_stats)
        
        # Recurse into children
        if hasattr(node, "children") and node.children:
            for child in node.children:
                self._filter_dom_node(child, url, stats)
        
        # Also check children_nodes (used in some node types)
        if hasattr(node, "children_nodes") and node.children_nodes:
            for child in node.children_nodes:
                self._filter_dom_node(child, url, stats)
    
    def _merge_stats(self, target: dict[str, int], source: dict[str, int]) -> None:
        """Merge source stats into target."""
        for key, value in source.items():
            target[key] = target.get(key, 0) + value


class LLMRedactFilter(PrivacyFilter):
    """
    LLM-based privacy filter (placeholder for future implementation).
    
    Uses a local LLM (vLLM, SGLang, etc.) to intelligently identify
    and redact sensitive information that regex patterns might miss.
    """
    
    def __init__(
        self, 
        endpoint: str = "",
        model: str = "",
        config: PrivacyConfig | None = None
    ):
        """
        Initialize the LLM filter.
        
        Args:
            endpoint: LLM server endpoint (e.g., "http://localhost:8000/v1")
            model: Model name to use
            config: Privacy configuration
        """
        self.endpoint = endpoint
        self.model = model
        self.config = config or load_privacy_config()
        
        # TODO: Initialize LLM client when implementing
        # self.client = None
    
    def filter_text(self, text: str, url: str = "") -> tuple[str, dict[str, int]]:
        """
        Filter text using LLM-based redaction.
        
        TODO: Implement when local LLM is available.
        
        The implementation would:
        1. Send text to local LLM with a prompt asking to identify PII
        2. Parse LLM response to get PII locations
        3. Redact identified PII
        4. Return filtered text
        """
        # Placeholder - return unchanged
        logger.debug("[LLMRedactFilter] LLM filtering not yet implemented")
        return text, {}
    
    def filter_browser_state(self, browser_state: Any, url: str = "") -> FilterResult:
        """
        Filter browser state using LLM-based redaction.
        
        TODO: Implement when local LLM is available.
        """
        # Placeholder - return unchanged
        return FilterResult(
            filtered_data=browser_state,
            original_data=browser_state if self.config.keep_original else None,
            was_filtered=False,
            url=url,
        )


class CompositeFilter(PrivacyFilter):
    """
    Composite filter that chains multiple filters together.
    
    Filters are applied in order, with each filter receiving
    the output of the previous filter.
    """
    
    def __init__(self, filters: list[PrivacyFilter] | None = None):
        """
        Initialize with a list of filters.
        
        Args:
            filters: List of filters to apply in order
        """
        self.filters = filters or []
    
    def add_filter(self, filter_: PrivacyFilter) -> "CompositeFilter":
        """Add a filter to the chain."""
        self.filters.append(filter_)
        return self
    
    def filter_text(self, text: str, url: str = "") -> tuple[str, dict[str, int]]:
        """Apply all filters to text in sequence."""
        total_stats: dict[str, int] = {}
        filtered = text
        
        for f in self.filters:
            filtered, stats = f.filter_text(filtered, url)
            for key, value in stats.items():
                total_stats[key] = total_stats.get(key, 0) + value
        
        return filtered, total_stats
    
    def filter_browser_state(self, browser_state: Any, url: str = "") -> FilterResult:
        """Apply all filters to browser state in sequence."""
        if not self.filters:
            return FilterResult(filtered_data=browser_state, was_filtered=False)
        
        # Keep original from first filter
        original = None
        current_state = browser_state
        total_stats: dict[str, int] = {}
        
        for i, f in enumerate(self.filters):
            result = f.filter_browser_state(current_state, url)
            
            # Keep original from first filter only
            if i == 0 and result.original_data is not None:
                original = result.original_data
            
            current_state = result.filtered_data
            
            for key, value in result.stats.items():
                total_stats[key] = total_stats.get(key, 0) + value
        
        return FilterResult(
            filtered_data=current_state,
            original_data=original,
            stats=total_stats,
            was_filtered=bool(total_stats),
            url=url,
        )


def create_default_filter(config: PrivacyConfig | None = None) -> PrivacyFilter:
    """
    Create a default privacy filter with standard configuration.
    
    Args:
        config: Optional custom configuration
        
    Returns:
        Configured PrivacyFilter instance
    """
    config = config or load_privacy_config()
    
    # For now, just use regex filter
    # In the future, can compose with LLM filter:
    # return CompositeFilter([
    #     RegexMaskFilter(config),
    #     LLMRedactFilter(config.llm_filter_endpoint, config=config),
    # ])
    
    return RegexMaskFilter(config)
