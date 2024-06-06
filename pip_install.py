# https://www.cnblogs.com/xingyaowuhen/p/17065140.html
"""

一、requirements.txt的生成方式

(1)第一种方法是，在终端窗口输入

pip freeze > requirements.txt
requirements.txt文件会自动生成到项目所在文件夹中。

注意：这个会把环境中的所有库都保存下来，配合virtualenv才好用。如果没有virtualenv，这个方法会保存很多多余的库。

(2)第二种方法是pipreqs，这种方法会自动检测项目中调用的库，然后写进requirements.txt

首先，安装pipreqs

pip install pipreqs
然后，在终端输入以下命令

pipreqs ./
（问题1）当项目所在文件夹中已有requirement.txt时，会提示

WARNING: requirements.txt already exists, use --force to overwrite it
这时需要将输入代码改为以下，即可更新已经存在的requirement.txt文件了。

pipreqs --force ./
（问题2）有可能会出现如下所示的报错，如下图

解决办法：输入

pipreqs ./ --encoding=utf-8
即可成功

二、requirement.txt的使用方式

首先将requirements.txt复制到项目所在文件夹里面，然后在新建的项目的终端里，输入

pip install -r requirements.txt
所需要的库就会自动安装成功
三、更新requirements.txt 中的包

安装：

pip install pip-upgrader

使用方法

激活你的virtualenv（很重要，因为它也将在当前virtualenv中安装新版本的升级包）。

pip-upgrade
"""

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