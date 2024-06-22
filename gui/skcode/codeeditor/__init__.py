# -*- coding:utf-8 -*-
# @Time: 2021/1/30 18:11
# @Author: Zhanyi Hou
# @Email: 1295752786@qq.com
# @File: __init__.py.py
from utils.time_util import TimeUtil

print(TimeUtil.formatted_now_with_ms() + " Initializing package gui.skcode.codeeditor...")

from gui.skcode.codeeditor.baseeditor import PMGBaseEditor
from gui.skcode.codeeditor.pythoneditor import PMGPythonEditor