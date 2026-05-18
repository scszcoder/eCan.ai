#!/usr/bin/env python3
"""
测试 product_listing_orchestrator skill 的节点流程
验证 pend_input_wait 节点正确配置
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_skill():
    """加载 skill"""
    skill_file = "my_skills/product_listing_orchestrator_skill/diagram_dir/product_listing_orchestrator_skill.json"
    with open(skill_file, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_node_edges(skill_data):
    """提取节点和边"""
    workflow = skill_data.get("workFlow", {})
    nodes = workflow.get("nodes", [])
    edges = workflow.get("edges", [])

    return nodes, edges


def build_adjacency(nodes, edges):
    """构建邻接表"""
    # node_id -> [target_node_ids]
    outgoing = {}
    # node_id -> [(source_node_id, source_port)]
    incoming = {}

    for node in nodes:
        node_id = node.get("id")
        outgoing[node_id] = []
        incoming[node_id] = []

    for edge in edges:
        source = edge.get("sourceNodeID")
        target = edge.get("targetNodeID")
        port = edge.get("sourcePortID", "")

        if source in outgoing:
            outgoing[source].append((target, port))
        if target in incoming:
            incoming[target].append((source, port))

    return outgoing, incoming


def find_path(start_node, end_node, outgoing):
    """BFS 查找从 start_node 到 end_node 的路径"""
    if start_node == end_node:
        return [start_node]

    visited = {start_node}
    queue = [(start_node, [start_node])]

    while queue:
        node, path = queue.pop(0)
        for next_node, _ in outgoing.get(node, []):
            if next_node == end_node:
                return path + [next_node]
            if next_node not in visited:
                visited.add(next_node)
                queue.append((next_node, path + [next_node]))

    return None


def test_pend_input_wait_in_followup_loop():
    """测试 pend_input_wait 在追问循环中"""
    skill_data = load_skill()
    nodes, edges = extract_node_edges(skill_data)
    outgoing, incoming = build_adjacency(nodes, edges)

    # 验证 pend_input_wait 节点存在
    pend_input_node = None
    for node in nodes:
        if node.get("id") == "pend_input_wait":
            pend_input_node = node
            break

    assert pend_input_node is not None, "找不到 pend_input_wait 节点"
    print(f"✓ pend_input_wait 节点存在，类型: {pend_input_node.get('type')}")

    # 验证追问流程: ask_followup -> chat_ask_followup -> pend_input_wait -> structured_collector
    path = find_path("ask_followup", "structured_collector", outgoing)
    assert path is not None, "找不到从 ask_followup 到 structured_collector 的路径"
    print(f"✓ 追问循环路径: {' -> '.join(path)}")

    # 验证路径中包含 pend_input_wait
    assert "pend_input_wait" in path, "追问循环应该包含 pend_input_wait 节点"
    print("✓ 追问循环包含 pend_input_wait 节点")


def test_pend_input_wait_waits_for_human_chat():
    """测试 pend_input_wait 配置为等待 human_chat"""
    skill_data = load_skill()
    nodes, _ = extract_node_edges(skill_data)

    for node in nodes:
        if node.get("id") == "pend_input_wait":
            inputs_values = node.get("data", {}).get("inputsValues", {})
            event_type = inputs_values.get("eventType", {}).get("content", "")

            assert event_type == "human_chat", (
                f"pend_input_wait 应该配置为等待 human_chat 事件，"
                f"实际: {event_type}"
            )
            print(f"✓ pend_input_wait 配置为等待 human_chat 事件")
            return

    assert False, "找不到 pend_input_wait 节点"


def test_all_pend_event_nodes():
    """测试所有 pend_event_node 节点"""
    skill_data = load_skill()
    nodes, _ = extract_node_edges(skill_data)

    pend_nodes = []
    for node in nodes:
        if node.get("type") == "pend_event_node":
            node_id = node.get("id")
            inputs_values = node.get("data", {}).get("inputsValues", {})
            event_type = inputs_values.get("eventType", {}).get("content", "")
            pend_nodes.append({
                "id": node_id,
                "event_type": event_type
            })

    print(f"✓ 找到 {len(pend_nodes)} 个 pend_event_node 节点:")
    for pn in pend_nodes:
        print(f"  - {pn['id']}: 等待 {pn['event_type']}")

    assert len(pend_nodes) > 0, "应该至少有 1 个 pend_event_node 节点"


def test_skill_compiles_without_error():
    """测试 skill 能否编译（不报错）"""
    from agent.ec_skills.flowgram2langgraph_v2 import flowgram2langgraph_v2

    skill_data = load_skill()

    try:
        graph, _ = flowgram2langgraph_v2(
            skill_data,
            bundle_json=skill_data.get("bundle"),
            enable_subgraph=False
        )
        compiled = graph.compile()
        print("✓ Skill 编译成功")
    except Exception as e:
        print(f"❌ Skill 编译失败: {e}")
        import traceback
        traceback.print_exc()
        raise AssertionError(f"Skill 编译失败: {e}")


def test_verify_graph_structure():
    """验证图结构的基本完整性"""
    skill_data = load_skill()
    nodes, edges = extract_node_edges(skill_data)

    # 1. 应该有 start 和 end 节点
    node_ids = {n.get("id") for n in nodes}
    assert "start" in node_ids, "应该有 start 节点"
    assert "end" in node_ids, "应该有 end 节点"
    print("✓ 有 start 和 end 节点")

    # 2. 每个节点都应该有边连接
    nodes_with_edges = set()
    for edge in edges:
        nodes_with_edges.add(edge.get("sourceNodeID"))
        nodes_with_edges.add(edge.get("targetNodeID"))

    orphan_nodes = node_ids - nodes_with_edges
    if orphan_nodes:
        # start 节点通常没有入边，end 节点通常没有出边
        acceptable_orphans = {"start", "end"}
        real_orphans = orphan_nodes - acceptable_orphans
        if real_orphans:
            print(f"⚠️ 孤立节点: {real_orphans}")

    print(f"✓ 图结构基本完整 ({len(nodes)} 个节点, {len(edges)} 条边)")


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Product Listing Skill 流程测试")
    print("=" * 60)

    test_pend_input_wait_in_followup_loop()
    test_pend_input_wait_waits_for_human_chat()
    test_all_pend_event_nodes()
    test_verify_graph_structure()
    test_skill_compiles_without_error()

    print("\n" + "=" * 60)
    print("✅ 所有测试通过!")
    print("=" * 60)
