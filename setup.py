import subprocess
import tempfile

from PyInstaller.__main__ import run
import os
import shutil
import fnmatch
from pathlib import Path


def build_app():
    # The path separator is platform specific,os.pathsep (which is ; on Windows and : on most unix systems) is used.
    if os.name == 'nt':  # Windows
        pathsep = ";"
    else:  # macOS
        pathsep = ":"

    # 打包选项
    options = [
        '--name=ecbot',  # 替换为你的应用程序名称
        '--windowed',
        '--clean',
        # '--noconsole',
        '--log-level=DEBUG',
        '--onefile',
        # --debug = imports, # 分析工具查看哪些模块被打包
        # --strip, # 选项去除可执行文件中的符号表和调试信息，减小文件大小
        '--icon=ECBot.ico',
        # '--add-data=resource:resource'
        pathsep.join(['--add-data=ecbot-ui/dist', 'resource/ui']),
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

    if os.name == 'nt':  # Windows
        pass
    else:
        # 执行shell脚本，构建dmg文件
        result = subprocess.run(['sh', 'build_dmg.sh'], capture_output=True, text=True)


def remove_directory(path):
    if os.path.exists(path):
        shutil.rmtree(path)
        print(f"Removed directory: {path}")
    else:
        print(f"Directory not found: {path}")


def remove_file(path):
    if os.path.exists(path):
        os.remove(path)
        print(f"Removed file: {path}")
    else:
        print(f"File not found: {path}")


def find_and_remove_cache():
    if os.name == 'nt':  # Windows
        temp_dir = Path(tempfile.gettempdir())
    else:  # macOS
        temp_dir = Path('/var/folders')

    print(temp_dir)

    for root, dirs, files in os.walk(temp_dir):
        for dir_name in dirs:
            if fnmatch.fnmatch(dir_name, '*pyinstaller*'):
                cache_path = Path(root) / dir_name
                shutil.rmtree(cache_path)
                print(f"Removed PyInstaller cache: {cache_path}")


def main():
    project_path = Path('./')

    # Remove build and dist directories
    remove_directory(project_path / 'build')
    remove_directory(project_path / 'dist')

    # Remove .spec files
    for spec_file in project_path.glob('*.spec'):
        remove_file(spec_file)

    # Find and remove PyInstaller cache
    find_and_remove_cache()

    build_app()


if __name__ == "__main__":
    main()
