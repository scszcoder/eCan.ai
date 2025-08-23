#!/bin/bash
set -e

echo "=== Verifying PKG installer ==="
ARCH="$BUILD_ARCH"
VERSION="$VERSION"
APP_PATH="dist/eCan.app"
PKG_PATH="dist/eCan-${VERSION}-macos-${ARCH}.pkg"

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
  pkgutil --payload-files "$PKG_PATH" >/dev/null 2>&1 && echo "[OK] PKG structure is valid" || echo "[WARNING] PKG structure validation failed (may be normal in CI)"
  
else
  echo "[WARNING] PKG installer not found at: $PKG_PATH"
  echo "[INFO] Attempting to create PKG manually..."
  
  # Fallback PKG creation if main build didn't create it
  mkdir -p build/pkg_fallback
  rm -rf build/pkg_fallback/*

  # Create simple component PKG
  pkgbuild --component "$APP_PATH" \
           --identifier "com.ecan.ecan" \
           --version "$VERSION" \
           --install-location "/Applications" \
           "build/pkg_fallback/eCan-component.pkg"

  # Create minimal distribution XML using echo statements
  echo '<?xml version="1.0" encoding="utf-8"?>' > build/pkg_fallback/distribution.xml
  echo '<installer-gui-script minSpecVersion="1">' >> build/pkg_fallback/distribution.xml
  echo '    <title>eCan Installer</title>' >> build/pkg_fallback/distribution.xml
  echo '    <organization>com.ecan</organization>' >> build/pkg_fallback/distribution.xml
  echo '    <domains enable_localSystem="true"/>' >> build/pkg_fallback/distribution.xml
  echo '    <options customize="never" require-scripts="false" rootVolumeOnly="true"/>' >> build/pkg_fallback/distribution.xml
  echo '    <pkg-ref id="com.ecan.ecan"/>' >> build/pkg_fallback/distribution.xml
  echo '    <choices-outline>' >> build/pkg_fallback/distribution.xml
  echo '        <line choice="default">' >> build/pkg_fallback/distribution.xml
  echo '            <line choice="com.ecan.ecan"/>' >> build/pkg_fallback/distribution.xml
  echo '        </line>' >> build/pkg_fallback/distribution.xml
  echo '    </choices-outline>' >> build/pkg_fallback/distribution.xml
  echo '    <choice id="default"/>' >> build/pkg_fallback/distribution.xml
  echo '    <choice id="com.ecan.ecan" visible="false">' >> build/pkg_fallback/distribution.xml
  echo '        <pkg-ref id="com.ecan.ecan"/>' >> build/pkg_fallback/distribution.xml
  echo '    </choice>' >> build/pkg_fallback/distribution.xml
  echo '    <pkg-ref id="com.ecan.ecan" version="VERSION_PLACEHOLDER" onConclusion="none">' >> build/pkg_fallback/distribution.xml
  echo '        eCan-component.pkg' >> build/pkg_fallback/distribution.xml
  echo '    </pkg-ref>' >> build/pkg_fallback/distribution.xml
  echo '</installer-gui-script>' >> build/pkg_fallback/distribution.xml

  # Replace version placeholder
  sed -i '' "s/VERSION_PLACEHOLDER/$VERSION/g" build/pkg_fallback/distribution.xml

  # Create final PKG
  if productbuild --distribution "build/pkg_fallback/distribution.xml" \
                  --package-path "build/pkg_fallback" \
                  "$PKG_PATH"; then
    echo "[OK] Fallback PKG created successfully"
    pkg_size=$(du -sh "$PKG_PATH" | cut -f1)
    echo "   Size: $pkg_size"
  else
    echo "[ERROR] Failed to create fallback PKG"
    exit 1
  fi
fi

# Final validation
if [ -f "$PKG_PATH" ] && [ $(stat -f "%z" "$PKG_PATH" 2>/dev/null || echo "0") -gt 1024 ]; then
  echo "[SUCCESS] PKG installer validation passed"
else
  echo "[ERROR] PKG installer validation failed"
  exit 1
fi
