#!/usr/bin/env python3
"""
测试节点 builder 映射是否正确注册
确保所有 skill 中使用的节点类型都有对应的 builder
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_pend_event_node_builder_exists():
    """测试 pend_event_node builder 是否存在"""
    from agent.ec_skills.flowgram2langgraph import function_registry as FUNCTION_REGISTRY

    assert "pend_event_node" in FUNCTION_REGISTRY, (
        "pend_event_node builder 不存在于 FUNCTION_REGISTRY"
    )
    print("✓ pend_event_node builder 存在")


def test_all_skill_node_types_have_builders():
    """测试所有 skill 中使用的节点类型都有对应的 builder"""
    import json

    from agent.ec_skills.flowgram2langgraph import function_registry as FUNCTION_REGISTRY

    # 加载所有 skill 文件
    skills_dir = "my_skills"
    if not os.path.exists(skills_dir):
        print(f"⚠️ Skills 目录不存在: {skills_dir}")
        return

    # 特殊节点类型，这些不需要 builder，会在转换过程中被处理
    SPECIAL_NODE_TYPES = {"start", "end", "group", "sheet-inputs", "sheet_inputs", "sheet-outputs", "sheet_outputs", "sheet-call", "sheet_call"}

    node_types_without_builders = []

    for skill_name in os.listdir(skills_dir):
        skill_path = os.path.join(skills_dir, skill_name)
        if not os.path.isdir(skill_path):
            continue

        diagram_dir = os.path.join(skill_path, "diagram_dir")
        if not os.path.exists(diagram_dir):
            continue

        for f in os.listdir(diagram_dir):
            if not f.endswith(".json"):
                continue

            skill_file = os.path.join(diagram_dir, f)
            try:
                with open(skill_file, "r", encoding="utf-8") as fp:
                    skill_data = json.load(fp)

                # 获取所有节点
                workflow = skill_data.get("workFlow", {})
                nodes = workflow.get("nodes", [])

                for node in nodes:
                    node_type = node.get("type")
                    # 跳过特殊节点类型（不需要 builder）
                    if node_type and node_type not in SPECIAL_NODE_TYPES and node_type not in FUNCTION_REGISTRY:
                        node_id = node.get("id", "unknown")
                        if node_type not in [item["node_type"] for item in node_types_without_builders]:
                            node_types_without_builders.append({
                                "skill": skill_name,
                                "node_id": node_id,
                                "node_type": node_type
                            })
            except Exception as e:
                print(f"⚠️ 读取 {skill_file} 失败: {e}")

    if node_types_without_builders:
        msg = "\n".join([
            f"  - {item['skill']}/{item['node_id']}: {item['node_type']}"
            for item in node_types_without_builders
        ])
        print(f"\n❌ 以下节点类型没有对应的 builder:")
        print(msg)
        assert False, f"发现 {len(node_types_without_builders)} 个节点类型没有 builder"
    else:
        print("✓ 所有 skill 中使用的节点类型都有对应的 builder")


def test_product_listing_pend_input_wait_node():
    """专门测试 product_listing_orchestrator skill 中的 pend_input_wait 节点"""
    import json

    from agent.ec_skills.flowgram2langgraph import function_registry as FUNCTION_REGISTRY

    skill_file = "my_skills/product_listing_orchestrator_skill/diagram_dir/product_listing_orchestrator_skill.json"

    if not os.path.exists(skill_file):
        print(f"⚠️ Skill 文件不存在: {skill_file}")
        return

    with open(skill_file, "r", encoding="utf-8") as f:
        skill_data = json.load(f)

    # 查找 pend_input_wait 节点
    nodes = skill_data.get("workFlow", {}).get("nodes", [])
    pend_input_node = None
    for node in nodes:
        if node.get("id") == "pend_input_wait":
            pend_input_node = node
            break

    assert pend_input_node is not None, "找不到 pend_input_wait 节点"

    node_type = pend_input_node.get("type")
    print(f"✓ pend_input_wait 节点类型: {node_type}")

    # 检查是否有对应的 builder
    assert node_type in FUNCTION_REGISTRY, (
        f"pend_input_wait 节点类型 '{node_type}' 没有对应的 builder"
    )
    print(f"✓ {node_type} 有对应的 builder")


def test_chat_node_has_valid_message_template():
    """测试 chat_node 节点使用正确的 messageTemplate 字段"""
    import json

    skill_file = "my_skills/product_listing_orchestrator_skill/diagram_dir/product_listing_orchestrator_skill.json"

    if not os.path.exists(skill_file):
        print(f"⚠️ Skill 文件不存在: {skill_file}")
        return

    with open(skill_file, "r", encoding="utf-8") as f:
        skill_data = json.load(f)

    nodes = skill_data.get("workFlow", {}).get("nodes", [])
    errors = []

    for node in nodes:
        if node.get("type") == "chat_node":
            node_id = node.get("id", "unknown")
            inputs_values = node.get("data", {}).get("inputsValues", {})

            # 标准字段名是 messageTemplate（与 node_config_agent.py 一致）
            has_message_template = (
                isinstance(inputs_values.get("messageTemplate"), dict) or
                isinstance(inputs_values.get("messageTemplate"), str)
            )

            if not has_message_template:
                errors.append(f"{node_id}: 缺少必需的 inputsValues.messageTemplate 字段")

    if errors:
        print(f"\n❌ chat_node 配置错误:")
        for err in errors:
            print(f"  - {err}")
        assert False, f"发现 {len(errors)} 个 chat_node 配置错误"
    else:
        print("✓ 所有 chat_node 节点都使用了正确的 messageTemplate 字段")


def test_pend_input_wait_waits_for_human_input():
    """测试 pend_input_wait 节点配置为等待 human_chat 事件"""
    import json

    skill_file = "my_skills/product_listing_orchestrator_skill/diagram_dir/product_listing_orchestrator_skill.json"

    with open(skill_file, "r", encoding="utf-8") as f:
        skill_data = json.load(f)

    nodes = skill_data.get("workFlow", {}).get("nodes", [])
    for node in nodes:
        if node.get("id") == "pend_input_wait":
            inputs_values = node.get("data", {}).get("inputsValues", {})
            event_type = inputs_values.get("eventType", {}).get("content")
            assert event_type == "human_chat", (
                f"pend_input_wait 应该等待 human_chat 事件，实际: {event_type}"
            )
            print(f"✓ pend_input_wait 配置为等待 human_chat 事件")
            return

    print("⚠️ 未找到 pend_input_wait 节点")


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 节点 Builder 映射测试")
    print("=" * 60)

    test_pend_event_node_builder_exists()
    test_product_listing_pend_input_wait_node()
    test_pend_input_wait_waits_for_human_input()
    test_chat_node_has_valid_message_template()  # 新增：测试 chat_node 配置
    test_all_skill_node_types_have_builders()

    print("\n" + "=" * 60)
    print("✅ 所有测试通过!")
    print("=" * 60)
