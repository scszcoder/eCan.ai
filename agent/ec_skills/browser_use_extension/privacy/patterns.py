"""
Regex patterns for PII detection and masking.

These patterns are used by RegexMaskFilter to identify and redact
sensitive information from browser content before sending to LLM.
"""

import re
from dataclasses import dataclass, field
from typing import Pattern


@dataclass
class PIIPattern:
    """A pattern for detecting and masking PII."""
    name: str
    pattern: str
    replacement: str
    description: str = ""
    enabled: bool = True
    case_sensitive: bool = False
    
    _compiled: Pattern | None = field(default=None, repr=False, compare=False)
    
    def compile(self) -> Pattern:
        """Compile the regex pattern."""
        if self._compiled is None:
            flags = 0 if self.case_sensitive else re.IGNORECASE
            self._compiled = re.compile(self.pattern, flags)
        return self._compiled
    
    def mask(self, text: str) -> tuple[str, int]:
        """
        Apply masking to text.
        
        Returns:
            tuple: (masked_text, count of replacements)
        """
        compiled = self.compile()
        masked, count = compiled.subn(self.replacement, text)
        return masked, count


# Default PII patterns - these are common patterns that should be masked
PII_PATTERNS: dict[str, PIIPattern] = {
    # Email addresses
    "email": PIIPattern(
        name="email",
        pattern=r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        replacement="[EMAIL_REDACTED]",
        description="Email addresses",
    ),
    
    # Phone numbers (various formats)
    "phone_us": PIIPattern(
        name="phone_us",
        pattern=r'\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
        replacement="[PHONE_REDACTED]",
        description="US phone numbers",
    ),
    
    # Social Security Numbers
    "ssn": PIIPattern(
        name="ssn",
        pattern=r'\b[0-9]{3}[-\s]?[0-9]{2}[-\s]?[0-9]{4}\b',
        replacement="[SSN_REDACTED]",
        description="Social Security Numbers",
    ),
    
    # Credit Card Numbers (basic patterns)
    "credit_card": PIIPattern(
        name="credit_card",
        pattern=r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b',
        replacement="[CC_REDACTED]",
        description="Credit card numbers (Visa, MC, Amex, Discover)",
    ),
    
    # Credit card with spaces/dashes
    "credit_card_formatted": PIIPattern(
        name="credit_card_formatted",
        pattern=r'\b(?:[0-9]{4}[-\s]){3}[0-9]{4}\b',
        replacement="[CC_REDACTED]",
        description="Credit card numbers with separators",
    ),
    
    # IP Addresses (IPv4)
    "ipv4": PIIPattern(
        name="ipv4",
        pattern=r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b',
        replacement="[IP_REDACTED]",
        description="IPv4 addresses",
        enabled=False,  # Disabled by default as may be needed for debugging
    ),
    
    # Date of Birth patterns
    "dob": PIIPattern(
        name="dob",
        pattern=r'\b(?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|[12][0-9]|3[01])[/\-](?:19|20)[0-9]{2}\b',
        replacement="[DOB_REDACTED]",
        description="Dates of birth (MM/DD/YYYY or MM-DD-YYYY)",
    ),
    
    # US ZIP codes
    "zip_code": PIIPattern(
        name="zip_code",
        pattern=r'\b[0-9]{5}(?:-[0-9]{4})?\b',
        replacement="[ZIP_REDACTED]",
        description="US ZIP codes",
        enabled=False,  # Disabled by default - too many false positives
    ),
    
    # Street addresses (basic pattern)
    "street_address": PIIPattern(
        name="street_address",
        pattern=r'\b\d+\s+(?:[A-Za-z]+\s+){1,4}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|Place|Pl)\.?\b',
        replacement="[ADDRESS_REDACTED]",
        description="Street addresses",
        enabled=False,  # Disabled by default - may interfere with navigation
    ),
    
    # Bank account numbers (generic pattern)
    "bank_account": PIIPattern(
        name="bank_account",
        pattern=r'\b[0-9]{8,17}\b',
        replacement="[ACCOUNT_REDACTED]",
        description="Bank account numbers",
        enabled=False,  # Disabled by default - too generic
    ),
    
    # Passport numbers (US format)
    "passport_us": PIIPattern(
        name="passport_us",
        pattern=r'\b[A-Z][0-9]{8}\b',
        replacement="[PASSPORT_REDACTED]",
        description="US passport numbers",
        case_sensitive=True,
    ),
    
    # Driver's license (generic pattern)
    "drivers_license": PIIPattern(
        name="drivers_license",
        pattern=r'\b[A-Z]{1,2}[0-9]{5,8}\b',
        replacement="[DL_REDACTED]",
        description="Driver's license numbers",
        enabled=False,  # Disabled by default - too generic
        case_sensitive=True,
    ),
    
    # API Keys / Tokens (common patterns)
    "api_key": PIIPattern(
        name="api_key",
        pattern=r'\b(?:sk|pk|api|key|token|secret|password|auth)[_-]?[A-Za-z0-9]{20,}\b',
        replacement="[API_KEY_REDACTED]",
        description="API keys and tokens",
    ),
    
    # AWS Access Keys
    "aws_key": PIIPattern(
        name="aws_key",
        pattern=r'\b(?:AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}\b',
        replacement="[AWS_KEY_REDACTED]",
        description="AWS access key IDs",
        case_sensitive=True,
    ),
    
    # Generic secrets in URLs
    "url_secret": PIIPattern(
        name="url_secret",
        pattern=r'(?:password|pwd|secret|token|key|auth|api_key)=([^&\s]+)',
        replacement=r'\1=[REDACTED]',
        description="Secrets in URL parameters",
    ),
}


def get_default_patterns(include_disabled: bool = False) -> dict[str, PIIPattern]:
    """
    Get the default PII patterns.
    
    Args:
        include_disabled: If True, include patterns that are disabled by default
        
    Returns:
        Dictionary of pattern name to PIIPattern
    """
    if include_disabled:
        return PII_PATTERNS.copy()
    return {k: v for k, v in PII_PATTERNS.items() if v.enabled}


def create_custom_pattern(
    name: str,
    pattern: str,
    replacement: str,
    description: str = "",
    case_sensitive: bool = False,
) -> PIIPattern:
    """
    Create a custom PII pattern.
    
    Args:
        name: Unique name for the pattern
        pattern: Regex pattern string
        replacement: Replacement text
        description: Human-readable description
        case_sensitive: Whether pattern is case-sensitive
        
    Returns:
        PIIPattern instance
    """
    return PIIPattern(
        name=name,
        pattern=pattern,
        replacement=replacement,
        description=description,
        case_sensitive=case_sensitive,
        enabled=True,
    )
