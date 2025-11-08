# Sparkle Setup Guide

Sparkle is a macOS framework that provides automatic update functionality for macOS applications. It is **not** a Python package and cannot be installed via pip.

## Installation Options

### Option 1: Using Homebrew (Recommended)

```bash
brew install sparkle
```

This will install Sparkle to `/opt/homebrew/Frameworks/Sparkle.framework` (Apple Silicon) or `/usr/local/Frameworks/Sparkle.framework` (Intel).

### Option 2: Download Pre-built Framework

1. Download the latest Sparkle release from: https://github.com/sparkle-project/Sparkle/releases
2. Extract the archive
3. Copy `Sparkle.framework` to one of these locations:
   - `/Applications/ECBot.app/Contents/Frameworks/Sparkle.framework`
   - `/Library/Frameworks/Sparkle.framework`
   - `~/Library/Frameworks/Sparkle.framework`

### Option 3: Build from Source

1. Clone the repository:
   ```bash
   git clone https://github.com/sparkle-project/Sparkle.git
   ```

2. Build using Xcode:
   ```bash
   cd Sparkle
   xcodebuild -project Sparkle.xcodeproj -configuration Release
   ```

3. Copy the built framework to your application bundle

## Integration with ECBot

### Framework Placement

The OTA system will automatically search for Sparkle.framework in these locations:
- `/Applications/ECBot.app/Contents/Frameworks/Sparkle.framework`
- `{app_home_path}/Frameworks/Sparkle.framework`
- `/Library/Frameworks/Sparkle.framework`

### CLI Tool (Optional)

If you need a command-line interface for Sparkle:

1. The framework includes a CLI tool at:
   `Sparkle.framework/Versions/Current/Resources/sparkle-cli`

2. Ensure it's executable:
   ```bash
   chmod +x Sparkle.framework/Versions/Current/Resources/sparkle-cli
   ```

## Python Integration

The OTA system will automatically detect Sparkle if it's properly installed:

```python
from ota import OTAUpdater

# The updater will automatically use Sparkle on macOS
updater = OTAUpdater()
has_update = updater.check_for_updates()
```

## App Bundle Configuration

### Info.plist Configuration

Add these keys to your app's `Info.plist`:

```xml
<key>SUFeedURL</key>
<string>https://scszcoder.github.io/ecbot/appcast-macos.xml</string>
<key>SUPublicEDKey</key>
<!-- Base64 of 32-byte raw Ed25519 public key. You can get it via:
     python scripts/verify_ed25519_signature.py --public-key ed25519-public.pem --print-sparkle-key -->
<string>paste-your-SUPublicEDKey-here</string>
<key>SUEnableAutomaticChecks</key>
<true/>
```

### Appcast XML

Create an appcast XML file for your updates:

```xml
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
    <channel>
        <title>ECBot Updates</title>
        <description>Updates for ECBot</description>
        <language>en</language>
        <item>
            <title>ECBot 1.1.0</title>
            <description>New features and bug fixes</description>
            <pubDate>Mon, 01 Jan 2024 12:00:00 +0000</pubDate>
            <enclosure url="https://updates.ecbot.com/downloads/ECBot-1.1.0.dmg"
                       sparkle:version="1.1.0"
                       sparkle:os="macos"
                       length="52428800"
                       type="application/octet-stream"
                       sparkle:edSignature="ABC123..." />
        </item>
    </channel>
</rss>
```

## Code Signing

### Generate Ed25519 Keys

```bash
# Generate private key
openssl genpkey -algorithm Ed25519 -out private_key.pem

# Extract public key
openssl pkey -in private_key.pem -pubout -out public_key.pem
```

### Sign Updates

```bash
# Sign your update package
./sign_update.py your_update.dmg private_key.pem
```

## Troubleshooting

### Common Issues

1. **Framework not found**: Ensure Sparkle.framework is in one of the expected locations
2. **CLI tool not found**: The OTA system will fall back to generic HTTP updates if CLI tools are not available
3. **Permission errors**: Ensure the framework and CLI tool have proper permissions
4. **Code signing issues**: Verify your Ed25519 keys are properly configured

### Verification

To verify Sparkle is properly installed:

```python
import os
from ota.core.platforms import SparkleUpdater
from ota.core.updater import OTAUpdater

updater = OTAUpdater()
if hasattr(updater.platform_updater, '_find_sparkle_framework'):
    framework_path = updater.platform_updater._find_sparkle_framework()
    if framework_path:
        print(f"Sparkle found at: {framework_path}")
    else:
        print("Sparkle framework not found")
```

### Debug Mode

Enable debug logging to troubleshoot issues:

```python
import os
os.environ['ECBOT_DEV_MODE'] = 'true'

from ota import OTAUpdater
updater = OTAUpdater()
```

## Alternative: Generic HTTP Updates

If Sparkle is not available, the OTA system will automatically fall back to generic HTTP-based updates, which work on all platforms but may have fewer features.

## References

- [Sparkle Official Website](https://sparkle-project.org/)
- [Sparkle GitHub Repository](https://github.com/sparkle-project/Sparkle)
- [Sparkle Documentation](https://sparkle-project.org/documentation/)
- [App Store Distribution](https://sparkle-project.org/documentation/app-store/)
