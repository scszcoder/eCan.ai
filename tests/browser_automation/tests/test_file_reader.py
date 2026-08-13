"""文件/文件夹读取测试

这个测试验证：
1. 输入类型检测器能正确识别 FILE/FOLDER 类型
2. 文件路径能被正确解析
3. 模拟的 browser-automation 节点能处理文件输入

运行方式：
    python -m pytest tests/browser_automation/tests/test_file_reader.py -v
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any

import pytest

# 设置环境变量
os.environ["DASHSCOPE_API_KEY"] = os.getenv("DASHSCOPE_API_KEY", "")
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")
os.environ.setdefault("ECAN_ENV", "development")

# 设置路径
_ROOT = Path("/Users/liuqiang/WorkSpace/ecan/eCan.ai")
sys.path.insert(0, str(_ROOT))

# 测试数据目录
TEST_DATA_DIR = _ROOT / "tests" / "test_data" / "product_listing"


class MockBrowserAutomationNode:
    """模拟 browser-automation 节点，用于测试文件读取逻辑"""

    def __init__(self, skill_data: dict):
        self.skill_data = skill_data
        self.executed = False
        self.result = {}
        self.input_type = None
        self.input_path = None

    def detect_input_type(self, input_text: str) -> Dict[str, Any]:
        """检测输入类型（FILE/FOLDER/TEXT/URL）"""
        if input_text.startswith("http://") or input_text.startswith("https://"):
            return {"input_type": "URL", "detected_path": ""}

        path = Path(input_text)
        if path.exists():
            if path.is_file():
                return {"input_type": "FILE", "detected_path": input_text}
            elif path.is_dir():
                return {"input_type": "FOLDER", "detected_path": input_text}

        return {"input_type": "TEXT", "detected_path": ""}

    def read_file_content(self, file_path: str) -> str:
        """读取文件内容"""
        try:
            path = Path(file_path)
            if not path.exists():
                return f"[文件不存在: {file_path}]"

            if path.suffix == ".json":
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return json.dumps(data, ensure_ascii=False, indent=2)
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception as e:
            return f"[读取失败: {e}]"

    def scan_folder(self, folder_path: str) -> list:
        """扫描文件夹"""
        try:
            path = Path(folder_path)
            if not path.exists() or not path.is_dir():
                return []

            files = []
            for f in path.iterdir():
                if f.is_file():
                    files.append({
                        "name": f.name,
                        "path": str(f),
                        "type": "file",
                        "size": f.stat().st_size if f.exists() else 0
                    })
            return files
        except Exception as e:
            return []

    def process_file_input(self, input_text: str) -> Dict[str, Any]:
        """处理文件输入"""
        detection = self.detect_input_type(input_text)
        self.input_type = detection.get("input_type")
        self.input_path = detection.get("detected_path") or input_text

        if self.input_type == "FILE":
            content = self.read_file_content(self.input_path)
            return {
                "input_type": "FILE",
                "file_path": self.input_path,
                "content": content,
                "success": True
            }
        elif self.input_type == "FOLDER":
            files = self.scan_folder(self.input_path)
            return {
                "input_type": "FOLDER",
                "folder_path": self.input_path,
                "files": files,
                "file_count": len(files),
                "success": True
            }
        else:
            return {
                "input_type": self.input_type,
                "error": "不是文件/文件夹类型",
                "success": False
            }


# 测试用例定义
FILE_TEST_CASES = [
    (f"{TEST_DATA_DIR}/product_info.txt", "FILE", "商品信息文本文件"),
    (f"{TEST_DATA_DIR}/product_info.json", "FILE", "商品信息JSON文件"),
    (f"{TEST_DATA_DIR}/product_info.md", "FILE", "商品信息Markdown文件"),
]

FOLDER_TEST_CASES = [
    (f"{TEST_DATA_DIR}", "FOLDER", "测试数据文件夹"),
]


@pytest.mark.asyncio
class TestFileReader:
    """文件读取测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """设置测试环境"""
        self.results = []

    @pytest.mark.parametrize("file_path,expected_type,description", FILE_TEST_CASES)
    async def test_file_type_detection(self, file_path: str, expected_type: str, description: str):
        """测试文件类型检测"""
        mock_node = MockBrowserAutomationNode({})
        detection = mock_node.detect_input_type(file_path)

        assert detection["input_type"] == expected_type, \
            f"期望类型 {expected_type}，实际 {detection['input_type']}"

    @pytest.mark.parametrize("file_path,expected_type,description", FILE_TEST_CASES)
    async def test_file_content_reading(self, file_path: str, expected_type: str, description: str):
        """测试文件内容读取"""
        mock_node = MockBrowserAutomationNode({})
        result = mock_node.process_file_input(file_path)

        assert result["success"] is True, f"文件读取失败: {result.get('error')}"
        assert result["input_type"] == "FILE"
        assert len(result["content"]) > 0, "文件内容为空"

        # 验证 JSON 文件解析正确
        if Path(file_path).suffix == ".json":
            data = json.loads(result["content"])
            assert "product_name" in data or "商品名称" in result["content"]

    @pytest.mark.parametrize("folder_path,expected_type,description", FOLDER_TEST_CASES)
    async def test_folder_scanning(self, folder_path: str, expected_type: str, description: str):
        """测试文件夹扫描"""
        mock_node = MockBrowserAutomationNode({})
        result = mock_node.process_file_input(folder_path)

        assert result["success"] is True, f"文件夹扫描失败: {result.get('error')}"
        assert result["input_type"] == "FOLDER"
        assert result["file_count"] >= 3, "测试数据文件夹应包含至少3个文件"

    async def test_text_input_not_file(self):
        """测试纯文本输入不被识别为文件"""
        mock_node = MockBrowserAutomationNode({})
        detection = mock_node.detect_input_type("上架iPhone 17 Pro Max")

        assert detection["input_type"] == "TEXT"
        assert detection["detected_path"] == ""

    async def test_url_detection(self):
        """测试 URL 检测"""
        mock_node = MockBrowserAutomationNode({})

        urls = [
            "https://www.apple.com.cn",
            "http://example.com/product",
        ]

        for url in urls:
            detection = mock_node.detect_input_type(url)
            assert detection["input_type"] == "URL", f"URL 未被正确识别: {url}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
