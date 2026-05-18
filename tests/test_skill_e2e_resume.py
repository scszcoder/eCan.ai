"""E2E 测试：验证 pend_event_node 事件恢复机制

Bug 根因：
1. GUI 用户输入 "256G" → GraphQL → send_chat
2. normalize_event() 将 send_chat → chat_message
3. pend_input_wait 等待 human_chat，accepted = {"human_chat", "send_chat"}
4. chat_message 不在 accepted 中 → 永远挂起直到超时

修复：在 build_pend_event_node 中，当等待 human_chat 时，
添加 chat_message 作为别名（send_chat 也已添加）。

TODO(统一命名)：后续将 chat_message / send_chat / human_chat 统一为 1:1 命名，
届时可删除 chat_message 别名，仅保留 send_chat。
见 conversation: 2026-05-17 关于事件类型命名统一讨论。

运行：
    .venv/bin/python -m pytest tests/test_skill_e2e_resume.py -v -s
"""

import inspect
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path("/Users/liuqiang/WorkSpace/ecan/eCan.ai")
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)


# ---------------------------------------------------------------------------
# accepted_event_types 别名验证
# ---------------------------------------------------------------------------

class TestPendEventAcceptedTypes:
    """验证 pend_event_node 的 accepted_event_types 别名逻辑"""

    def test_human_chat_aliases(self):
        """
        核心测试：验证 human_chat 等待者的 accepted_event_types 包含：
        1. human_chat - 原始配置
        2. send_chat - GUI 发送的原始类型（已修复）
        3. chat_message - normalize_event 转换后的类型（本次修复）

        这是修复的关键验证。
        """
        from agent.ec_skills.build_node import build_pend_event_node

        source = inspect.getsource(build_pend_event_node)

        # 查找 human_chat 别名块
        human_chat_block = None
        for pattern in ['if "human_chat" in accepted_event_types:', "if 'human_chat' in accepted_event_types:"]:
            idx = source.find(pattern)
            if idx != -1:
                # 提取足够长的代码块来包含所有别名
                human_chat_block = source[idx:idx + 600]
                break

        assert human_chat_block is not None, "找不到 human_chat 别名块"
        print(f"\n=== human_chat 别名块 ===")
        print(human_chat_block[:400])

        # 验证 send_chat 别名存在（之前已有的修复）
        has_send_chat = '"send_chat"' in human_chat_block or "'send_chat'" in human_chat_block
        assert has_send_chat, (
            "human_chat 应该添加 send_chat 别名。"
            "这是之前已修复的别名。"
        )
        print("✓ human_chat → send_chat 别名存在")

        # 验证 chat_message 别名存在（本次修复）
        has_chat_message = '"chat_message"' in human_chat_block or "'chat_message'" in human_chat_block
        assert has_chat_message, (
            "BUG：human_chat 应该添加 chat_message 别名！"
            "normalize_event 将 send_chat → chat_message，"
            "如果不在 accepted 中，skill 将永远挂起。"
        )
        print("✓ human_chat → chat_message 别名存在（修复确认）")

    def test_accepted_types_summary(self):
        """汇总：所有等待类型及其别名"""
        from agent.ec_skills.build_node import build_pend_event_node

        source = inspect.getsource(build_pend_event_node)

        print(f"\n=== accepted_event_types 别名汇总 ===")

        # 规则1：chat_message → a2a_response, a2a_task_result
        if 'if "chat_message" in accepted_event_types:' in source:
            print("✓ chat_message → 添加 a2a_response, a2a_task_result 别名")
        else:
            print("⚠ chat_message 没有 a2a 别名块（可能不是问题）")

        # 规则2：human_chat → send_chat, chat_message
        human_chat_block = None
        for pattern in ['if "human_chat" in accepted_event_types:', "if 'human_chat' in accepted_event_types:"]:
            idx = source.find(pattern)
            if idx != -1:
                human_chat_block = source[idx:idx + 600]
                break

        if human_chat_block:
            send_chat_ok = '"send_chat"' in human_chat_block or "'send_chat'" in human_chat_block
            chat_msg_ok = '"chat_message"' in human_chat_block or "'chat_message'" in human_chat_block

            print(f"  human_chat → send_chat: {'✓' if send_chat_ok else '✗'}")
            print(f"  human_chat → chat_message: {'✓' if chat_msg_ok else '✗ (BUG)'}")

            if not chat_msg_ok:
                print("\n🚨 BUG 未修复：accepted_event_types 缺少 chat_message 别名！")

            assert chat_msg_ok, (
                "BUG：human_chat 等待者的 accepted_event_types 缺少 chat_message 别名。"
                "这会导致 skill 在 GUI 用户输入后永远挂起。"
            )
        else:
            pytest.fail("找不到 human_chat 别名块")

    def test_other_event_type_aliases(self):
        """验证其他事件类型的别名逻辑"""
        from agent.ec_skills.build_node import build_pend_event_node

        source = inspect.getsource(build_pend_event_node)

        print(f"\n=== 其他事件类型别名 ===")

        # chat_message → a2a_response, a2a_task_result
        if 'if "chat_message" in accepted_event_types:' in source:
            idx = source.find('if "chat_message" in accepted_event_types:')
            block = source[idx:idx + 300]
            has_a2a = '"a2a_response"' in block or "'a2a_response'" in block
            print(f"  chat_message → a2a_response: {'✓' if has_a2a else '✗'}")
            assert has_a2a, "chat_message 应该添加 a2a_response 别名"

    def test_pend_node_can_be_built(self):
        """验证 pend_event_node 可以正常构建（不报错）"""
        from agent.ec_skills.build_node import build_pend_event_node
        from agent.ec_skills.dev_defs import BreakpointManager

        # 测试 human_chat 配置
        config = {
            "inputsValues": {
                "eventType": {"content": "human_chat"}
            }
        }

        bp_mgr = BreakpointManager()
        node_func = build_pend_event_node(config, "test_pend", "test_skill", "test_owner", bp_mgr)

        assert callable(node_func), "build_pend_event_node 应返回一个可调用对象"
        print(f"\n✓ pend_event_node 函数构建成功: {type(node_func)}")


class TestEventTypeConversion:
    """验证事件类型的转换逻辑"""

    def test_event_types_in_normalize_event(self):
        """分析 normalize_event 对 send_chat 的处理"""
        from agent.ec_tasks.resume import normalize_event, _infer_event_type

        # _infer_event_type 是 normalize_event 内部使用的转换函数
        # 它将 send_chat → chat_message
        result = _infer_event_type("send_chat")
        print(f"\n=== _infer_event_type ===")
        print(f"  send_chat → {result}")

        assert result == "chat_message", f"send_chat 应该转为 chat_message，实际: {result}"
        print("✓ _infer_event_type 正确转换 send_chat → chat_message")

    def test_resume_payload_event_type_flow(self):
        """
        验证 resume payload 的事件类型流：
        1. GUI 发送 send_chat
        2. _infer_event_type → chat_message
        3. normalize_event 设置 event["type"] = "chat_message"
        4. build_general_resume_payload 使用 event["type"] 构建 resume_payload["event_type"]
        5. pend_event_node 检查 event_type in accepted_event_types

        如果 accepted 不包含 chat_message，第 5 步失败。
        """
        from agent.ec_tasks.resume import normalize_event, _infer_event_type

        # 模拟 GUI 发送的消息
        gui_msg = {
            "method": "send_chat",
            "params": {
                "metadata": {
                    "params": {
                        "role": "user",
                        "senderType": "human"
                    }
                }
            }
        }

        # Step 1-3: normalize_event
        normalized = normalize_event("send_chat", gui_msg)
        event_type = normalized.get("type", "")

        print(f"\n=== resume payload 事件类型流 ===")
        print(f"Step 1: GUI method = 'send_chat'")
        print(f"Step 2: _infer_event_type('send_chat') = '{_infer_event_type('send_chat')}'")
        print(f"Step 3: normalized event['type'] = '{event_type}'")

        # 验证 _infer_event_type 确实转换了类型
        assert _infer_event_type("send_chat") == "chat_message", (
            "_infer_event_type 应将 send_chat 转为 chat_message"
        )

        # Step 4: 在 resume.py 的 build_general_resume_payload 中：
        # resume_payload["event_type"] = event.get("type") = "chat_message"
        resume_event_type = event_type  # 这是 resume_payload["event_type"]

        # Step 5: pend_event_node 的检查
        # if resume_event_type in accepted_event_types:
        from agent.ec_skills.build_node import build_pend_event_node
        source = inspect.getsource(build_pend_event_node)

        human_chat_block = None
        for pattern in ['if "human_chat" in accepted_event_types:', "if 'human_chat' in accepted_event_types:"]:
            idx = source.find(pattern)
            if idx != -1:
                human_chat_block = source[idx:idx + 600]
                break

        # 模拟 accepted_event_types（human_chat 等待者）
        accepted = {"human_chat"}
        if human_chat_block:
            if '"send_chat"' in human_chat_block or "'send_chat'" in human_chat_block:
                accepted.add("send_chat")
            if '"chat_message"' in human_chat_block or "'chat_message'" in human_chat_block:
                accepted.add("chat_message")

        print(f"Step 4: resume_payload['event_type'] = '{resume_event_type}'")
        print(f"Step 5: accepted_event_types = {accepted}")
        print(f"        {resume_event_type} in {accepted} = {resume_event_type in accepted}")

        # 关键断言：resume_event_type 应该在 accepted 中
        assert resume_event_type in accepted, (
            f"BUG 确认：event_type='{resume_event_type}' 不在 accepted={accepted} 中。"
            f"这意味着用户输入后 skill 将永远挂起！"
        )
        print(f"\n✓ 完整事件类型流验证通过：")
        print(f"  GUI send_chat → chat_message → accepted ✓")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
