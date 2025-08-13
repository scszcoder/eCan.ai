"""
PyInstaller hook for anyio package.

This hook ensures that anyio's backend modules are properly included in the PyInstaller bundle.
AnyIO dynamically imports backend modules at runtime, which PyInstaller's static analysis misses.

Fixes the common error:
ModuleNotFoundError: No module named 'anyio._backends._asyncio'
KeyError: 'asyncio'
"""

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Collect all submodules from anyio._backends
# This includes _asyncio, _trio, and any other backends
hiddenimports = collect_submodules('anyio._backends')

# Also collect the main anyio modules that might be dynamically imported
hiddenimports.extend([
    'anyio',
    'anyio.abc',
    'anyio.streams',
    'anyio.streams.memory',
    'anyio.streams.stapled',
    'anyio.streams.text',
    'anyio.streams.tls',
    'anyio.lowlevel',
    'anyio.from_thread',
    'anyio.to_thread',
    'anyio.to_process',
    'anyio._core',
    'anyio._core._eventloop',
    'anyio._core._exceptions',
    'anyio._core._fileio',
    'anyio._core._signals',
    'anyio._core._sockets',
    'anyio._core._subprocesses',
    'anyio._core._synchronization',
    'anyio._core._tasks',
    'anyio._core._testing',
])

# Collect any data files that anyio might need
datas = collect_data_files('anyio')

# Print debug information during build
print(f"[HOOK-ANYIO] Collected {len(hiddenimports)} hidden imports for anyio")
print(f"[HOOK-ANYIO] Hidden imports: {hiddenimports}")
if datas:
    print(f"[HOOK-ANYIO] Collected {len(datas)} data files for anyio")
