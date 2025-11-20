# Build Information Module

## Architecture

This directory contains the unified build information system that works identically in both **development** and **production** environments.

### Files

```
config/
├── __init__.py
├── build_info.py          # Core logic (hand-written, version controlled)
├── build_data.py          # Build data (auto-generated, gitignored)
└── README.md              # This file
```

### Design Principles

1. **Development and Production Consistency**: Same code structure in both environments
2. **Unified Banner Template**: Single banner implementation, only data differs
3. **Consistent Data Structure**: Both environments use the same data format
4. **Automatic Fallback**: Local development works without manual setup

---

## File Descriptions

### `build_info.py` (Core Logic)

**Purpose**: Contains all logic, banner templates, and utility functions

**Features**:
- Loads data from `build_data.py` (if exists)
- Auto-generates fallback data for local development
- Provides unified API for accessing build information
- Exports constants: `VERSION`, `ENVIRONMENT`, `CHANNEL`, etc.
- Utility functions: `get_banner()`, `get_version_string()`, `is_production()`, etc.

**Version Control**: ✅ Committed to Git

### `build_data.py` (Generated Data)

**Purpose**: Pure data file generated at build time

**Content**: Single `BUILD_DATA` dictionary containing:
```python
BUILD_DATA = {
    "version": "1.0.0",
    "environment": "production",
    "channel": "stable",
    "git_commit": "abc123",
    "git_branch": "main",
    "git_commit_time": "2025-01-01 12:00:00",
    "build_time": "2025-01-01 12:00:00",
    "build_timestamp": 1704110400.0,
    "ota_enabled": True,
    "signature_required": True,
    "is_fallback": False
}
```

**Generation**: Run `python build_system/scripts/inject_build_info.py --environment <env>`

**Version Control**: ❌ Gitignored (auto-generated)

---

## Usage

### In Application Code

```python
# Import from the unified module
from config.build_info import (
    VERSION,
    ENVIRONMENT,
    get_banner,
    get_startup_banner,
    get_version_string,
    is_production,
    BUILD_INFO
)

# Display simple banner
print(get_banner())

# Display startup banner (with system info)
print(get_startup_banner())

# Check environment
if is_production():
    print("Running in production")

# Get version string
version = get_version_string()  # e.g., "1.0.0" or "1.0.0-dev-abc123"

# Access all info
print(BUILD_INFO)
```

### Generate Build Data

```bash
# For production build
python build_system/scripts/inject_build_info.py \
    --version 1.0.0 \
    --environment production

# For development (uses VERSION file)
python build_system/scripts/inject_build_info.py \
    --environment development
```

### Local Development (No Setup Required)

When `build_data.py` doesn't exist, `build_info.py` automatically:
1. Reads version from `VERSION` file (or uses "0.0.0-dev")
2. Gets Git information from local repository
3. Sets environment to "development"
4. Generates fallback data

**Result**: You can start coding immediately without running any build scripts!

---

## Behavior Comparison

### Before (Old Architecture)

❌ **Problems**:
- `build_info.py` was entirely generated (logic + data mixed)
- Local development failed if script wasn't run
- Banner logic duplicated in generated file
- Different code paths for dev vs prod

### After (New Architecture)

✅ **Solutions**:
- Core logic is permanent, only data is generated
- Local development works automatically with fallback
- Single banner template, only data differs
- Identical code structure in all environments

---

## Environment-Specific Behavior

### Production

```python
VERSION = "1.0.0"
ENVIRONMENT = "production"
CHANNEL = "stable"
IS_FALLBACK = False
get_version_string() → "1.0.0"
```

### Staging

```python
VERSION = "1.0.0"
ENVIRONMENT = "staging"
CHANNEL = "stable"
IS_FALLBACK = False
get_version_string() → "1.0.0-staging"
```

### Development (with build_data.py)

```python
VERSION = "1.0.0"
ENVIRONMENT = "development"
CHANNEL = "dev"
IS_FALLBACK = False
get_version_string() → "1.0.0-dev-abc123"
```

### Development (fallback, no build_data.py)

```python
VERSION = "0.0.0-dev"  # or from VERSION file
ENVIRONMENT = "development"
CHANNEL = "dev"
IS_FALLBACK = True  # ⚠️ Warning shown
get_version_string() → "0.0.0-dev-dev-abc123"
```

---

## Testing

### Test the Example

```bash
# Run the example script
python examples/show_banner.py

# Show full banner
python examples/show_banner.py --full

# Show short banner (for logs)
python examples/show_banner.py --short

# Show detailed info
python examples/show_banner.py --info
```

### Check Version Consistency

```bash
python build_system/scripts/check_version_consistency.py
```

---

## CI/CD Integration

The build system automatically calls `inject_build_info.py` during the build process:

```yaml
# In .github/workflows/release.yml
- name: Inject build information
  run: |
    python build_system/scripts/inject_build_info.py \
      --version ${{ needs.validate-tag.outputs.version }} \
      --environment ${{ needs.validate-tag.outputs.environment }}
```

---

## Migration Guide

If you have existing code importing from the old `build_info.py`:

### Old Code (Still Works!)

```python
from config.build_info import VERSION, get_banner
```

### New Code (Recommended)

```python
# Same import! The API is unchanged
from config.build_info import VERSION, get_banner, IS_FALLBACK

# New utilities available
from config.build_info import is_production, is_development
```

**No changes required** - the API is backward compatible!

---

## FAQ

**Q: Do I need to run inject_build_info.py for local development?**  
A: No! The fallback mechanism handles it automatically.

**Q: Will the fallback warning affect my application?**  
A: It's just a Python warning. You can suppress it or run the script to generate proper data.

**Q: Can I commit build_data.py to Git?**  
A: No, it's gitignored. It should be generated during the build process.

**Q: How do I know if I'm using fallback data?**  
A: Check the `IS_FALLBACK` constant or look for the warning message.

**Q: What if VERSION file doesn't exist?**  
A: Fallback uses "0.0.0-dev" as the default version.

---

## Related Files

- `build_system/scripts/inject_build_info.py` - Data generation script
- `build_system/scripts/check_version_consistency.py` - Consistency checker
- `examples/show_banner.py` - Usage example
- `.gitignore` - Excludes `build_data.py`
