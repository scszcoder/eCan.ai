#!/bin/bash
# Build script for skill_editor_lambda on Linux
# This script creates a Lambda-compatible package by:
# 1. Copying source modules
# 2. Overriding files that have Lambda-incompatible dependencies
# 3. NOT bundling pip packages (use Lambda layers or pre-installed packages)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ECAN_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
BUILD_DIR="/tmp/skill_editor_lambda_build"
ZIP_FILE="/tmp/skill_editor_agent.zip"

echo "========================================"
echo "Building skill_editor_lambda package"
echo "========================================"
echo "ECAN_ROOT: $ECAN_ROOT"
echo "BUILD_DIR: $BUILD_DIR"

# Clean up
echo "[1/5] Cleaning build directory..."
rm -rf "$BUILD_DIR" "$ZIP_FILE"
mkdir -p "$BUILD_DIR"

# Copy handler as lambda_function.py
echo "[2/5] Copying Lambda entry point..."
cp "$ECAN_ROOT/lambda_functions/skill_editor_lambda/handler.py" "$BUILD_DIR/lambda_function.py"
echo "lambda_handler = handler" >> "$BUILD_DIR/lambda_function.py"

# Copy source modules
echo "[3/5] Copying source modules..."
cp -r "$ECAN_ROOT/agent" "$BUILD_DIR/agent"
cp -r "$ECAN_ROOT/utils" "$BUILD_DIR/utils"
cp -r "$ECAN_ROOT/config" "$BUILD_DIR/config"
cp -r "$ECAN_ROOT/my_prompts" "$BUILD_DIR/my_prompts" 2>/dev/null || true
cp -r "$ECAN_ROOT/lambda_functions/skill_editor_lambda/prompts" "$BUILD_DIR/prompts" 2>/dev/null || true

# Copy mapping DSL doc into prompts/ so prompt_store can load it at runtime
MAPPING_DSL_SRC="$ECAN_ROOT/gui_v2/src/modules/skill-editor/doc/mapping-dsl.md"
if [ ! -f "$MAPPING_DSL_SRC" ]; then
    # Fallback to docs/ copy if gui_v2 canonical version is missing
    MAPPING_DSL_SRC="$ECAN_ROOT/docs/mapping-dsl.md"
fi
if [ -f "$MAPPING_DSL_SRC" ]; then
    cp "$MAPPING_DSL_SRC" "$BUILD_DIR/prompts/mapping-dsl.md"
    echo "  - Copied mapping-dsl.md into prompts/"
else
    echo "  WARNING: mapping-dsl.md not found at $MAPPING_DSL_SRC"
fi

cp "$ECAN_ROOT/app_context.py" "$BUILD_DIR/" 2>/dev/null || true

# Remove heavy assets not needed in Lambda (OCR models, etc.)
rm -rf "$BUILD_DIR/agent/mcp/server/local_ocr" 2>/dev/null || true

# Apply Lambda overrides (CRITICAL - these replace files that have Lambda-incompatible code)
echo "[4/5] Applying Lambda overrides..."
OVERRIDES_DIR="$ECAN_ROOT/lambda_functions/skill_editor_lambda/lambda_overrides"
if [ -d "$OVERRIDES_DIR" ]; then
    # Override ec_tasks/__init__.py (avoids importing scheduler which imports logger_helper which imports app_info)
    cp "$OVERRIDES_DIR/agent/ec_tasks/__init__.py" "$BUILD_DIR/agent/ec_tasks/__init__.py"
    echo "  - Overrode agent/ec_tasks/__init__.py (minimal version)"
    
    # Override utils/__init__.py
    cp "$OVERRIDES_DIR/utils/__init__.py" "$BUILD_DIR/utils/__init__.py"
    echo "  - Overrode utils/__init__.py (minimal version)"
    
    # Override utils/logger_helper.py (avoids importing config.app_info which creates directories)
    cp "$OVERRIDES_DIR/utils/logger_helper.py" "$BUILD_DIR/utils/logger_helper.py"
    echo "  - Overrode utils/logger_helper.py (minimal version)"
else
    echo "  WARNING: lambda_overrides directory not found at $OVERRIDES_DIR"
fi

# Remove __pycache__ directories
find "$BUILD_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Create zip
echo "[5/5] Creating deployment package..."
cd "$BUILD_DIR"
zip -r "$ZIP_FILE" . -x "*.pyc" -x "*__pycache__*"

ZIP_SIZE=$(du -h "$ZIP_FILE" | cut -f1)
echo ""
echo "Package created: $ZIP_FILE ($ZIP_SIZE)"
echo ""
echo "To deploy:"
echo "  aws lambda update-function-code --function-name skill_editor_agent --region us-east-1 --zip-file fileb://$ZIP_FILE"
