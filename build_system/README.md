# eCan Build System

## Overview

The eCan build system provides a unified and simplified build flow powered by MiniSpecBuilder. It builds the core app via PyInstaller spec generation and optionally builds frontend and installers.

## Core Features

### 1. Unified Build Path
- Single entry: build.py
- Core builder: build_system/minibuild_core.py (MiniSpecBuilder)
- Optional: FrontendBuilder and InstallerBuilder (build_system/ecan_build.py)

### 2. Multi-mode Build Support
- **fast**: Fast build (for development and debugging)
- **dev**: Development build (with debug information)
- **prod**: Production build (fully optimized)

### 3. Minimal Spec Generation
- Generate pre-safe hooks for known argparse-at-import modules
- Honor build_system/build_config.json for data files, excludes, hiddenimports
- Keep spec and build logs easy to reason about

## Usage

### Basic Build Commands

```bash
# Fast build (for development and debugging)
python build.py fast

# Development build
python build.py dev

# Production build
python build.py prod

# Force rebuild
python build.py prod --force

# Skip frontend build
python build.py prod --skip-frontend

# Skip installer creation
python build.py prod --skip-installer
```

### Build Commands

```bash
# Fast build (dev onedir)
python build.py fast --skip-frontend

# Production build with installer
python build.py prod

# Development build with console
python build.py dev --skip-installer
```

## Problems Solved

### Dynamic Import Issues
- `ModuleNotFoundError: No module named 'scipy.spatial'`
- `ModuleNotFoundError: No module named 'numpy.random'`
- All similar dynamic import errors

### Covered Library Types
- **Scientific Computing Libraries**: scipy, numpy, pandas, matplotlib, sklearn
- **Machine Learning Libraries**: transformers, torch, tensorflow
- **Web Frameworks**: fastapi, starlette, uvicorn
- **Databases**: sqlalchemy, django
- **AI Libraries**: openai, langchain
- **Other Common Libraries**: pydantic, click, rich, cryptography, etc.

## Technical Features

### 1. Intelligent Optimization
- Limits maximum module count (1000), avoiding overly long spec files
- Priority sorting, keeping the most important modules
- Intelligent filtering, avoiding redundant detection

### 2. Precise Detection
- Project-specific dynamic imports (highest priority)
- Actual dynamic imports in code
- Critical dependency dynamic imports

### 3. Efficient Coverage
- Covers the most common dynamic import issues
- Automatically identifies critical patterns
- Avoids over-detection

## Configuration Files

The build system uses the following configuration files:

- `build_config.json`: Main configuration file
- `smart_dynamic_detector.py`: Dynamic import detector
- `ecan_build.py`: Core build system

### Configuration Structure

```json
{
  "app_info": {
    "name": "eCan",
    "version": "1.0.0",
    "main_script": "main.py"
  },
  "build_modes": {
    "fast": {
      "use_cache": true,
      "parallel": true,
      "strip_debug": false
    },
    "dev": {
      "use_cache": false,
      "parallel": true,
      "console": true
    },
    "prod": {
      "use_cache": false,
      "parallel": true,
      "strip_debug": true
    }
  }
}
```

## Troubleshooting

### 1. Detector Run Failure

```bash
# Check Python environment
python -c "import sys; print(sys.path)"

# Manually run detector
python build_system/smart_dynamic_detector.py
```

### 2. Missing Modules During Build

```bash
# View detailed error information
python build.py prod --verbose

# Check detection results
cat build_system/smart_detected_modules.json
```

### 3. Specific Module Missing

```bash
# Check if module exists
python -c "import module_name"
``` 