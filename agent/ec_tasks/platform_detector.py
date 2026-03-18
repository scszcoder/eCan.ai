"""
Platform Detector - Automatically identifies e-commerce platforms for chat monitoring.

Detects platform based on URL patterns and DOM signatures, then loads the
appropriate platform profile for event detection and chat ID extraction.

Usage:
    detector = PlatformDetector()
    platform_id = detector.detect_platform(url, dom_snapshot)
    profile = detector.get_profile(platform_id)
"""

import json
import re
import os
from typing import Optional, Dict, Any, List
from pathlib import Path

from utils.logger_helper import logger_helper as logger


class PlatformDetector:
    """Detects e-commerce platforms and loads their configuration profiles."""
    
    def __init__(self, profiles_path: Optional[str] = None):
        """
        Initialize platform detector.
        
        Args:
            profiles_path: Path to platform_profiles.json. If None, uses default location.
        """
        if profiles_path is None:
            # Default to same directory as this file
            current_dir = Path(__file__).parent
            profiles_path = current_dir / "platform_profiles.json"
        
        self.profiles_path = Path(profiles_path)
        self.profiles: Dict[str, Dict[str, Any]] = {}
        self._load_profiles()
    
    def _load_profiles(self) -> None:
        """Load platform profiles from JSON file."""
        try:
            if not self.profiles_path.exists():
                logger.error(f"[PlatformDetector] Profiles file not found: {self.profiles_path}")
                self.profiles = {}
                return
            
            with open(self.profiles_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.profiles = data.get('profiles', {})
            
            # Remove template from active profiles
            if 'custom_template' in self.profiles:
                del self.profiles['custom_template']
            
            logger.info(f"[PlatformDetector] Loaded {len(self.profiles)} platform profiles")
            
        except Exception as e:
            logger.error(f"[PlatformDetector] Failed to load profiles: {e}")
            self.profiles = {}
    
    def detect_platform(
        self,
        url: str,
        dom_snapshot: Optional[str] = None,
        required_elements: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Detect platform based on URL and optional DOM snapshot.
        
        Args:
            url: Current page URL
            dom_snapshot: Optional HTML snapshot for DOM signature matching
            required_elements: Optional list of element selectors found on page
        
        Returns:
            platform_id if detected, None otherwise
        """
        if not url:
            return None
        
        url_lower = url.lower()
        
        # Try each profile
        for platform_id, profile in self.profiles.items():
            detection = profile.get('detection', {})
            
            # Check URL patterns
            url_patterns = detection.get('url_patterns', [])
            if self._match_url_patterns(url_lower, url_patterns):
                logger.info(f"[PlatformDetector] Detected platform by URL: {platform_id}")
                
                # If DOM snapshot available, verify with DOM signatures
                if dom_snapshot:
                    dom_signatures = detection.get('dom_signatures', [])
                    if dom_signatures and not self._match_dom_signatures(dom_snapshot, dom_signatures):
                        logger.warning(
                            f"[PlatformDetector] URL matched {platform_id} but DOM signatures failed, "
                            "continuing search..."
                        )
                        continue
                
                # If required elements provided, verify them
                if required_elements:
                    required = detection.get('required_elements', [])
                    if required and not self._match_required_elements(required_elements, required):
                        logger.warning(
                            f"[PlatformDetector] URL matched {platform_id} but required elements missing, "
                            "continuing search..."
                        )
                        continue
                
                return platform_id
        
        logger.warning(f"[PlatformDetector] No platform detected for URL: {url[:100]}")
        return None
    
    def _match_url_patterns(self, url: str, patterns: List[str]) -> bool:
        """Check if URL matches any of the patterns."""
        for pattern in patterns:
            # Convert glob-like pattern to regex
            # Replace * with .* for wildcard matching
            regex_pattern = pattern.replace('.', r'\.').replace('*', '.*')
            if re.search(regex_pattern, url, re.IGNORECASE):
                return True
        return False
    
    def _match_dom_signatures(self, dom_snapshot: str, signatures: List[str]) -> bool:
        """Check if DOM contains any of the signature selectors."""
        # Simple check: look for selector patterns in HTML
        # This is a basic implementation; could be enhanced with actual DOM parsing
        for signature in signatures:
            # Extract key parts of selector for matching
            # e.g., "div[data-test-id='message-thread']" -> look for "data-test-id='message-thread'"
            if 'data-test-id' in signature:
                match = re.search(r"data-test-id=['\"]([^'\"]+)['\"]", signature)
                if match and match.group(0) in dom_snapshot:
                    return True
            elif 'class*=' in signature:
                match = re.search(r"class\*=['\"]([^'\"]+)['\"]", signature)
                if match and match.group(1) in dom_snapshot:
                    return True
            elif signature in dom_snapshot:
                return True
        return False
    
    def _match_required_elements(self, found_elements: List[str], required: List[str]) -> bool:
        """Check if all required elements are present."""
        # Check if any required element is in the found elements
        for req in required:
            if any(req in elem for elem in found_elements):
                return True
        return False
    
    def get_profile(self, platform_id: str) -> Optional[Dict[str, Any]]:
        """
        Get platform profile by ID.
        
        Args:
            platform_id: Platform identifier
        
        Returns:
            Platform profile dict or None if not found
        """
        profile = self.profiles.get(platform_id)
        if profile:
            logger.debug(f"[PlatformDetector] Retrieved profile for: {platform_id}")
        else:
            logger.warning(f"[PlatformDetector] Profile not found: {platform_id}")
        return profile
    
    def get_all_platforms(self) -> List[str]:
        """Get list of all available platform IDs."""
        return list(self.profiles.keys())
    
    def validate_profile(self, profile: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Validate a platform profile structure.
        
        Args:
            profile: Platform profile dict to validate
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Required top-level fields
        required_fields = ['platform_id', 'display_name', 'detection', 'event_strategy', 
                          'chat_id_extraction', 'message_detection', 'polling_config']
        
        for field in required_fields:
            if field not in profile:
                errors.append(f"Missing required field: {field}")
        
        # Validate detection section
        if 'detection' in profile:
            detection = profile['detection']
            if 'url_patterns' not in detection or not detection['url_patterns']:
                errors.append("detection.url_patterns is required and must not be empty")
        
        # Validate chat_id_extraction
        if 'chat_id_extraction' in profile:
            extractions = profile['chat_id_extraction']
            if not isinstance(extractions, list) or len(extractions) == 0:
                errors.append("chat_id_extraction must be a non-empty list")
            else:
                for i, extraction in enumerate(extractions):
                    if 'method' not in extraction:
                        errors.append(f"chat_id_extraction[{i}] missing 'method' field")
                    if 'priority' not in extraction:
                        errors.append(f"chat_id_extraction[{i}] missing 'priority' field")
        
        # Validate polling_config
        if 'polling_config' in profile:
            polling = profile['polling_config']
            if 'enabled' not in polling:
                errors.append("polling_config.enabled is required")
            if polling.get('enabled') and 'interval_ms' not in polling:
                errors.append("polling_config.interval_ms is required when polling is enabled")
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    def add_custom_profile(self, profile: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Add a custom platform profile.
        
        Args:
            profile: Platform profile dict
        
        Returns:
            Tuple of (success, error_message)
        """
        # Validate profile
        is_valid, errors = self.validate_profile(profile)
        if not is_valid:
            error_msg = "Profile validation failed: " + "; ".join(errors)
            logger.error(f"[PlatformDetector] {error_msg}")
            return False, error_msg
        
        platform_id = profile['platform_id']
        
        # Add to in-memory profiles
        self.profiles[platform_id] = profile
        
        # Optionally save to file (for persistence)
        try:
            self._save_custom_profile(profile)
            logger.info(f"[PlatformDetector] Added custom profile: {platform_id}")
            return True, None
        except Exception as e:
            error_msg = f"Failed to save custom profile: {e}"
            logger.error(f"[PlatformDetector] {error_msg}")
            return False, error_msg
    
    def _save_custom_profile(self, profile: Dict[str, Any]) -> None:
        """Save custom profile to a separate file."""
        # Save to custom_profiles directory
        custom_dir = self.profiles_path.parent / "custom_profiles"
        custom_dir.mkdir(exist_ok=True)
        
        platform_id = profile['platform_id']
        custom_file = custom_dir / f"{platform_id}.json"
        
        with open(custom_file, 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
        
        logger.info(f"[PlatformDetector] Saved custom profile to: {custom_file}")
    
    def load_custom_profiles(self) -> int:
        """
        Load all custom profiles from custom_profiles directory.
        
        Returns:
            Number of custom profiles loaded
        """
        custom_dir = self.profiles_path.parent / "custom_profiles"
        if not custom_dir.exists():
            return 0
        
        count = 0
        for profile_file in custom_dir.glob("*.json"):
            try:
                with open(profile_file, 'r', encoding='utf-8') as f:
                    profile = json.load(f)
                
                platform_id = profile.get('platform_id')
                if platform_id:
                    self.profiles[platform_id] = profile
                    count += 1
                    logger.info(f"[PlatformDetector] Loaded custom profile: {platform_id}")
            except Exception as e:
                logger.error(f"[PlatformDetector] Failed to load {profile_file}: {e}")
        
        return count
    
    def reload_profiles(self) -> None:
        """Reload all profiles from disk."""
        self._load_profiles()
        custom_count = self.load_custom_profiles()
        logger.info(
            f"[PlatformDetector] Reloaded profiles: "
            f"{len(self.profiles) - custom_count} built-in, {custom_count} custom"
        )


# Singleton instance
_detector_instance: Optional[PlatformDetector] = None


def get_platform_detector() -> PlatformDetector:
    """Get or create singleton PlatformDetector instance."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = PlatformDetector()
        # Load custom profiles on first initialization
        _detector_instance.load_custom_profiles()
    return _detector_instance


def detect_platform_from_browser(browser_session) -> Optional[str]:
    """
    Detect platform from an active browser session.
    
    Args:
        browser_session: Browser session object with get_url() and execute_script() methods
    
    Returns:
        platform_id if detected, None otherwise
    """
    try:
        detector = get_platform_detector()
        
        # Get current URL
        url = browser_session.get_url() if hasattr(browser_session, 'get_url') else None
        if not url:
            logger.warning("[PlatformDetector] Could not get URL from browser session")
            return None
        
        # Try to get DOM snapshot (optional, for better detection)
        dom_snapshot = None
        try:
            if hasattr(browser_session, 'execute_script'):
                dom_snapshot = browser_session.execute_script("return document.documentElement.outerHTML;")
        except Exception as e:
            logger.debug(f"[PlatformDetector] Could not get DOM snapshot: {e}")
        
        # Detect platform
        platform_id = detector.detect_platform(url, dom_snapshot)
        return platform_id
        
    except Exception as e:
        logger.error(f"[PlatformDetector] Error detecting platform from browser: {e}")
        return None
