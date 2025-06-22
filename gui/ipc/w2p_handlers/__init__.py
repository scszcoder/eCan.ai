import pkgutil
import importlib

# 动态导入当前包下的所有模块，以确保所有处理器都被注册
for loader, name, is_pkg in pkgutil.walk_packages(__path__):
    importlib.import_module('.' + name, __name__)
