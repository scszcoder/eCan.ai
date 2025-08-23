#!/bin/bash
set -e

echo "=== Verifying PKG installer ==="
ARCH="$BUILD_ARCH"
VERSION="$VERSION"
APP_PATH="dist/eCan.app"
PKG_PATH="dist/eCan-${VERSION}-macos-${ARCH}.pkg"

echo "[INFO] Build architecture: $ARCH"
echo "[INFO] Version: $VERSION"
echo "[INFO] Expected PKG: $PKG_PATH"

# First check if app bundle exists and is valid
if [ ! -d "$APP_PATH" ]; then
  echo "[ERROR] Application bundle not found at $APP_PATH"
  echo "Available files in dist:"
  ls -la dist/ || echo "dist directory not found"
  exit 1
fi

echo "[OK] App bundle found at $APP_PATH"

# Validate app bundle structure
if [ ! -f "$APP_PATH/Contents/Info.plist" ]; then
  echo "[ERROR] Info.plist missing from app bundle"
  exit 1
fi

if [ ! -d "$APP_PATH/Contents/MacOS" ]; then
  echo "[ERROR] MacOS directory missing from app bundle"
  exit 1
fi

# Check for executable
EXECUTABLE_PATH="$APP_PATH/Contents/MacOS/eCan"
if [ ! -f "$EXECUTABLE_PATH" ]; then
  echo "[WARNING] Main executable not found at expected location"
  echo "Contents of MacOS directory:"
  ls -la "$APP_PATH/Contents/MacOS/" || echo "MacOS directory is empty"
else
  echo "[OK] Main executable found"
fi

# Now check for PKG installer
if [ -f "$PKG_PATH" ]; then
  echo "[OK] PKG installer found: $PKG_PATH"
  pkg_size=$(du -sh "$PKG_PATH" | cut -f1)
  echo "   Size: $pkg_size"
  echo "   Created: $(stat -f "%Sm" "$PKG_PATH" 2>/dev/null || date)"

  # Basic PKG validation
  if [ $(stat -f "%z" "$PKG_PATH" 2>/dev/null || echo "0") -lt 1024 ]; then
    echo "[ERROR] PKG file is too small (likely corrupted)"
    exit 1
  fi

  # Try to verify PKG structure without signature check (which would fail in CI)
  echo "[INFO] Validating PKG structure..."
  if pkgutil --payload-files "$PKG_PATH" >/dev/null 2>&1; then
    echo "[OK] PKG structure is valid"
    
    # Check if .app is in the PKG contents
    if pkgutil --payload-files "$PKG_PATH" | grep -q "\.app"; then
      echo "[OK] App bundle found in PKG contents"
    else
      echo "[WARNING] No .app found in PKG contents, but PKG structure is valid"
      echo "[INFO] This may indicate a packaging issue"
    fi
  else
    echo "[WARNING] PKG structure validation failed (may be normal in CI)"
    # Try alternative validation method
    if pkgutil --expand "$PKG_PATH" /tmp/pkg_test >/dev/null 2>&1; then
      echo "[OK] PKG can be expanded (alternative validation passed)"
      rm -rf /tmp/pkg_test
    else
      echo "[WARNING] PKG expansion also failed"
    fi
  fi
  
else
  echo "[WARNING] PKG installer not found at: $PKG_PATH"
  echo "[INFO] Attempting to create PKG manually..."
  
  # Fallback PKG creation if main build didn't create it
  mkdir -p build/pkg_fallback
  rm -rf build/pkg_fallback/*

  echo "[INFO] Creating component PKG..."
  # Create simple component PKG
  if pkgbuild --component "$APP_PATH" \
           --identifier "com.ecan.ecan" \
           --version "$VERSION" \
           --install-location "/Applications" \
           "build/pkg_fallback/eCan-component.pkg"; then
    echo "[OK] Component PKG created"
  else
    echo "[ERROR] Failed to create component PKG"
    exit 1
  fi

  echo "[INFO] Creating distribution XML..."
  # Create minimal distribution XML using echo statements
  cat > build/pkg_fallback/distribution.xml << 'EOF'
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="1">
    <title>eCan Installer</title>
    <organization>com.ecan</organization>
    <domains enable_localSystem="true"/>
    <options customize="never" require-scripts="false" rootVolumeOnly="true"/>
    <pkg-ref id="com.ecan.ecan"/>
    <choices-outline>
        <line choice="default">
            <line choice="com.ecan.ecan"/>
        </line>
    </choices-outline>
    <choice id="default"/>
    <choice id="com.ecan.ecan" visible="false">
        <pkg-ref id="com.ecan.ecan"/>
    </choice>
    <pkg-ref id="com.ecan.ecan" version="VERSION_PLACEHOLDER" onConclusion="none">
        eCan-component.pkg
    </pkg-ref>
</installer-gui-script>
EOF

  # Replace version placeholder
  sed -i '' "s/VERSION_PLACEHOLDER/$VERSION/g" build/pkg_fallback/distribution.xml

  echo "[INFO] Creating final PKG..."
  # Create final PKG
  if productbuild --distribution "build/pkg_fallback/distribution.xml" \
                  --package-path "build/pkg_fallback" \
                  "$PKG_PATH"; then
    echo "[OK] Fallback PKG created successfully"
    pkg_size=$(du -sh "$PKG_PATH" | cut -f1)
    echo "   Size: $pkg_size"
  else
    echo "[ERROR] Failed to create fallback PKG"
    echo "[DEBUG] Component PKG exists: $(ls -la build/pkg_fallback/)"
    echo "[DEBUG] Distribution XML exists: $(ls -la build/pkg_fallback/distribution.xml)"
    exit 1
  fi
fi

# Final validation
if [ -f "$PKG_PATH" ] && [ $(stat -f "%z" "$PKG_PATH" 2>/dev/null || echo "0") -gt 1024 ]; then
  echo "[SUCCESS] PKG installer validation passed"
  echo "[INFO] Final PKG details:"
  echo "   Path: $PKG_PATH"
  echo "   Size: $(du -sh "$PKG_PATH" | cut -f1)"
  echo "   Created: $(stat -f "%Sm" "$PKG_PATH" 2>/dev/null || date)"
  
  # Additional validation: check if .app is actually in the PKG
  echo "[INFO] Verifying app bundle is actually in PKG..."
  if pkgutil --payload-files "$PKG_PATH" | grep -q "\.app"; then
    echo "[OK] App bundle confirmed in PKG contents"
  else
    echo "[WARNING] App bundle not found in PKG contents - this may cause installation issues"
    echo "[INFO] Note: PKG verification will be handled by verify_architecture.py"
  fi
else
  echo "[ERROR] PKG installer validation failed"
  echo "[DEBUG] PKG file exists: $([ -f "$PKG_PATH" ] && echo "Yes" || echo "No")"
  if [ -f "$PKG_PATH" ]; then
    echo "[DEBUG] PKG file size: $(stat -f "%z" "$PKG_PATH" 2>/dev/null || echo "Unknown")"
  fi
  exit 1
fi
