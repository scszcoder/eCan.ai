"""
ECBot OTA更新对话框模块
提供标准的更新对话框组件
"""

# 导入标准更新对话框
from .update_dialog import UpdateDialog, UpdateNotificationDialog

# 导入增强对话框
try:
    from .enhanced_dialog import EnhancedUpdateDialog
    # 默认使用增强对话框
    UpdateDialog = EnhancedUpdateDialog
except ImportError:
    # 如果导入失败，使用标准对话框作为后备
    pass