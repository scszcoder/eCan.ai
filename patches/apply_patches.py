#!/usr/bin/env python3
"""
Apply Python 3.14 compatibility patches to site-packages.

This script applies necessary patches to third-party libraries that are
incompatible with Python 3.14's stricter asyncio.timeout() requirements.

Usage:
    python -m patches.apply_patches [--check] [--verbose] [--dry-run]

Options:
    --check     Only check if patches are applied, don't apply them
    --verbose   Show detailed output
    --dry-run   Show what would be changed without actually changing files
"""

import argparse
import importlib.util
import re
import sys
from pathlib import Path
from typing import Callable


# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'


def get_site_packages_path() -> Path:
    """Get the site-packages directory for the current Python environment."""
    # Try to find site-packages from a known installed package
    for module_name in ['websockets', 'httpx', 'pydantic']:
        spec = importlib.util.find_spec(module_name)
        if spec and spec.origin:
            # Go up from the module to find site-packages
            module_path = Path(spec.origin)
            for parent in module_path.parents:
                if parent.name == 'site-packages':
                    return parent
    
    # Fallback: use the first site-packages in sys.path
    for path in sys.path:
        if 'site-packages' in path:
            return Path(path)
    
    raise RuntimeError("Could not find site-packages directory")


class Patch:
    """Represents a single patch to apply to a file."""
    
    def __init__(
        self,
        library: str,
        relative_path: str,
        description: str,
        old_code: str,
        new_code: str,
        check_fn: Callable[[str], bool] | None = None,
    ):
        self.library = library
        self.relative_path = relative_path
        self.description = description
        self.old_code = old_code
        self.new_code = new_code
        self.check_fn = check_fn or (lambda content: self.new_code in content)
    
    def get_file_path(self, site_packages: Path) -> Path:
        return site_packages / self.relative_path
    
    def is_applied(self, site_packages: Path) -> bool:
        """Check if this patch has already been applied."""
        file_path = self.get_file_path(site_packages)
        if not file_path.exists():
            return False
        content = file_path.read_text(encoding='utf-8')
        return self.check_fn(content)
    
    def apply(self, site_packages: Path, dry_run: bool = False) -> tuple[bool, str]:
        """Apply this patch. Returns (success, message)."""
        file_path = self.get_file_path(site_packages)
        
        if not file_path.exists():
            return False, f"File not found: {file_path}"
        
        content = file_path.read_text(encoding='utf-8')
        
        # Check if already applied
        if self.check_fn(content):
            return True, "Already applied"
        
        # Check if old code exists
        if self.old_code not in content:
            return False, f"Could not find code to patch (library may have been updated)"
        
        # Apply the patch
        new_content = content.replace(self.old_code, self.new_code, 1)
        
        if dry_run:
            return True, "Would apply patch (dry-run)"
        
        # Create backup
        backup_path = file_path.with_suffix(file_path.suffix + '.bak')
        if not backup_path.exists():
            file_path.rename(backup_path)
            backup_path.rename(backup_path)  # Restore original name
            file_path.write_text(content, encoding='utf-8')  # Write original first
        
        # Write patched content
        file_path.write_text(new_content, encoding='utf-8')
        
        return True, "Patch applied successfully"


# =============================================================================
# PATCH DEFINITIONS
# =============================================================================

PATCHES: list[Patch] = [
    # -------------------------------------------------------------------------
    # websockets library
    # -------------------------------------------------------------------------
    Patch(
        library="websockets",
        relative_path="websockets/asyncio/compatibility.py",
        description="Use bundled async_timeout on Python 3.14+ (asyncio.timeout requires task context)",
        old_code='''if sys.version_info[:2] >= (3, 11):
    from asyncio import timeout as asyncio_timeout''',
        new_code='''if sys.version_info[:2] >= (3, 11):
    if sys.version_info[:2] >= (3, 14):
        # Python 3.14: asyncio.timeout requires task context, use bundled async_timeout
        from .async_timeout import timeout as asyncio_timeout
    else:
        from asyncio import timeout as asyncio_timeout''',
    ),
    
    Patch(
        library="websockets",
        relative_path="websockets/asyncio/async_timeout.py",
        description="Handle _task is None in _on_timeout() for Python 3.14",
        old_code='''    def _on_timeout(self) -> None:
        assert self._task is not None
        self._task.cancel()''',
        new_code='''    def _on_timeout(self) -> None:
        if self._task is not None:
            self._task.cancel()
        self._state = _State.TIMEOUT''',
    ),
    
    # -------------------------------------------------------------------------
    # cdp_use library
    # -------------------------------------------------------------------------
    Patch(
        library="cdp_use",
        relative_path="cdp_use/client.py",
        description="Disable open_timeout in websockets.connect() to avoid asyncio.timeout",
        old_code='''        connect_kwargs = {
            "max_size": self.max_ws_frame_size,
        }''',
        new_code='''        connect_kwargs = {
            "max_size": self.max_ws_frame_size,
            # Python 3.14: avoid asyncio.timeout in websockets by disabling open_timeout
            "open_timeout": None,
        }''',
        check_fn=lambda content: '"open_timeout": None' in content or "'open_timeout': None" in content,
    ),
    
    # -------------------------------------------------------------------------
    # bubus library
    # -------------------------------------------------------------------------
    Patch(
        library="bubus",
        relative_path="bubus/models.py",
        description="Replace asyncio.wait_for() with polling loop in event_results_filtered()",
        old_code='''        if _timeout is not None:
            try:
                await asyncio.wait_for(self.event_completed_signal.wait(), timeout=_timeout)
            except asyncio.TimeoutError:
                raise''',
        new_code='''        if _timeout is not None:
            # Python 3.14 fix: asyncio.wait_for requires task context, use polling loop
            _start = asyncio.get_event_loop().time()
            while not self.event_completed_signal.is_set():
                _elapsed = asyncio.get_event_loop().time() - _start
                if _elapsed >= _timeout:
                    raise asyncio.TimeoutError()
                await asyncio.sleep(0.01)''',
        check_fn=lambda content: 'Python 3.14 fix' in content and 'polling loop' in content.lower(),
    ),
    
    Patch(
        library="bubus",
        relative_path="bubus/service.py",
        description="Replace asyncio.wait_for() with polling loop in execute_handler()",
        old_code='''                result_value = await asyncio.wait_for(handler_task, timeout=event_result.timeout)''',
        new_code='''                # Python 3.14 fix: asyncio.wait_for requires task context, use polling loop
                if event_result.timeout is not None:
                    start_time = asyncio.get_event_loop().time()
                    while not handler_task.done():
                        _elapsed = asyncio.get_event_loop().time() - start_time
                        if _elapsed >= event_result.timeout:
                            handler_task.cancel()
                            raise asyncio.TimeoutError()
                        await asyncio.sleep(0.01)
                result_value = await handler_task''',
        check_fn=lambda content: 'Python 3.14 fix' in content and 'execute_handler' in content,
    ),
    
    # -------------------------------------------------------------------------
    # browser_use library
    # -------------------------------------------------------------------------
    Patch(
        library="browser_use",
        relative_path="browser_use/browser/session_manager.py",
        description="Replace asyncio.wait_for() with polling loop in ensure_valid_focus() - first location",
        old_code='''                try:
                    await asyncio.wait_for(self._recovery_complete_event.wait(), timeout=timeout)''',
        new_code='''                # Python 3.14 fix: use polling loop instead of asyncio.wait_for
                try:
                    _recovery_start = asyncio.get_event_loop().time()
                    while not self._recovery_complete_event.is_set():
                        if asyncio.get_event_loop().time() - _recovery_start > timeout:
                            raise TimeoutError()
                        await asyncio.sleep(0.01)''',
        check_fn=lambda content: 'Python 3.14 fix' in content and '_recovery_start' in content,
    ),
    
    Patch(
        library="browser_use",
        relative_path="browser_use/browser/watchdogs/dom_watchdog.py",
        description="Replace asyncio.wait_for() with polling loop for page title",
        old_code='''            try:
                title = await asyncio.wait_for(
                    self.browser_session.get_current_page_title(),
                    timeout=1.0
                )''',
        new_code='''            # Python 3.14 fix: use polling loop instead of asyncio.wait_for
            try:
                _title_task = asyncio.create_task(self.browser_session.get_current_page_title())
                _title_start = time.time()
                while not _title_task.done():
                    if time.time() - _title_start > 1.0:
                        _title_task.cancel()
                        raise asyncio.TimeoutError()
                    await asyncio.sleep(0.01)
                title = _title_task.result()''',
        check_fn=lambda content: 'Python 3.14 fix' in content and '_title_task' in content,
    ),
    
    Patch(
        library="browser_use",
        relative_path="browser_use/browser/watchdogs/dom_watchdog.py",
        description="Replace asyncio.wait_for() with polling loop for page info",
        old_code='''            try:
                page_info = await asyncio.wait_for(
                    self._get_page_info(),
                    timeout=1.0
                )''',
        new_code='''            # Python 3.14 fix: use polling loop instead of asyncio.wait_for
            try:
                _page_info_task = asyncio.create_task(self._get_page_info())
                _page_info_start = time.time()
                while not _page_info_task.done():
                    if time.time() - _page_info_start > 1.0:
                        _page_info_task.cancel()
                        raise asyncio.TimeoutError()
                    await asyncio.sleep(0.01)
                page_info = _page_info_task.result()''',
        check_fn=lambda content: 'Python 3.14 fix' in content and '_page_info_task' in content,
    ),
    
    Patch(
        library="browser_use",
        relative_path="browser_use/browser/session.py",
        description="Replace httpx.AsyncClient with sync client in thread for _wait_for_cdp_url",
        old_code='''            async with httpx.AsyncClient() as client:
                response = await client.get(cdp_url)''',
        new_code='''            # Python 3.14 fix: use sync httpx in thread to avoid sniffio detection issues
            def _sync_fetch():
                with httpx.Client() as client:
                    return client.get(cdp_url)
            response = await asyncio.to_thread(_sync_fetch)''',
        check_fn=lambda content: 'Python 3.14 fix' in content and '_sync_fetch' in content,
    ),
]


def apply_all_patches(
    verbose: bool = False,
    dry_run: bool = False,
    site_packages: Path | None = None,
) -> tuple[int, int, int]:
    """
    Apply all patches.
    
    Returns:
        Tuple of (applied_count, already_applied_count, failed_count)
    """
    if site_packages is None:
        site_packages = get_site_packages_path()
    
    if verbose:
        print(f"{BLUE}Site-packages path: {site_packages}{RESET}")
        print()
    
    applied = 0
    already_applied = 0
    failed = 0
    
    current_library = None
    
    for patch in PATCHES:
        if patch.library != current_library:
            current_library = patch.library
            if verbose:
                print(f"{BOLD}[{patch.library}]{RESET}")
        
        success, message = patch.apply(site_packages, dry_run=dry_run)
        
        if success:
            if "Already applied" in message:
                already_applied += 1
                if verbose:
                    print(f"  {GREEN}✓{RESET} {patch.description} - {message}")
            else:
                applied += 1
                print(f"  {GREEN}✓{RESET} {patch.description} - {message}")
        else:
            failed += 1
            print(f"  {RED}✗{RESET} {patch.description} - {message}")
        
    return applied, already_applied, failed


def check_patches_applied(
    verbose: bool = False,
    site_packages: Path | None = None,
) -> tuple[int, int]:
    """
    Check which patches are applied.
    
    Returns:
        Tuple of (applied_count, not_applied_count)
    """
    if site_packages is None:
        site_packages = get_site_packages_path()
    
    if verbose:
        print(f"{BLUE}Site-packages path: {site_packages}{RESET}")
        print()
    
    applied = 0
    not_applied = 0
    
    current_library = None
    
    for patch in PATCHES:
        if patch.library != current_library:
            current_library = patch.library
            if verbose:
                print(f"{BOLD}[{patch.library}]{RESET}")
        
        if patch.is_applied(site_packages):
            applied += 1
            if verbose:
                print(f"  {GREEN}✓{RESET} {patch.description}")
        else:
            not_applied += 1
            print(f"  {YELLOW}○{RESET} {patch.description} - NOT APPLIED")
    
    return applied, not_applied


def main():
    parser = argparse.ArgumentParser(
        description="Apply Python 3.14 compatibility patches to site-packages"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check if patches are applied, don't apply them",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without actually changing files",
    )
    
    args = parser.parse_args()
    
    print(f"{BOLD}Python 3.14 Asyncio Compatibility Patches{RESET}")
    print(f"Python version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    print()
    
    if sys.version_info[:2] < (3, 14):
        print(f"{YELLOW}Warning: You are running Python {sys.version_info.major}.{sys.version_info.minor}")
        print(f"These patches are only needed for Python 3.14+{RESET}")
        print()
    
    try:
        site_packages = get_site_packages_path()
    except RuntimeError as e:
        print(f"{RED}Error: {e}{RESET}")
        sys.exit(1)
    
    if args.check:
        applied, not_applied = check_patches_applied(verbose=args.verbose, site_packages=site_packages)
        print()
        print(f"Summary: {GREEN}{applied} applied{RESET}, {YELLOW}{not_applied} not applied{RESET}")
        sys.exit(0 if not_applied == 0 else 1)
    else:
        if args.dry_run:
            print(f"{YELLOW}DRY RUN - no files will be modified{RESET}")
            print()
        
        applied, already_applied, failed = apply_all_patches(
            verbose=args.verbose,
            dry_run=args.dry_run,
            site_packages=site_packages,
        )
        
        print()
        print(f"Summary: {GREEN}{applied} applied{RESET}, {BLUE}{already_applied} already applied{RESET}, {RED}{failed} failed{RESET}")
        
        if failed > 0:
            print()
            print(f"{YELLOW}Some patches failed. This may be because:")
            print("  - The library version has changed")
            print("  - The library is not installed")
            print(f"  - The code has already been modified differently{RESET}")
            sys.exit(1)


if __name__ == "__main__":
    main()
