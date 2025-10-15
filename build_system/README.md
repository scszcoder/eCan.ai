# eCan Build System Architecture

## Overview

The eCan build system is designed with strict separation between build-time and runtime code to ensure:
- Clean build environment
- No circular dependencies
- Reliable CI/CD pipeline
- Maintainable codebase

## Architecture Principles

### 1. Build-Runtime Separation

**Build System (`build_system/`)**:
- Contains only build-related code
- Independent logging system (`build_logger.py`)
- No imports from `utils/`, `config/`, or other runtime modules
- Self-contained with its own configuration (`build_config.json`)

**Runtime System**:
- Application code in `utils/`, `config/`, `bot/`, etc.
- Uses `utils/logger_helper.py` for runtime logging
- Packaged as data files during build process

### 2. Directory Structure

```
build_system/
├── build_logger.py          # Independent build logging
├── build_config.json        # Build configuration
├── unified_build.py         # Main build orchestrator
├── build_validator.py       # Environment validation
├── url_scheme_config.py     # URL scheme setup
├── minibuild_core.py        # PyInstaller spec generation
└── ...

utils/
├── logger_helper.py         # Runtime logging (NOT used by build system)
└── ...

config/
├── constants.py             # Runtime constants
└── ...
```

### 3. Logging Systems

**Build Logging** (`build_system/build_logger.py`):
- Simple, focused on build process
- Component-based logging
- No external dependencies
- Used only during build
**Runtime Logging** (`utils/logger_helper.py`):
- Rich logging with colors, crash handling
- Application-focused features
- Used only by running application

### 4.## S3 Upload Documentation

### Quick Links

- **[Quick Fix](./docs/QUICK_FIX.md)** - Fix "Access Denied" error immediately
- **[Troubleshooting](./docs/TROUBLESHOOTING.md)** - Common issues and solutions
- **[S3 Setup Guide](./docs/AWS_S3_RELEASE_SETUP.md)** - Complete AWS S3 configuration
- **[Appcast Management](./docs/APPCAST_MANAGEMENT.md)** - OTA update management
- User preferences
- Runtime constants

## Key Files

### Build System Core
- `unified_build.py`: Main build orchestrator
- `minibuild_core.py`: PyInstaller spec generation
- `build_validator.py`: Environment validation
- `build_logger.py`: Build-specific logging

### Platform Support
- `platform_handler.py`: Platform detection
- `url_scheme_config.py`: URL scheme configuration

### Utilities
- `build_utils.py`: Build helper functions
- `build_cleaner.py`: Build cleanup

## Usage

### Local Development
```bash
python build.py prod --version 1.0.0
```

### CI/CD
The build system is designed to work in GitHub Actions with:
- Virtual environment management
- Dependency validation
- Cross-platform support

## Maintenance Guidelines

1. **Never import runtime modules in build system**
2. **Use build_logger for all build-time logging**
3. **Keep build_config.json as single source of truth**
4. **Test build system independently of runtime code**
5. **Avoid emoji or special characters in build scripts**

## Troubleshooting

### Common Issues
1. **Import errors**: Check for runtime imports in build system
2. **Logging issues**: Ensure using correct logger for context
3. **Dependency issues**: Verify virtual environment setup
4. **Encoding issues**: Avoid emoji in build scripts

### Debug Mode
```bash
python build.py prod --version 1.0.0 --verbose
```
