"""
Privacy filtering module for browser-use integration.

This module provides privacy-preserving filters that intercept browser state
before it's sent to the LLM, masking or redacting sensitive information.

Supports:
- Regex-based pattern matching (emails, phones, SSN, credit cards, etc.)
- Per-domain and global filtering rules
- JSON-based configuration for extensibility
- Placeholder for OCR-based screenshot filtering
- Placeholder for LLM-based intelligent redaction
"""

from .filters import (
    PrivacyFilter,
    RegexMaskFilter,
    CompositeFilter,
    FilterResult,
)
from .patterns import (
    PII_PATTERNS,
    get_default_patterns,
)
from .config import (
    PrivacyConfig,
    PatternConfig,
    DomainRule,
    get_default_config,
    get_example_config,
    load_privacy_config,
    save_privacy_config,
)

__all__ = [
    # Filters
    "PrivacyFilter",
    "RegexMaskFilter",
    "CompositeFilter",
    "FilterResult",
    # Patterns
    "PII_PATTERNS",
    "get_default_patterns",
    # Config
    "PrivacyConfig",
    "PatternConfig",
    "DomainRule",
    "get_default_config",
    "get_example_config",
    "load_privacy_config",
    "save_privacy_config",
]
