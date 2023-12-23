import platform
import subprocess

# 获取当前操作系统
current_os = platform.system()

# 根据操作系统安装对应的依赖项
if current_os == "Darwin":  # macOS
    subprocess.run(["pip", "install", "-r", "requirements_macos.txt"])
elif current_os == "Windows":
    subprocess.run(["pip", "install", "-r", "requirements_windows.txt"])
else:
    print("Unsupported operating system")