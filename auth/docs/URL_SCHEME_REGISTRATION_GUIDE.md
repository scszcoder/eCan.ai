# eCan Application URL Scheme Registration Guide

This guide explains how to register the `ecan://` URL scheme for the eCan application to enable OAuth callback redirection from the browser to the application.

## Overview

The OAuth authentication flow uses `ecan://auth/success` to redirect users back to the application after successful Google authentication. The application must register this custom URL scheme with the operating system.

## macOS Implementation

### 1. Info.plist Configuration

Add the following to your application's `Info.plist` file:

```xml
<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleURLName</key>
        <string>com.ecan.oauth</string>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>ecan</string>
        </array>
        <key>CFBundleURLIconFile</key>
        <string>eCan.icns</string>
    </dict>
</array>
```

### 2. Application Delegate Implementation

For Qt applications, handle the URL scheme in your main application:

```python
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QUrl

class ECanApplication(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.setOrganizationName("eCan")
        self.setApplicationName("eCan")
        
    def event(self, event):
        if event.type() == QEvent.FileOpen:
            url = event.url()
            if url.scheme() == "ecan":
                self.handle_url_scheme(url)
                return True
        return super().event(event)
    
    def handle_url_scheme(self, url: QUrl):
        """Handle ecan:// URL scheme calls"""
        if url.host() == "auth" and url.path() == "/success":
            # OAuth authentication successful
            self.handle_oauth_success()
        
    def handle_oauth_success(self):
        """Handle successful OAuth authentication"""
        # Bring application to foreground
        # Update UI to reflect authentication status
        # Refresh user session
        pass
```

### 3. Build Configuration

Ensure your build system includes the Info.plist with URL scheme registration:

```python
# In your build script or setup.py
app_info_plist = {
    'CFBundleURLTypes': [
        {
            'CFBundleURLName': 'com.ecan.oauth',
            'CFBundleURLSchemes': ['ecan'],
            'CFBundleURLIconFile': 'eCan.icns'
        }
    ]
}
```

## Windows Implementation

### 1. Registry Registration

Create a registry entry for the URL scheme:

```python
import winreg

def register_url_scheme():
    """Register ecan:// URL scheme in Windows registry"""
    try:
        # Create the protocol key
        key = winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, "ecan")
        winreg.SetValue(key, "", winreg.REG_SZ, "URL:eCan Protocol")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
        
        # Set the default icon
        icon_key = winreg.CreateKey(key, "DefaultIcon")
        winreg.SetValue(icon_key, "", winreg.REG_SZ, f"{app_path}\\eCan.ico,0")
        
        # Set the command to execute
        command_key = winreg.CreateKey(key, "shell\\open\\command")
        winreg.SetValue(command_key, "", winreg.REG_SZ, f'"{app_path}\\eCan.exe" "%1"')
        
        winreg.CloseKey(command_key)
        winreg.CloseKey(icon_key)
        winreg.CloseKey(key)
        
        print("URL scheme registered successfully")
        return True
        
    except Exception as e:
        print(f"Failed to register URL scheme: {e}")
        return False
```

### 2. Command Line Argument Handling

Handle URL scheme calls via command line arguments:

```python
import sys
from urllib.parse import urlparse

class ECanApplication:
    def __init__(self):
        self.check_url_scheme_launch()
    
    def check_url_scheme_launch(self):
        """Check if application was launched via URL scheme"""
        if len(sys.argv) > 1:
            url_arg = sys.argv[1]
            if url_arg.startswith("ecan://"):
                self.handle_url_scheme(url_arg)
    
    def handle_url_scheme(self, url_string: str):
        """Handle ecan:// URL scheme calls"""
        parsed_url = urlparse(url_string)
        
        if parsed_url.scheme == "ecan":
            if parsed_url.netloc == "auth" and parsed_url.path == "/success":
                self.handle_oauth_success()
    
    def handle_oauth_success(self):
        """Handle successful OAuth authentication"""
        # Bring application window to foreground
        # Update authentication status
        # Refresh user session
        pass
```

## Linux Implementation

### 1. Desktop Entry File

Create a `.desktop` file for URL scheme handling:

```ini
[Desktop Entry]
Name=eCan
Exec=/path/to/ecan %u
Icon=/path/to/ecan.png
Type=Application
MimeType=x-scheme-handler/ecan
```

### 2. Register the Handler

```bash
# Install the desktop file
cp ecan.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications/

# Register the URL scheme handler
xdg-mime default ecan.desktop x-scheme-handler/ecan
```

## Application Integration

### 1. URL Scheme Handler

Implement a centralized URL scheme handler:

```python
from urllib.parse import urlparse, parse_qs
from utils.logger_helper import logger_helper as logger

class URLSchemeHandler:
    """Handle ecan:// URL scheme calls"""
    
    def __init__(self, app_instance):
        self.app = app_instance
    
    def handle_scheme_url(self, url_string: str):
        """Process incoming URL scheme calls"""
        try:
            parsed_url = urlparse(url_string)
            
            if parsed_url.scheme != "ecan":
                logger.warning(f"Unsupported URL scheme: {parsed_url.scheme}")
                return False
            
            # Route based on host
            if parsed_url.netloc == "auth":
                return self._handle_auth_callback(parsed_url)
            else:
                logger.warning(f"Unknown URL host: {parsed_url.netloc}")
                return False
                
        except Exception as e:
            logger.error(f"Error handling URL scheme: {e}")
            return False
    
    def _handle_auth_callback(self, parsed_url):
        """Handle authentication callbacks"""
        if parsed_url.path == "/success":
            logger.info("OAuth authentication success callback received")
            self.app.handle_oauth_success()
            return True
        elif parsed_url.path == "/error":
            query_params = parse_qs(parsed_url.query)
            error = query_params.get('error', ['Unknown error'])[0]
            logger.error(f"OAuth authentication error: {error}")
            self.app.handle_oauth_error(error)
            return True
        else:
            logger.warning(f"Unknown auth callback path: {parsed_url.path}")
            return False
```

### 2. Main Application Integration

Integrate the URL scheme handler into your main application:

```python
class MainGUI:
    def __init__(self):
        self.url_scheme_handler = URLSchemeHandler(self)
        self.setup_url_scheme_handling()
    
    def setup_url_scheme_handling(self):
        """Setup URL scheme handling for the application"""
        # Register URL scheme on application startup
        if sys.platform == "win32":
            self.register_windows_url_scheme()
        
        # Check for URL scheme launch
        self.check_startup_url_scheme()
    
    def check_startup_url_scheme(self):
        """Check if app was launched via URL scheme"""
        if len(sys.argv) > 1 and sys.argv[1].startswith("ecan://"):
            self.url_scheme_handler.handle_scheme_url(sys.argv[1])
    
    def handle_oauth_success(self):
        """Handle successful OAuth authentication"""
        # Bring window to foreground
        self.activateWindow()
        self.raise_()
        
        # Update UI to reflect authentication status
        self.update_auth_status()
        
        # Show success notification
        self.show_notification("Authentication successful!")
    
    def handle_oauth_error(self, error: str):
        """Handle OAuth authentication error"""
        logger.error(f"OAuth error: {error}")
        self.show_error_dialog(f"Authentication failed: {error}")
```

## Testing

### Test URL Scheme Registration

1. **macOS**: Open Terminal and run:
   ```bash
   open "ecan://auth/success"
   ```

2. **Windows**: Open Command Prompt and run:
   ```cmd
   start ecan://auth/success
   ```

3. **Linux**: Open Terminal and run:
   ```bash
   xdg-open "ecan://auth/success"
   ```

The application should launch and handle the URL scheme appropriately.

## Security Considerations

1. **Validate URLs**: Always validate incoming URL scheme calls
2. **Sanitize Parameters**: Clean any query parameters before processing
3. **Rate Limiting**: Implement rate limiting for URL scheme calls
4. **Logging**: Log all URL scheme activities for debugging

## Troubleshooting

### Common Issues

1. **Scheme Not Registered**: Ensure the URL scheme is properly registered with the OS
2. **Application Not Launching**: Check file permissions and executable paths
3. **Multiple Instances**: Handle cases where multiple app instances might be launched
4. **Browser Compatibility**: Test with different browsers (Chrome, Firefox, Safari, Edge)

### Debug Mode

Enable debug logging for URL scheme handling:

```python
import logging

# Enable debug logging for URL scheme
logging.getLogger('url_scheme').setLevel(logging.DEBUG)
```

## Summary

After implementing URL scheme registration:

1. The application will respond to `ecan://auth/success` calls
2. OAuth authentication will seamlessly redirect back to the app
3. Users will have a smooth authentication experience
4. The application can handle authentication state changes appropriately

Make sure to test the URL scheme registration on all target platforms before deployment.
