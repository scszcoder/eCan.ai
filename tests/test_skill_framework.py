#!/usr/bin/env python3
"""
Skill 框架测试套件
==================

支持测试的节点类型：
- ✅ TEXT: 直接通过 LLM 处理
- ⚠️ URL/FILE/FOLDER: 需要浏览器环境 (browser-automation 节点)

浏览器相关测试需要在 eCan.ai GUI 中手动测试。
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# 设置环境变量
os.environ["DASHSCOPE_API_KEY"] = os.getenv("DASHSCOPE_API_KEY", "sk-6ca3a58ae47f44ea992be2b3f47d621e")
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "sk-6ca3a58ae47f44ea992be2b3f47d621e")
os.environ.setdefault("ECAN_ENV", "development")

# 设置路径
_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

# 测试数据目录
TEST_DATA_DIR = _ROOT / "tests" / "test_data" / "skill_framework"
SKILL_FILE = str(_ROOT / "my_skills" / "product_listing_orchestrator_skill" / "diagram_dir" / "product_listing_orchestrator_skill.json")


# ============================================================================
# 辅助函数
# ============================================================================

def setup_test_files():
    """准备测试文件"""
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 商品信息文本文件
    (TEST_DATA_DIR / "product_info.txt").write_text("""商品名称: iPhone 15 Pro Max
品牌: Apple
容量: 256GB
颜色: 原色钛金属
成色: 99新
价格: 6999元
""", encoding="utf-8")

    # 商品信息 JSON 文件
    (TEST_DATA_DIR / "product_info.json").write_text(json.dumps({
        "product_name": "AirPods Pro 2代",
        "brand": "Apple",
        "condition": "全新",
        "price": 1699
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # 商品信息 Markdown 文件
    (TEST_DATA_DIR / "product_info.md").write_text("""# 商品信息
- 商品: 索尼A7M4微单相机
- 品牌: 索尼
- 成色: 95新
- 价格: 14500元
""", encoding="utf-8")

    return TEST_DATA_DIR


def check_skill_file() -> bool:
    """检查 Skill 文件是否存在"""
    if not Path(SKILL_FILE).exists():
        print(f"❌ Skill 文件不存在: {SKILL_FILE}")
        return False
    return True


# ============================================================================
# Skill 测试类
# ============================================================================

class SkillTester:
    """Skill 框架测试器"""

    def __init__(self, skill_file: str):
        self.skill_file = skill_file
        self.skill_data: Optional[Dict] = None
        self.graph = None
        self.results: list = []

    def load(self) -> bool:
        """加载 Skill"""
        print(f"📂 加载 Skill: {self.skill_file}")

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
                print("❌ Skill graph 转换失败")
                return False

            print("✅ Skill 加载成功")
            return True

        except ImportError as e:
            print(f"❌ 导入失败: {e}")
            return False
        except Exception as e:
            print(f"❌ 加载失败: {type(e).__name__}: {e}")
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
            print(f"   ⚠️ 执行异常: {type(e).__name__}")
            return state

    @staticmethod
    def extract_result(state: Dict) -> Dict:
        """提取结果"""
        result = state.get("result", {})
        tool_result = state.get("tool_result", {})

        # 获取 LLM 结果
        llm_result = result.get("llm_result", {}) if isinstance(result, dict) else {}

        # input_type 检测
        input_type_detector = result.get("input_type_detector", {})
        if isinstance(llm_result, dict) and "input_type" in llm_result:
            input_type = llm_result.get("input_type")
        elif isinstance(input_type_detector, dict) and "input_type" in input_type_detector:
            input_type = input_type_detector.get("input_type")
        else:
            input_type = None

        # structured_collector 结果
        if isinstance(tool_result, dict):
            structured = tool_result.get("structured_collector", {})
            if isinstance(structured, dict):
                pass
            else:
                structured = result.get("structured_collector", {})
        else:
            structured = result.get("structured_collector", {})

        if not isinstance(structured, dict):
            structured = {}

        product_name = (
            llm_result.get("product_name") or
            structured.get("product_name") or
            ""
        )
        is_complete = (
            llm_result.get("is_complete") or
            structured.get("is_complete")
        )
        missing = (
            llm_result.get("missing_required_fields", []) or
            structured.get("missing_required_fields", [])
        )
        if not isinstance(missing, list):
            missing = []

        # 执行节点
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

    async def test_case(
        self,
        input_text: str,
        expected_complete: Optional[bool] = None,
        description: str = "",
        expected_type: Optional[str] = None,
        expected_product: Optional[str] = None,
        timeout: int = 60
    ) -> bool:
        """测试单个用例"""
        print(f"\n{'='*60}")
        print(f"🧪 {description or input_text[:50]}")
        print(f"📥 输入: {input_text}")

        start = time.time()
        state = await self.run(input_text, timeout=timeout)
        elapsed = time.time() - start

        result = self.extract_result(state)

        print(f"\n⏱️ 耗时: {elapsed:.2f}s")
        print(f"📤 结果:")
        print(f"   input_type: {result['input_type']}")
        print(f"   product_name: {result['product_name']}")
        print(f"   is_complete: {result['is_complete']}")
        print(f"   missing: {result['missing']}")
        print(f"   执行节点: {result['executed_nodes']}")

        # 验证
        is_complete = result.get('is_complete', False)

        # 根据执行的节点判断输入类型
        executed = result.get('executed_nodes', [])
        if 'browser_processor' in executed:
            actual_type = "FILE/FOLDER/URL"
        elif 'structured_collector' in executed:
            actual_type = "TEXT"
        else:
            actual_type = "UNKNOWN"

        type_ok = (expected_type is None) or (expected_type in actual_type)
        product_ok = (expected_product is None) or (expected_product.lower() in result['product_name'].lower())
        complete_ok = (expected_complete is None) or (is_complete == expected_complete)

        passed = type_ok and product_ok and complete_ok

        status = "✅" if passed else "❌"
        print(f"\n{status} 验证:")
        print(f"   输入类型: {'✅' if type_ok else '❌'} (期望={expected_type}, 实际={actual_type})")
        if expected_product:
            print(f"   商品名称: {'✅' if product_ok else '❌'} (期望含'{expected_product}')")
        if expected_complete is not None:
            print(f"   完整性: {'✅' if complete_ok else '❌'} (期望={'完整' if expected_complete else '追问'})")

        self.results.append({
            "input": input_text,
            "description": description,
            "expected_complete": expected_complete,
            "expected_type": expected_type,
            "expected_product": expected_product,
            "actual_complete": is_complete,
            "actual_type": actual_type,
            "actual_product": result['product_name'],
            "passed": passed,
            "elapsed": elapsed,
            "executed_nodes": executed,
        })
        return passed

    def summary(self) -> bool:
        """输出测试总结"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.get('passed'))

        print(f"\n{'='*60}")
        print(f"📊 测试总结: {passed}/{total} 通过")
        print(f"{'='*60}")

        # 按类型统计
        by_type: Dict[str, Dict] = {}
        for r in self.results:
            t = r.get('expected_type') or 'TEXT'
            if t not in by_type:
                by_type[t] = {"total": 0, "passed": 0}
            by_type[t]["total"] += 1
            if r.get('passed'):
                by_type[t]["passed"] += 1

        print(f"\n📋 按输入类型统计:")
        for t, stats in by_type.items():
            print(f"   {t}: {stats['passed']}/{stats['total']}")

        # 失败用例详情
        failed = [r for r in self.results if not r.get('passed')]
        if failed:
            print(f"\n❌ 失败用例 ({len(failed)}):")
            for r in failed:
                print(f"   - {r['description'] or r['input'][:40]}")

        # 保存报告
        report = {
            "timestamp": datetime.now().isoformat(),
            "framework": "flowgram2langgraph_v2",
            "skill_file": self.skill_file,
            "summary": {"total": total, "passed": passed, "failed": total - passed},
            "by_type": by_type,
            "results": self.results
        }

        report_file = "tests/test_results/skill_framework_report.json"
        Path(report_file).parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n📄 报告已保存: {report_file}")
        return passed == total


# ============================================================================
# 测试用例定义
# ============================================================================

TEXT_TEST_CASES = [
    # (输入, 期望完整, 描述, 期望类型, 期望商品关键词)
    ("上架iPhone 17 Pro Max 256G 黑色 准新", True, "iPhone完整信息", "TEXT", "iPhone"),
    ("上架iphone17promax", False, "手机缺成色", "TEXT", "iphone"),
    ("转让一台 MacBook Pro M3 512G", True, "Mac完整信息", "TEXT", "Mac"),
    ("卖一个AirPods", False, "AirPods缺信息", "TEXT", "airpods"),
]

URL_TEST_CASES = [
    # (输入, 期望类型, 描述)
    ("https://www.apple.com.cn/shop/buy-iphone", "FILE/FOLDER/URL", "Apple官网iPhone页面"),
    ("https://www.jd.com/product/123456.html", "FILE/FOLDER/URL", "京东商品页面"),
]

FILE_TEST_CASES = [
    # (输入, 期望类型, 描述)
    (f"{TEST_DATA_DIR}/product_info.txt", "FILE/FOLDER/URL", "商品信息文本文件"),
    (f"{TEST_DATA_DIR}/product_info.json", "FILE/FOLDER/URL", "商品信息JSON文件"),
    (f"{TEST_DATA_DIR}/product_info.md", "FILE/FOLDER/URL", "商品信息Markdown文件"),
]

FOLDER_TEST_CASES = [
    # (输入, 期望类型, 描述)
    (f"{TEST_DATA_DIR}", "FILE/FOLDER/URL", "测试数据文件夹"),
]


# ============================================================================
# 主函数
# ============================================================================

async def run_tests(include_types: list = None):
    """运行测试

    Args:
        include_types: 要测试的类型，如 ["text", "url", "file", "folder"]
                     默认测试所有支持的类型
    """
    if include_types is None:
        include_types = ["text"]

    print(f"{'='*60}")
    print("🚀 Skill 框架测试")
    print(f"{'='*60}")
    print(f"测试类型: {', '.join(include_types)}")
    print(f"支持类型: text (✅), url/file/folder (⚠️ 需要浏览器)")

    # 检查 Skill 文件
    if not check_skill_file():
        return False

    # 准备测试文件
    if "file" in include_types or "folder" in include_types:
        setup_test_files()

    # 加载 Skill
    tester = SkillTester(SKILL_FILE)
    if not tester.load():
        return False

    # 统计
    all_results = []

    # TEXT 类型测试
    if "text" in include_types:
        print(f"\n{'='*60}")
        print("📝 TEXT 类型测试 (可直接运行)")
        print(f"{'='*60}")

        for case in TEXT_TEST_CASES:
            passed = await tester.test_case(*case)
            all_results.append({
                "passed": passed,
                "description": case[2] or case[0][:40],
                "input": case[0],
                "expected_type": case[3]
            })

    # URL 类型测试 (仅检查路由)
    if "url" in include_types:
        print(f"\n{'='*60}")
        print("🔗 URL 类型测试 (需要浏览器环境)")
        print(f"{'='*60}")
        print("⚠️ URL 测试需要 browser-automation 节点")
        print("⚠️ 请在 eCan.ai GUI 中手动测试")
        for case in URL_TEST_CASES:
            print(f"   - {case[2]}: {case[0]}")
            all_results.append({"passed": None, "description": case[2], "input": case[0], "expected_type": "FILE/FOLDER/URL"})

    # FILE 类型测试 (仅检查路由)
    if "file" in include_types:
        print(f"\n{'='*60}")
        print("📄 FILE 类型测试 (需要浏览器环境)")
        print(f"{'='*60}")
        print("⚠️ FILE 测试需要 browser-automation 节点")
        print("⚠️ 请在 eCan.ai GUI 中手动测试")
        for case in FILE_TEST_CASES:
            print(f"   - {case[2]}: {case[0]}")
            all_results.append({"passed": None, "description": case[2], "input": case[0], "expected_type": "FILE/FOLDER/URL"})

    # FOLDER 类型测试 (仅检查路由)
    if "folder" in include_types:
        print(f"\n{'='*60}")
        print("📁 FOLDER 类型测试 (需要浏览器环境)")
        print(f"{'='*60}")
        print("⚠️ FOLDER 测试需要 browser-automation 节点")
        print("⚠️ 请在 eCan.ai GUI 中手动测试")
        for case in FOLDER_TEST_CASES:
            print(f"   - {case[2]}: {case[0]}")
            all_results.append({"passed": None, "description": case[2], "input": case[0], "expected_type": "FILE/FOLDER/URL"})

    # 输出总结
    total = len(all_results)
    passed = sum(1 for r in all_results if r.get('passed') is True)
    failed = sum(1 for r in all_results if r.get('passed') is False)
    skipped = sum(1 for r in all_results if r.get('passed') is None)

    print(f"\n{'='*60}")
    print(f"📊 测试总结: {passed}/{total} 通过")
    if failed > 0:
        print(f"   失败: {failed}")
    if skipped > 0:
        print(f"   跳过 (需要浏览器): {skipped}")
    print(f"{'='*60}")

    # 失败用例详情
    failed_cases = [r for r in all_results if r.get('passed') is False]
    if failed_cases:
        print(f"\n❌ 失败用例 ({len(failed_cases)}):")
        for r in failed_cases:
            print(f"   - {r['description'] or r['input'][:40]}")

    # 保存报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "framework": "flowgram2langgraph_v2",
        "skill_file": SKILL_FILE,
        "summary": {"total": total, "passed": passed, "failed": failed, "skipped": skipped},
        "results": all_results
    }

    report_file = "tests/test_results/skill_framework_report.json"
    Path(report_file).parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n📄 报告已保存: {report_file}")
    return passed == total and failed == 0


async def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Skill 框架测试")
    parser.add_argument(
        "--type",
        "-t",
        nargs="+",
        choices=["text", "url", "file", "folder", "all"],
        default=["text"],
        help="测试类型 (默认: text)"
    )
    args = parser.parse_args()

    types = args.type
    if "all" in types:
        types = ["text", "url", "file", "folder"]

    success = await run_tests(types)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
