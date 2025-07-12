import re
from collections import defaultdict

# =========================== ai generated dome tree code===========================================
def find_top_level_nodes(dom_json):
    # child_ids = set()
    # for key, val in dom_json["map"].items():
    #     child_ids.update(dom_json["map"][key].get("children", []))
    # top_level = [node_id for node_id in dom_json["map"].keys() if node_id not in child_ids]
    root_id = dom_json["rootId"]

    top_level = dom_json["map"][root_id]["children"]
    print(top_level)
    return top_level

def traverse_branch(dom_json, node_id, depth=0, max_depth=10):
    """Recursively traverse and yield node data up to max_depth."""
    if depth > max_depth:
        return
    node = dom_json[node_id]
    yield {
        "id": node_id,
        "tagName": node.get("tagName"),
        "attributes": node.get("attributes", {}),
        "text": node.get("text", ""),
        "type": node.get("type", ""),
        "xpath": node.get("xpath", ""),
        "isVisible": node.get("isVisible", None),
        "isInteractive": node.get("isInteractive", None),
        "children": node.get("children", [])
    }
    for child_id in node.get("children", []):
        yield from traverse_branch(dom_json, child_id, depth+1, max_depth)


def get_shallowest_texts(top_node_ids, dom_json):
    texts = {}
    node_map = dom_json["map"]

    for top_id in top_node_ids:
        queue = [[top_id]]  # List of node id lists; each inner list is one level
        found_texts = {}
        found = False

        while queue and not found:
            level = queue.pop(0)
            next_level = []
            for nid in level:
                node = node_map.get(nid, {})
                # TEXT_NODE: get 'text' directly
                if 'text' in node and node['text']:
                    found_texts[nid] = node['text']
                    found = True
                # Otherwise, queue children for next level
                if 'children' in node:
                    next_level.extend(node['children'])
            # If we found text(s) at this level, don't go deeper
            if found:
                texts.update(found_texts)
                break
            # If not, go to next level if there are nodes to check
            if next_level:
                queue.append(next_level)
    print("found texts:", texts)
    return texts

def collect_text_nodes_by_level(dom_json):
    node_map = dom_json["map"]
    root_id = dom_json["rootId"]
    levels = []  # Each entry: list of node ids with text at this depth

    # BFS queue: [(node_id, depth)]
    from collections import deque
    queue = deque([(root_id, 0)])

    while queue:
        node_id, depth = queue.popleft()
        node = node_map.get(node_id, {})

        # Extend the levels list if needed
        if len(levels) <= depth:
            levels.append([])

        # Check for text property
        if 'text' in node and node['text']:
            levels[depth].append(node_id)

        # Enqueue children (if any)
        for child_id in node.get('children', []):
            queue.append((child_id, depth + 1))

    return levels

def classify_node(node, keyword_map, semantic_sections, aria_roles):
    tag = node.get("tagName", "").lower()
    attrs = node.get("attributes", {})
    if tag in semantic_sections:
        return semantic_sections[tag]
    role = attrs.get("role", "").lower()
    for sec, roles in aria_roles.items():
        if role in roles:
            return sec
    class_id = (attrs.get("class", "") + " " + attrs.get("id", "")).strip().lower()
    for sec, pattern in keyword_map.items():
        if pattern.search(class_id):
            return sec
    return None

def sectionize_dt_with_subsections(dom_tree):
    dom_map = dom_tree["map"]
    root_id = str(dom_tree["rootId"])

    semantic_sections = {
        "header": "header",
        "nav": "nav",
        "main": "main",
        "aside": "aside",
        "footer": "footer",
        "section": "section",
        "article": "article"
    }
    keyword_map = {
        "header": re.compile(r"header|topbar|banner", re.I),
        "nav": re.compile(r"nav|menu|navigation", re.I),
        "main": re.compile(r"main|content|body", re.I),
        "aside": re.compile(r"aside|sidebar|side-nav|sidenav", re.I),
        "footer": re.compile(r"footer|bottom|copyright", re.I),
        "section": re.compile(r"section|block|panel", re.I),
        "article": re.compile(r"article|post|entry", re.I)
    }
    aria_roles = {
        "header": ["banner"],
        "nav": ["navigation"],
        "main": ["main"],
        "footer": ["contentinfo"]
    }

    def recurse_section(node_id, parent_section=None):
        node = dom_map[node_id]
        this_section = classify_node(node, keyword_map, semantic_sections, aria_roles)

        result = None
        if this_section and this_section != parent_section:
            # This node is a (sub)section
            result = {
                'type': this_section,
                'node_id': node_id,
                'children': []
            }
            # Only look for sub-sections inside this section
            for cid in node.get("children", []):
                subsec = recurse_section(cid, parent_section=this_section)
                if subsec:
                    result['children'].append(subsec)
            return result
        else:
            # Not a new section: look for (sub)sections inside children
            sub_sections = []
            for cid in node.get("children", []):
                subsec = recurse_section(cid, parent_section=parent_section)
                if subsec:
                    sub_sections.append(subsec)
            # Only return list if non-empty and at least one is a section
            if sub_sections:
                return sub_sections if len(sub_sections) > 1 else sub_sections[0]
            else:
                return None

    # Traverse from root
    all_sections = []
    for cid in dom_map[root_id].get("children", []):
        s = recurse_section(cid, parent_section=None)
        if s:
            all_sections.append(s)
    return all_sections

def extract_elements(node_id, dom_map, interesting_tags=None, max_depth=None, _depth=0):
    """
    Recursively extract interesting elements (table, list, heading, p, etc.)
    from a subtree rooted at node_id in dom_map.

    Returns a list of dicts with keys: type, tag, node_id, text, attrs, children
    """
    if interesting_tags is None:
        interesting_tags = {"table", "thead", "tbody", "tr", "th", "td",
                            "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
                            "p", "img", "a", "form", "button"}
    if max_depth is not None and _depth > max_depth:
        return []

    node = dom_map[node_id]
    results = []
    tag = node.get("tagName", "").lower()
    node_type = node.get("type", None)
    node_text = node.get("text", None)

    # If this is a text node directly under an interesting element, treat specially
    if node_type == "TEXT_NODE" and node_text and node.get("isVisible", True):
        return [{"type": "text", "node_id": node_id, "text": node_text.strip()}]

    # If this is an interesting tag, start a new branch
    if tag in interesting_tags:
        children = []
        for cid in node.get("children", []):
            children += extract_elements(cid, dom_map, interesting_tags, max_depth, _depth=_depth+1)
        results.append({
            "type": tag,
            "node_id": node_id,
            "text": node_text.strip() if node_text else "",
            "attrs": node.get("attributes", {}),
            "children": children
        })
    else:
        # Not an interesting tag, but see if its children contain interesting nodes
        for cid in node.get("children", []):
            results += extract_elements(cid, dom_map, interesting_tags, max_depth, _depth=_depth+1)

    return results

# ================================end of ai generated code==============================
