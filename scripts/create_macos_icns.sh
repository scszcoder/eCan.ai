#!/bin/bash
# Create macOS .icns file from high-resolution PNG
# This ensures the Dock icon is crisp and properly formatted

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "🎨 Creating macOS .icns file from PNG sources..."

# Source PNG file (512x512 or higher)
SOURCE_PNG="$PROJECT_ROOT/resource/images/logos/rounded/dock_512x512.png"

if [ ! -f "$SOURCE_PNG" ]; then
    echo "❌ Error: Source PNG not found: $SOURCE_PNG"
    exit 1
fi

echo "📁 Source: $SOURCE_PNG"

# Create iconset directory
ICONSET_DIR="$PROJECT_ROOT/eCan.iconset"
rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"

echo "🔧 Generating icon sizes..."

# Generate all required icon sizes for macOS
# Standard resolutions
sips -z 16 16     "$SOURCE_PNG" --out "$ICONSET_DIR/icon_16x16.png" > /dev/null 2>&1
sips -z 32 32     "$SOURCE_PNG" --out "$ICONSET_DIR/icon_16x16@2x.png" > /dev/null 2>&1
sips -z 32 32     "$SOURCE_PNG" --out "$ICONSET_DIR/icon_32x32.png" > /dev/null 2>&1
sips -z 64 64     "$SOURCE_PNG" --out "$ICONSET_DIR/icon_32x32@2x.png" > /dev/null 2>&1
sips -z 128 128   "$SOURCE_PNG" --out "$ICONSET_DIR/icon_128x128.png" > /dev/null 2>&1
sips -z 256 256   "$SOURCE_PNG" --out "$ICONSET_DIR/icon_128x128@2x.png" > /dev/null 2>&1
sips -z 256 256   "$SOURCE_PNG" --out "$ICONSET_DIR/icon_256x256.png" > /dev/null 2>&1
sips -z 512 512   "$SOURCE_PNG" --out "$ICONSET_DIR/icon_256x256@2x.png" > /dev/null 2>&1
sips -z 512 512   "$SOURCE_PNG" --out "$ICONSET_DIR/icon_512x512.png" > /dev/null 2>&1

# Copy the 512x512 source as 512x512@2x (1024x1024 would be ideal, but 512 is acceptable)
cp "$SOURCE_PNG" "$ICONSET_DIR/icon_512x512@2x.png"

echo "✅ All icon sizes generated"

# Convert iconset to icns
OUTPUT_ICNS="$PROJECT_ROOT/eCan.icns"
echo "🎨 Creating .icns bundle..."
iconutil -c icns "$ICONSET_DIR" -o "$OUTPUT_ICNS"

# Clean up iconset directory
rm -rf "$ICONSET_DIR"

# Verify the created file
if [ -f "$OUTPUT_ICNS" ]; then
    FILE_SIZE=$(ls -lh "$OUTPUT_ICNS" | awk '{print $5}')
    echo "✅ Success! Created: $OUTPUT_ICNS ($FILE_SIZE)"
    echo "📊 File info:"
    file "$OUTPUT_ICNS"
else
    echo "❌ Error: Failed to create .icns file"
    exit 1
fi

echo ""
echo "🎉 Done! The .icns file is ready for use."
echo "   This will be used when packaging the macOS .app bundle."

