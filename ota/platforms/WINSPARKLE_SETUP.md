# winSparkle Setup Guide

winSparkle is a C++ library for Windows applications that provides automatic update functionality. It is **not** a Python package and cannot be installed via pip.

## Installation Options

### Option 1: Download Pre-built Binaries (Recommended)

1. Download the latest winSparkle release from: https://github.com/vslavik/winsparkle/releases
2. Extract the archive
3. Copy the following files to your application directory:
   - `winsparkle.dll` (main library)
   - `winsparkle.lib` (if building C++ extensions)

### Option 2: Build from Source

1. Clone the repository:
   ```bash
   git clone https://github.com/vslavik/winsparkle.git
   ```

2. Build using Visual Studio:
   - Open `winsparkle.sln` in Visual Studio
   - Build the solution in Release mode
   - Copy the generated `winsparkle.dll` to your application directory

## Integration with ECBot

### File Placement

Place `winsparkle.dll` in one of these locations:
- `{app_home_path}/winsparkle.dll`
- `{app_home_path}/lib/winsparkle.dll`
- `{app_home_path}/bin/winsparkle.dll`
- `C:\Program Files\ECBot\winsparkle.dll`
- `C:\Program Files (x86)\ECBot\winsparkle.dll`

### CLI Tool (Optional)

If you need a command-line interface for winSparkle:

1. Create a simple wrapper executable or batch script
2. Name it `winsparkle-cli.exe` or `winsparkle_cli.exe`
3. Place it in the same directories as the DLL

Example batch script (`winsparkle-cli.bat`):
```batch
@echo off
if "%1"=="check" (
    echo Checking for updates...
    rem Add your update check logic here
    exit /b 0
)
if "%1"=="install" (
    echo Installing update...
    rem Add your update install logic here
    exit /b 0
)
echo Usage: winsparkle-cli.exe [check|install]
exit /b 1
```

## Python Integration

The OTA system will automatically detect winSparkle if it's properly installed:

```python
from ota import OTAUpdater

# The updater will automatically use winSparkle on Windows
updater = OTAUpdater()
has_update = updater.check_for_updates()
```

## Troubleshooting

### Common Issues

1. **DLL not found**: Ensure `winsparkle.dll` is in the application directory or system PATH
2. **CLI tool not found**: The OTA system will fall back to generic HTTP updates if CLI tools are not available
3. **Permission errors**: Run the application as administrator if needed

### Verification

To verify winSparkle is properly installed:

```python
import os
from ota.core.platforms import WinSparkleUpdater
from ota.core.updater import OTAUpdater

updater = OTAUpdater()
if hasattr(updater.platform_updater, '_find_winsparkle_dll'):
    dll_path = updater.platform_updater._find_winsparkle_dll()
    if dll_path:
        print(f"winSparkle found at: {dll_path}")
    else:
        print("winSparkle DLL not found")
```

## Alternative: Generic HTTP Updates

If winSparkle is not available, the OTA system will automatically fall back to generic HTTP-based updates, which work on all platforms but may have fewer features.

## References

- [winSparkle Official Website](https://winsparkle.org/)
- [winSparkle GitHub Repository](https://github.com/vslavik/winsparkle)
- [winSparkle Documentation](https://github.com/vslavik/winsparkle/wiki)
