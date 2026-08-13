# eCan.cn Branding Assets

## Overview

CN version uses the same base icons as the international version, with the following references:

## Icon Assets

### Windows (.ico)
- **Location**: `icon.ico` (symlink to `../../../resource/images/logos/icon_multi.ico`)
- **Source**: `resource/images/logos/icon_multi.ico`
- **Format**: ICO with multiple sizes (16x16, 32x32, 48x48, 256x256)
- **Status**: ✅ Ready (symlink created)

### macOS (.icns)
- **Source**: `resource/icon.icns`
- **Generation**: Generate from source PNG using iconutil
- **Note**: .icns file is generated during the build process from the ICO file

### Linux (PNG)
- **Source**: `resource/images/logos/desktop_256x256.png`
- **Used for**: AppImage

## Installer Images

### Windows Installer
- **Source**: `resource/images/logos/installer_800x600.png`
- **Dimensions**: 800x600 pixels
- **Used in**: Inno Setup installer

## Build Notes

The icons are shared between CN and international versions. No separate icon assets are needed for the CN version.

If you need to customize CN-specific icons:
1. Create custom icons in this directory
2. Update `icon_config.json` to reference the custom icons
3. Update `plist_overrides.json` if using custom .icns file
