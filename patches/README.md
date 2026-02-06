# Python 3.14 Compatibility Patches

This directory contains automated patch scripts for third-party libraries that are incompatible with Python 3.14's stricter `asyncio.timeout()` requirements.

## Quick Start

```bash
# Apply all patches
python -m patches.apply_patches

# Check which patches are applied
python -m patches.apply_patches --check

# Dry run (see what would change without modifying files)
python -m patches.apply_patches --dry-run

# Verbose output
python -m patches.apply_patches --verbose
```

## When to Run

Run the patch script after:
- Fresh `pip install` of dependencies
- Updating any of the patched libraries (`websockets`, `cdp_use`, `bubus`, `browser_use`)
- Setting up a new development environment

## Patched Libraries

| Library | Files Patched | Reason |
|---------|---------------|--------|
| `websockets` | `asyncio/compatibility.py`, `asyncio/async_timeout.py` | Use bundled async_timeout on Python 3.14+ |
| `cdp_use` | `client.py` | Disable open_timeout to avoid asyncio.timeout |
| `bubus` | `models.py`, `service.py` | Replace asyncio.wait_for with polling loops |
| `browser_use` | `session_manager.py`, `session.py`, `dom_watchdog.py` | Replace asyncio.wait_for with polling loops |

## How It Works

The patch script:
1. Locates your Python environment's `site-packages` directory
2. Searches for specific code patterns in each library
3. Replaces them with Python 3.14-compatible alternatives
4. Reports success/failure for each patch

## Adding New Patches

To add a new patch, edit `apply_patches.py` and add a new `Patch` object to the `PATCHES` list:

```python
Patch(
    library="library_name",
    relative_path="library_name/module.py",
    description="Brief description of what this patch does",
    old_code='''exact code to find''',
    new_code='''replacement code''',
    check_fn=lambda content: 'unique string' in content,  # Optional
)
```

## Troubleshooting

### "Could not find code to patch"
The library version may have changed. Check if:
- The library was updated and the code structure changed
- The patch was already applied manually with different code

### "File not found"
The library may not be installed. Run:
```bash
pip install websockets cdp_use bubus browser_use
```

## Integration with pip

You can add a post-install hook to automatically apply patches. Add to your `setup.py` or use a shell alias:

```bash
# Shell alias example
alias pip-install='pip install && python -m patches.apply_patches'
```

Or add to your CI/CD pipeline after `pip install -r requirements.txt`.

## Related Documentation

See `docs/PYTHON_314_ASYNCIO_COMPATIBILITY.md` for detailed explanation of:
- Why these patches are needed
- The root cause (Python 3.14 asyncio changes)
- Manual patch instructions if the script fails
