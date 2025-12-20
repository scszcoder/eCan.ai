"""
Migration configuration for database version management.

This module provides static configuration for migration versions,
avoiding the need to load all migration scripts just to determine
the latest version.
"""

# Current supported latest database version
LATEST_DATABASE_VERSION = "3.0.7"

# Version history (for quick version comparison and path calculation)
VERSION_HISTORY = [
    "1.0.0",
    "1.0.1",
    "2.0.0",
    "3.0.0",
    "3.0.1",
    "3.0.2",
    "3.0.3",
    "3.0.4",
    "3.0.5",
    "3.0.6",
    "3.0.7"
]

# Version dependencies (version -> previous_version)
VERSION_DEPENDENCIES = {
    "1.0.1": "1.0.0",
    "2.0.0": "1.0.1",
    "3.0.0": "2.0.0",
    "3.0.1": "3.0.0",
    "3.0.2": "3.0.1",
    "3.0.3": "3.0.2",
    "3.0.4": "3.0.3",
    "3.0.5": "3.0.4",
    "3.0.6": "3.0.5",
    "3.0.7": "3.0.6"
}

def get_latest_version() -> str:
    """
    Get the latest available database version.
    
    Returns:
        str: Latest version string
    """
    return LATEST_DATABASE_VERSION

def is_version_supported(version: str) -> bool:
    """
    Check if a version is supported.
    
    Args:
        version: Version string to check
        
    Returns:
        bool: True if version is supported
    """
    return version in VERSION_HISTORY

def get_version_path(from_version: str, to_version: str) -> list[str]:
    """
    Get the migration path from one version to another.
    
    Args:
        from_version: Starting version
        to_version: Target version
        
    Returns:
        list[str]: List of versions in migration path
    """
    if not is_version_supported(from_version) or not is_version_supported(to_version):
        return []
    
    from_idx = VERSION_HISTORY.index(from_version)
    to_idx = VERSION_HISTORY.index(to_version)
    
    if from_idx >= to_idx:
        return []  # No migration needed or downgrade not supported
    
    return VERSION_HISTORY[from_idx + 1:to_idx + 1]

def version_to_tuple(version: str) -> tuple:
    """
    Convert version string to tuple for comparison.
    
    Args:
        version: Version string like "1.0.0"
        
    Returns:
        tuple: Version as tuple like (1, 0, 0)
    """
    try:
        return tuple(map(int, version.split('.')))
    except (ValueError, AttributeError):
        return (0, 0, 0)

def compare_versions(version1: str, version2: str) -> int:
    """
    Compare two version strings.
    
    Args:
        version1: First version
        version2: Second version
        
    Returns:
        int: -1 if version1 < version2, 0 if equal, 1 if version1 > version2
    """
    v1_tuple = version_to_tuple(version1)
    v2_tuple = version_to_tuple(version2)
    
    if v1_tuple < v2_tuple:
        return -1
    elif v1_tuple > v2_tuple:
        return 1
    else:
        return 0
