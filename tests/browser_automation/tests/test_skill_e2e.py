"""Skill 框架端到端测试

测试 product_listing_orchestrator_skill 的功能：
1. TEXT 类型输入处理
2. FILE/FOLDER 类型输入处理（需要 browser-automation）
3. URL 类型输入处理（需要 browser-automation）

运行方式：
    python -m pytest tests/browser_automation/tests/test_skill_e2e.py -v --type text
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import pytest

# 设置环境变量
os.environ["DASHSCOPE_API_KEY"] = os.getenv("DASHSCOPE_API_KEY", "")
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")
os.environ.setdefault("ECAN_ENV", "development")

# 设置路径
_ROOT = Path("/Users/liuqiang/WorkSpace/ecan/eCan.ai")
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

# Skill 文件路径
SKILL_FILE = str(_ROOT / "my_skills" / "product_listing_orchestrator_skill" / "diagram_dir" / "product_listing_orchestrator_skill.json")

# 测试数据目录
TEST_DATA_DIR = _ROOT / "tests" / "test_data" / "product_listing"


class SkillTester:
    """Skill 框架测试器"""

    def __init__(self, skill_file: str):
        self.skill_file = skill_file
        self.skill_data: Optional[Dict] = None
        self.graph = None
        self.results: list = []

    def load(self) -> bool:
        """加载 Skill"""
        try:
            from agent.ec_skills.flowgram2langgraph_v2 import flowgram2langgraph_v2

            with open(self.skill_file, 'r', encoding='utf-8') as f:
                self.skill_data = json.load(f)

            self.graph, _ = flowgram2langgraph_v2(
                self.skill_data,
                bundle_json=self.skill_data.get("bundle"),
                enable_subgraph=False
            )

            if self.graph is None:
                return False

            return True

        except Exception as e:
            print(f"❌ 加载失败: {e}")
            return False

    @staticmethod
    def create_state(input_text: str) -> Dict[str, Any]:
        """创建初始状态"""
        return {
            "input": input_text,
            "messages": [],
            "result": {},
            "tool_result": {},
            "attributes": {
                "__llm_timings__": [],
                "__node_timings__": [],
                "agent_id": "test_agent",
                "chat_id": "test_chat",
                "human": {"id": "user1", "name": "测试用户"},
                "thread_id": f"test_{int(time.time())}",
            },
            "prompts": [],
            "history": [],
            "threads": [],
            "events": [],
            "attachments": [],
            "error": "",
            "retries": 0,
            "condition": False,
            "condition_vars": {},
            "loop_end_vars": {},
            "case": "",
            "goals": [],
            "breakpoint": False,
            "max_steps": 100,
            "n_steps": 0,
            "metadata": {},
            "http_response": {},
            "cli_input": {},
            "cli_results": {}
        }

    async def run(self, input_text: str, timeout: int = 60) -> Dict[str, Any]:
        """运行 Skill"""
        if self.graph is None:
            return self.create_state(input_text)

        state = self.create_state(input_text)
        app = self.graph.compile()
        thread_id = f"test_{int(time.time())}"

        try:
            return await asyncio.wait_for(
                app.ainvoke(state, config={
                    "recursion_limit": 50,
                    "configurable": {"thread_id": thread_id}
                }),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            print(f"   ⚠️ 执行超时 ({timeout}s)")
            return state
        except Exception as e:
            print(f"   ⚠️ 执行异常: {type(e).__name__}: {e}")
            return state

    @staticmethod
    def extract_result(state: Dict) -> Dict:
        """提取结果"""
        result = state.get("result", {})
        tool_result = state.get("tool_result", {})

        llm_result = result.get("llm_result", {}) if isinstance(result, dict) else {}
        input_type_detector = result.get("input_type_detector", {})
        if isinstance(llm_result, dict) and "input_type" in llm_result:
            input_type = llm_result.get("input_type")
        elif isinstance(input_type_detector, dict) and "input_type" in input_type_detector:
            input_type = input_type_detector.get("input_type")
        else:
            input_type = None

        if isinstance(tool_result, dict):
            structured = tool_result.get("structured_collector", {})
        else:
            structured = result.get("structured_collector", {})

        if not isinstance(structured, dict):
            structured = {}

        product_name = llm_result.get("product_name") or structured.get("product_name") or ""
        is_complete = llm_result.get("is_complete") or structured.get("is_complete")
        missing = llm_result.get("missing_required_fields", []) or structured.get("missing_required_fields", [])
        if not isinstance(missing, list):
            missing = []

        if isinstance(tool_result, dict):
            executed_nodes = list(tool_result.keys())
        else:
            executed_nodes = []

        return {
            "llm_result": llm_result if isinstance(llm_result, dict) else {},
            "structured": structured,
            "product_name": product_name,
            "is_complete": is_complete,
            "missing": missing,
            "input_type": input_type,
            "executed_nodes": executed_nodes,
            "result": result,
            "tool_result": tool_result,
        }


# 测试用例定义
TEXT_TEST_CASES = [
    ("上架iPhone 17 Pro Max 256G 黑色 准新", True, "iPhone完整信息", "TEXT", "iPhone"),
    ("上架iphone17promax", False, "手机缺成色", "TEXT", "iphone"),
    ("转让一台 MacBook Pro M3 512G", False, "Mac缺成色", "TEXT", "Mac"),
    ("卖一个AirPods", False, "AirPods缺信息", "TEXT", "airpods"),
]

FILE_TEST_CASES = [
    (f"{TEST_DATA_DIR}/product_info.txt", "FILE", "商品信息文本文件"),
    (f"{TEST_DATA_DIR}/product_info.json", "FILE", "商品信息JSON文件"),
]

FOLDER_TEST_CASES = [
    (f"{TEST_DATA_DIR}", "FOLDER", "测试数据文件夹"),
]


@pytest.mark.skip(reason="需要 LLM 调用，请手动测试")
@pytest.mark.asyncio
class TestSkillFrameworkText:
    """TEXT 类型 Skill 测试"""

    @pytest.fixture(autouse=True)
    def setup_and_check(self):
        """设置测试环境并检查 Skill"""
        self.tester = SkillTester(SKILL_FILE)

        # 检查 Skill 是否存在
        if not Path(SKILL_FILE).exists():
            pytest.skip(f"Skill 文件不存在: {SKILL_FILE}")
        if not self.tester.load():
            pytest.skip("Skill 加载失败")

        yield

    @pytest.mark.parametrize("input_text,expected_complete,description,expected_type,expected_product", TEXT_TEST_CASES)
    async def test_text_input(self, input_text: str, expected_complete: bool, description: str, expected_type: str, expected_product: str):
        """测试 TEXT 类型输入"""
        print(f"\n🧪 {description}: {input_text}")

        start = time.time()
        state = await self.tester.run(input_text, timeout=60)
        elapsed = time.time() - start

        result = self.tester.extract_result(state)

        print(f"   ⏱️ 耗时: {elapsed:.2f}s")
        print(f"   input_type: {result['input_type']}")
        print(f"   product_name: {result['product_name']}")
        print(f"   is_complete: {result['is_complete']}")
        print(f"   missing: {result['missing']}")

        executed = result.get('executed_nodes', [])
        if 'browser_processor' in executed:
            actual_type = "FILE/FOLDER/URL"
        elif 'structured_collector' in executed:
            actual_type = "TEXT"
        else:
            actual_type = "UNKNOWN"

        type_ok = expected_type in actual_type
        product_ok = expected_product.lower() in result['product_name'].lower()
        complete_ok = result['is_complete'] == expected_complete

        assert type_ok, f"输入类型错误: 期望 {expected_type}, 实际 {actual_type}"
        assert product_ok, f"商品名称不匹配: {result['product_name']}"


@pytest.mark.skip(reason="需要真实浏览器，请在 GUI 环境下手动测试")
@pytest.mark.asyncio
class TestSkillFrameworkFile:
    """FILE 类型 Skill 测试"""

    @pytest.mark.browser
    @pytest.mark.parametrize("file_path,expected_type,description", FILE_TEST_CASES)
    async def test_file_input(self, file_path: str, expected_type: str, description: str):
        """测试 FILE 类型输入（需要真实浏览器）"""
        pytest.importorskip("browser_use")

        # 检查文件存在
        if not Path(file_path).exists():
            pytest.skip(f"测试文件不存在: {file_path}")

        print(f"\n🧪 {description}: {file_path}")

        # 验证文件可读
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert len(content) > 0, "文件内容为空"

        # 生成 file:// URL
        file_url = Path(file_path).absolute().as_uri()
        print(f"   🌐 File URL: {file_url}")


class TestSkillFrameworkData:
    """测试数据验证"""

    def test_test_data_exists(self):
        """验证测试数据文件存在"""
        assert TEST_DATA_DIR.exists(), f"测试数据目录不存在: {TEST_DATA_DIR}"

        txt_file = TEST_DATA_DIR / "product_info.txt"
        json_file = TEST_DATA_DIR / "product_info.json"
        md_file = TEST_DATA_DIR / "product_info.md"

        assert txt_file.exists(), "product_info.txt 不存在"
        assert json_file.exists(), "product_info.json 不存在"
        assert md_file.exists(), "product_info.md 不存在"

    def test_product_info_txt(self):
        """验证 product_info.txt 内容"""
        txt_file = TEST_DATA_DIR / "product_info.txt"
        with open(txt_file, 'r', encoding='utf-8') as f:
            content = f.read()

        assert "iPhone" in content or "商品名称" in content
        assert "Apple" in content

    def test_product_info_json(self):
        """验证 product_info.json 内容"""
        json_file = TEST_DATA_DIR / "product_info.json"
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert "product_name" in data
        assert data.get("brand") == "Apple"

    def test_product_info_md(self):
        """验证 product_info.md 内容"""
        md_file = TEST_DATA_DIR / "product_info.md"
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        assert "索尼" in content or "A7M4" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--type", "text"])
