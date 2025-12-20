"""
eCan.ai OTA Update Dialog Module
Provides standard update dialog components
"""

# Import standard update dialog
from .update_dialog import UpdateDialog, UpdateNotificationDialog

# Import enhanced dialog
try:
    from .enhanced_dialog import EnhancedUpdateDialog
    # Use enhanced dialog by default
    UpdateDialog = EnhancedUpdateDialog
except ImportError:
    # If import fails, use standard dialog as fallback
    pass