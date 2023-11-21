from PyInstaller.__main__ import run
import os

# The path separator is platform specific,os.pathsep (which is ; on Windows and : on most unix systems) is used.
if os.name == 'nt':  # Windows
    pathsep = ";"
else:  # macOS
    pathsep = ":"

# 打包选项
options = [
    '--name=ecbot',  # 替换为你的应用程序名称
    #'--windowed',
    #'--clean',
    '--log-level=DEBUG',
    '--onefile',
    '--icon=ECBot.ico',
    # '--add-data=resource:resource'
    pathsep.join(['--add-data=resource/images', 'resource/images']),
    pathsep.join(['--add-data=resource/languages', 'resource/languages']),
    pathsep.join(['--add-data=resource/translation', 'resource/translation']),
    pathsep.join(['--add-data=resource/skills', 'resource/skills']),
    pathsep.join(['--add-data=resource/settings', 'resource/settings']),
    pathsep.join(['--add-data=resource/testdata', 'resource/testdata'])
    # 添加其他需要的资源文件，例如 '--add-data=/path/to/resource_file.txt:.'
]

print(options)
# 运行 PyInstaller 打包
run(options + ['main.py'])