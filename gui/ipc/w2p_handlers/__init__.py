import pkgutil
import importlib

# 动态导入当前包下的所有模块，以确保所有处理器都被注册
for loader, name, is_pkg in pkgutil.walk_packages(__path__):
    importlib.import_module('.' + name, __name__)

# 确保关键处理器被显式导入（某些打包/运行环境下 walk_packages 可能遗漏新文件）
try:
    from . import node_state_schema_handler  # noqa: F401
    from . import agent_handler  # noqa: F401 - 确保 agent_handler 被导入
except Exception:
    pass
