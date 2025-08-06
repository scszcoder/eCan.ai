# eCan Build System

## Overview

The eCan build system integrates automated dynamic import detection functionality, automatically detecting all dynamic imports in the project and generating a complete hiddenimports list to ensure all dependencies are correctly packaged.

## Core Features

### 1. Automated Dynamic Import Detection
- **No manual maintenance of package name lists required**
- **Automatically detects all dynamic import patterns**
- **Intelligently identifies scientific computing libraries, machine learning libraries, web frameworks, etc.**

### 2. Multi-mode Build Support
- **fast**: Fast build (for development and debugging)
- **dev**: Development build (with debug information)
- **prod**: Production build (fully optimized)

### 3. Intelligent Package Detection
- Automatically detects all submodules of installed packages
- Intelligently identifies project-specific package structures
- Automatically tests module importability

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

### Run Detector Independently

```bash
# Run smart dynamic import detection
python build_system/smart_dynamic_detector.py

# Output example:
🧠 Starting smart dynamic import detection...
📝 Phase 1: Detecting project-specific dynamic imports...
Found project-specific imports: 200
💻 Phase 2: Detecting actual dynamic imports in code...
Analyzing 150 Python files...
Found code dynamic imports: 25
🔑 Phase 3: Detecting critical dependency dynamic imports...
Detecting 100 critical dynamic import patterns...
Found critical dependencies: 80
🔄 Phase 4: Intelligent merging and optimization...
✅ Smart detection completed: 305 modules
💾 Smart detection results saved to: build_system/smart_detected_modules.json
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