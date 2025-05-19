import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).parent.parent
sys.path.append(str(ROOT_DIR))

from scripts.dev import main

if __name__ == '__main__':
    sys.exit(main()) 