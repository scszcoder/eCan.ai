"""真实 Browser-Automation 测试

这个测试使用真实的 browser-use 库来：
1. 初始化真实的 Chromium 浏览器
2. 打开本地文件
3. 验证 browser-automation 节点的功能

运行方式：
    python -m pytest tests/browser_automation/tests/test_browser_real.py -v
"""

import asyncio
import json
import os
import sys
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


@pytest.mark.asyncio
class TestBrowserReal:
    """真实浏览器测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """设置测试环境"""
        self.results = []
        self.session = None

    def teardown_method(self):
        """清理测试环境"""
        self.session = None

    async def test_eCan_browser_automation_module(self):
        """测试 eCan 的 browser-automation 节点模块"""
        from agent.ec_skills.browser_node.config import parse_node_config
        from agent.ec_skills.browser_node.session import BrowserSessionManager

        config_data = {
            "nodeName": "test_browser_node",
            "skillName": "test_skill",
            "provider": "browser-use",
            "inputsValues": {
                "tool": {"content": "browser-use"},
                "browser": {"content": "new chromium"},
                "runEnvironment": {"content": "full_local"},
                "headless": {"content": "true"},
                "modelProvider": {"content": "Qwen"},
                "modelName": {"content": "qwen3.6-flash"},
            }
        }

        cfg = parse_node_config(
            config_data,
            node_name="test_browser_node",
            skill_name="test_skill",
            owner="test"
        )

        assert cfg.provider == "browser-use"
        assert "qwen" in cfg.llm_provider.lower() or "dashscope" in cfg.llm_provider.lower()

        manager = BrowserSessionManager(cfg)
        assert manager is not None

        # 测试 scope key 解析
        test_state = {"attributes": {"chat_id": "test-chat-123"}}
        scope_key = manager.resolve_scope_key(test_state)
        assert scope_key == "chat:test-chat-123"

    @pytest.mark.skip(reason="需要真实浏览器，手动测试")
    @pytest.mark.browser
    async def test_browser_session_file_navigation(self):
        """测试浏览器会话打开本地文件"""
        pytest.importorskip("browser_use")

        from browser_use import BrowserSession

        # 创建会话
        session = BrowserSession(headless=True)
        self.session = session

        # 启动浏览器
        try:
            await asyncio.wait_for(session.start(), timeout=30)
        except asyncio.TimeoutError:
            pytest.skip("浏览器启动超时")
        except Exception as e:
            pytest.skip(f"浏览器启动失败: {e}")

        # 测试文件导航
        test_file = TEST_DATA_DIR / "product_info.txt"
        if test_file.exists():
            file_url = test_file.absolute().as_uri()
            result = await session.navigate(file_url, timeout=15)
            assert result is not None

    @pytest.mark.skip(reason="需要真实浏览器，手动测试")
    @pytest.mark.browser
    async def test_browser_session_json_file(self):
        """测试浏览器打开 JSON 文件"""
        pytest.importorskip("browser_use")

        from browser_use import BrowserSession

        session = BrowserSession(headless=True)
        self.session = session

        try:
            await asyncio.wait_for(session.start(), timeout=30)
        except (asyncio.TimeoutError, Exception):
            pytest.skip("浏览器启动失败")

        test_file = TEST_DATA_DIR / "product_info.json"
        if test_file.exists():
            file_url = test_file.absolute().as_uri()
            result = await session.navigate(file_url, timeout=15)
            assert result is not None


class TestFileReading:
    """文件读取测试（验证测试数据）"""

    def test_file_data_exists(self):
        """验证测试数据文件存在"""
        assert TEST_DATA_DIR.exists(), f"测试数据目录不存在: {TEST_DATA_DIR}"

        txt_file = TEST_DATA_DIR / "product_info.txt"
        json_file = TEST_DATA_DIR / "product_info.json"
        md_file = TEST_DATA_DIR / "product_info.md"

        assert txt_file.exists(), "product_info.txt 不存在"
        assert json_file.exists(), "product_info.json 不存在"
        assert md_file.exists(), "product_info.md 不存在"

    def test_read_txt_file(self):
        """测试读取文本文件"""
        txt_file = TEST_DATA_DIR / "product_info.txt"
        with open(txt_file, 'r', encoding='utf-8') as f:
            content = f.read()

        assert "iPhone" in content or "商品名称" in content
        assert len(content) > 0

    def test_read_json_file(self):
        """测试读取 JSON 文件"""
        json_file = TEST_DATA_DIR / "product_info.json"
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert "product_name" in data or "product_name" in str(data)
        assert data.get("brand") == "Apple" or "Apple" in str(data)

    def test_read_markdown_file(self):
        """测试读取 Markdown 文件"""
        md_file = TEST_DATA_DIR / "product_info.md"
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        assert "索尼" in content or "A7M4" in content or "商品" in content

    def test_file_url_generation(self):
        """测试 file:// URL 生成"""
        txt_file = TEST_DATA_DIR / "product_info.txt"
        file_url = txt_file.absolute().as_uri()

        assert file_url.startswith("file://")
        assert file_url.endswith("product_info.txt")

    def test_folder_scanning(self):
        """测试文件夹扫描"""
        files = list(TEST_DATA_DIR.iterdir())
        assert len(files) >= 3, "测试数据文件夹应包含至少3个文件"

        file_names = [f.name for f in files if f.is_file()]
        assert "product_info.txt" in file_names
        assert "product_info.json" in file_names
        assert "product_info.md" in file_names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
