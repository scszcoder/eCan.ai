"""
Privacy configuration management.

Supports:
- Global patterns that apply to all pages
- Per-domain patterns for domain-specific filtering
- Per-URL patterns for fine-grained control (optional)
- JSON-based configuration for easy extension
"""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from fnmatch import fnmatch

from utils.logger_helper import logger_helper as logger


@dataclass
class PatternConfig:
    """Configuration for a single pattern."""
    name: str
    pattern: str
    replacement: str
    description: str = ""
    enabled: bool = True
    case_sensitive: bool = False


@dataclass
class DomainRule:
    """
    Privacy rules for a specific domain or URL pattern.
    
    Supports:
    - Exact domain match: "example.com"
    - Wildcard subdomain: "*.example.com"
    - URL path patterns: "example.com/checkout/*"
    """
    domain_pattern: str
    enabled: bool = True
    description: str = ""
    
    # Patterns to apply for this domain (in addition to global)
    additional_patterns: list[PatternConfig] = field(default_factory=list)
    
    # Pattern names to disable for this domain (override global)
    disabled_patterns: list[str] = field(default_factory=list)
    
    # Custom field masking - mask specific DOM attributes/elements
    field_masks: dict[str, str] = field(default_factory=dict)
    # Example: {"input[name='ssn']": "[SSN_FIELD]", "#credit-card": "[CC_FIELD]"}
    
    def matches(self, url: str) -> bool:
        """
        Check if this rule matches the given URL.
        
        Args:
            url: Full URL to check
            
        Returns:
            True if rule applies to this URL
        """
        from urllib.parse import urlparse
        
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            path = parsed.path
            
            pattern = self.domain_pattern.lower()
            
            # Handle URL path patterns
            if "/" in pattern:
                # Pattern includes path
                full_match = f"{domain}{path}"
                return fnmatch(full_match, pattern)
            
            # Domain-only pattern
            if pattern.startswith("*."):
                # Wildcard subdomain
                suffix = pattern[2:]
                return domain == suffix or domain.endswith(f".{suffix}")
            
            # Exact match
            return domain == pattern
            
        except Exception as e:
            logger.warning(f"Error matching domain pattern: {e}")
            return False


@dataclass
class PrivacyConfig:
    """
    Complete privacy configuration.
    
    Supports global patterns and per-domain rules.
    """
    # Global patterns applied to all pages
    global_patterns: list[PatternConfig] = field(default_factory=list)
    
    # Per-domain rules
    domain_rules: list[DomainRule] = field(default_factory=list)
    
    # Whether to keep original (unfiltered) data in memory for debugging
    keep_original: bool = True
    
    # Whether to log redaction statistics
    log_stats: bool = True
    
    # Screenshot filtering (placeholder for future OCR-based filtering)
    filter_screenshots: bool = False
    
    # LLM-based filtering (placeholder for future implementation)
    use_llm_filter: bool = False
    llm_filter_endpoint: str = ""
    
    def get_patterns_for_url(self, url: str) -> list[PatternConfig]:
        """
        Get all applicable patterns for a given URL.
        
        Combines global patterns with domain-specific patterns,
        respecting disabled_patterns overrides.
        
        Args:
            url: The URL to get patterns for
            
        Returns:
            List of PatternConfig to apply
        """
        # Start with global patterns
        patterns = {p.name: p for p in self.global_patterns if p.enabled}
        
        # Find matching domain rules
        for rule in self.domain_rules:
            if not rule.enabled:
                continue
            if not rule.matches(url):
                continue
                
            # Remove disabled patterns
            for name in rule.disabled_patterns:
                patterns.pop(name, None)
            
            # Add domain-specific patterns
            for p in rule.additional_patterns:
                if p.enabled:
                    patterns[p.name] = p
        
        return list(patterns.values())
    
    def get_field_masks_for_url(self, url: str) -> dict[str, str]:
        """
        Get field masks for a given URL.
        
        Args:
            url: The URL to get field masks for
            
        Returns:
            Dict of CSS selector to replacement text
        """
        masks = {}
        for rule in self.domain_rules:
            if rule.enabled and rule.matches(url):
                masks.update(rule.field_masks)
        return masks
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PrivacyConfig":
        """Create from dictionary."""
        # Convert nested structures
        global_patterns = [
            PatternConfig(**p) for p in data.get("global_patterns", [])
        ]
        
        domain_rules = []
        for rule_data in data.get("domain_rules", []):
            additional = [
                PatternConfig(**p) 
                for p in rule_data.get("additional_patterns", [])
            ]
            rule_data["additional_patterns"] = additional
            domain_rules.append(DomainRule(**rule_data))
        
        return cls(
            global_patterns=global_patterns,
            domain_rules=domain_rules,
            keep_original=data.get("keep_original", True),
            log_stats=data.get("log_stats", True),
            filter_screenshots=data.get("filter_screenshots", False),
            use_llm_filter=data.get("use_llm_filter", False),
            llm_filter_endpoint=data.get("llm_filter_endpoint", ""),
        )


def get_default_config() -> PrivacyConfig:
    """
    Get default privacy configuration - passthrough by default.
    
    All patterns are DISABLED by default. Users must explicitly enable
    patterns in their config file or programmatically to activate filtering.
    This ensures privacy filtering doesn't unexpectedly modify data.
    """
    from .patterns import get_default_patterns
    
    # Convert PIIPattern to PatternConfig - ALL DISABLED by default
    global_patterns = [
        PatternConfig(
            name=p.name,
            pattern=p.pattern,
            replacement=p.replacement,
            description=p.description,
            enabled=False,  # Disabled by default - passthrough mode
            case_sensitive=p.case_sensitive,
        )
        for p in get_default_patterns(include_disabled=True).values()
    ]
    
    # No domain rules by default - empty list
    domain_rules: list[DomainRule] = []
    
    return PrivacyConfig(
        global_patterns=global_patterns,
        domain_rules=domain_rules,
        keep_original=True,
        log_stats=True,
    )


def get_example_config() -> PrivacyConfig:
    """
    Get example privacy configuration with patterns ENABLED.
    
    Use this as a template for creating your own config.
    """
    from .patterns import get_default_patterns
    
    # Convert PIIPattern to PatternConfig - use original enabled state
    global_patterns = [
        PatternConfig(
            name=p.name,
            pattern=p.pattern,
            replacement=p.replacement,
            description=p.description,
            enabled=p.enabled,  # Use pattern's default enabled state
            case_sensitive=p.case_sensitive,
        )
        for p in get_default_patterns(include_disabled=True).values()
    ]
    
    # Example domain rules
    domain_rules = [
        DomainRule(
            domain_pattern="*.bank.com",
            description="Banking sites - extra protection",
            additional_patterns=[
                PatternConfig(
                    name="account_number",
                    pattern=r'\b\d{10,12}\b',
                    replacement="[ACCOUNT_REDACTED]",
                    description="Bank account numbers",
                ),
            ],
        ),
        DomainRule(
            domain_pattern="mail.google.com",
            description="Gmail - protect email content",
            additional_patterns=[],
            disabled_patterns=[],  # Use all global patterns
        ),
    ]
    
    return PrivacyConfig(
        global_patterns=global_patterns,
        domain_rules=domain_rules,
        keep_original=True,
        log_stats=True,
    )


def load_privacy_config(config_path: str | Path | None = None) -> PrivacyConfig:
    """
    Load privacy configuration from JSON file.
    
    Args:
        config_path: Path to config file. If None, uses default location.
        
    Returns:
        PrivacyConfig instance
    """
    if config_path is None:
        # Default location in user's config directory
        config_dir = Path.home() / ".ecan" / "privacy"
        config_path = config_dir / "privacy_config.json"
    
    config_path = Path(config_path)
    
    if not config_path.exists():
        logger.info(f"Privacy config not found at {config_path}, using defaults")
        return get_default_config()
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        config = PrivacyConfig.from_dict(data)
        logger.info(f"Loaded privacy config from {config_path}")
        return config
    except Exception as e:
        logger.error(f"Error loading privacy config: {e}, using defaults")
        return get_default_config()


def save_privacy_config(
    config: PrivacyConfig, 
    config_path: str | Path | None = None
) -> bool:
    """
    Save privacy configuration to JSON file.
    
    Args:
        config: PrivacyConfig to save
        config_path: Path to save to. If None, uses default location.
        
    Returns:
        True if saved successfully
    """
    if config_path is None:
        config_dir = Path.home() / ".ecan" / "privacy"
        config_path = config_dir / "privacy_config.json"
    
    config_path = Path(config_path)
    
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2)
        logger.info(f"Saved privacy config to {config_path}")
        return True
    except Exception as e:
        logger.error(f"Error saving privacy config: {e}")
        return False
