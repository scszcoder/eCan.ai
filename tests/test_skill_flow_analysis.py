#!/usr/bin/env python3
"""Analyze skill flow to find where raw JSON might be displayed."""

import json
import sys
sys.path.insert(0, '/Users/liuqiang/WorkSpace/ecan/eCan.ai')

with open('/Users/liuqiang/WorkSpace/ecan/eCan.ai/my_skills/product_listing_orchestrator_skill/diagram_dir/product_listing_orchestrator_skill.json', 'r') as f:
    skill = json.load(f)

nodes = skill['workFlow']['nodes']
edges = skill['workFlow']['edges']

print("=" * 70)
print("SKILL FLOW ANALYSIS: product_listing_orchestrator")
print("=" * 70)

# Build node map
node_map = {n['id']: n for n in nodes}

# Analyze edges
print("\n1. FLOW EDGES (connections):")
for i, edge in enumerate(edges):
    src = edge.get('sourceNodeID', '?')
    tgt = edge.get('targetNodeID', '?')
    port = edge.get('sourcePortID', '')
    port_str = f" [{port}]" if port else ""
    print(f"   {i+1}. {src} --> {tgt}{port_str}")

# Find all chat_node types
print("\n2. CHAT NODES (these send messages to UI):")
for node in nodes:
    if node.get('type') == 'chat_node':
        node_id = node['id']
        title = node['data'].get('title', '')
        msg_tpl = ""
        try:
            inputs = node['data'].get('inputsValues', {})
            msg_tpl = inputs.get('messageTemplate', {}).get('content', '') or inputs.get('message', '')
        except:
            pass
        print(f"   - {node_id}: '{title}'")
        print(f"     Template: {msg_tpl[:100]}..." if len(msg_tpl) > 100 else f"     Template: {msg_tpl}")

# Find all LLM nodes and check if any have direct message output
print("\n3. LLM NODES (check output format):")
llm_nodes = [n for n in nodes if n.get('type') == 'llm']
for node in llm_nodes[:5]:  # Show first 5
    node_id = node['id']
    title = node['data'].get('title', '')
    print(f"   - {node_id}: '{title}'")

print(f"   ... and {len(llm_nodes) - 5} more LLM nodes")

# Check for any node that might output raw LLM result
print("\n4. NODES WITH TEMPLATE MESSAGES:")
for node in nodes:
    try:
        inputs = node['data'].get('inputsValues', {})
        msg = inputs.get('messageTemplate', {}).get('content', '') or inputs.get('message', '')
        if msg and '{{' in msg:
            print(f"   - {node['id']}: Uses template variable")
            print(f"     Template: {msg[:150]}...")
    except:
        pass

# Check where skill execution ends
print("\n5. END NODES:")
for node in nodes:
    if node.get('type') == 'end':
        print(f"   - {node['id']}")

print("\n" + "=" * 70)
print("Analysis complete")
print("=" * 70)
