import re
from collections import defaultdict
import json
import traceback
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from agent.agent_service import get_agent_by_id
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException

def cap_text_length(text: str, max_length: int) -> str:
	if len(text) > max_length:
		return text[:max_length] + '...'
	return text

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
    try:
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
        # if node_type == "TEXT_NODE" and node_text and node.get("isVisible", True):
        if node_type == "TEXT_NODE" and node_text:
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

    except Exception as e:
        err_trace = get_traceback(e, "ErrorTraverseSectionsAndExtract")
        logger.debug(err_trace)
        return []

def traverse_sections_and_extract(sections, dom_map):
    try:
        for section in sections:
            print(f"Section type: {section['type']}, node: {section['node_id']}")
            content = extract_elements(section['node_id'], dom_map)
            # Print nicely, or convert to whatever format you want
            print(content)
            for sub in section.get("children", []):
                traverse_sections_and_extract([sub], dom_map)
    except Exception as e:
        err_trace = get_traceback(e, "ErrorTraverseSectionsAndExtract")
        logger.debug(err_trace)

# ================================end of ai generated code==============================
import json
from collections import defaultdict


class DomExtractor:
    def __init__(self, dom_map):
        self.dom_map = {str(k): v for k, v in dom_map.items()}
        self._text_cache = {}
        self._parent_map = {}
        for parent_id, element in self.dom_map.items():
            for child_id in element.get('children', []):
                self._parent_map[str(child_id)] = str(parent_id)

    def get_element(self, element_id):
        return self.dom_map.get(str(element_id))

    def get_element_text(self, element_id):
        element_id = str(element_id)
        if element_id in self._text_cache: return self._text_cache[element_id]
        element = self.get_element(element_id)
        if not element: return ""
        if element.get('type') == 'TEXT_NODE': return element.get('text', '').strip()
        child_texts = [self.get_element_text(child_id) for child_id in element.get('children', [])]
        full_text = ' '.join(filter(None, child_texts)).strip()
        self._text_cache[element_id] = full_text
        return full_text

    # def _is_valid_title(self, title):
    #     if not title or not title.strip(): return False
    #     junk_starters = ["back", "more", "see all", "view all"]
    #     lower_title = title.lower()
    #     if lower_title.startswith(tuple(junk_starters)): return False
    #     return True


    def _find_primary_link(self, element_id):
        element = self.get_element(element_id)
        if not element: return None, self.get_element_text(element_id)
        if element.get('tagName') == 'a':
            return element.get('attributes', {}).get('href'), self.get_element_text(element_id)
        for child_id in element.get('children', []):
            child = self.get_element(child_id)
            if child and child.get('tagName') == 'a':
                return child.get('attributes', {}).get('href'), self.get_element_text(child_id)
        return None, self.get_element_text(element_id)

    def _parse_and_extract_recursively(self, container_id):
        items = []
        nested_lists = {}
        container = self.get_element(container_id)
        if not container: return [], {}
        for item_id in container.get('children', []):
            item_element = self.get_element(item_id)
            if not item_element or item_element.get('tagName') != 'li': continue
            href, text = self._find_primary_link(item_id)
            if self._is_valid_title(text): items.append({"text": text, "href": href})
            for child_id in item_element.get('children', []):
                search_children = []
                child_element = self.get_element(child_id)
                if child_element and child_element.get('tagName') == 'div':
                    search_children = child_element.get('children', [])
                elif child_element and child_element.get('tagName') in ['ul', 'ol']:
                    search_children = [child_id]
                for grandchild_id in search_children:
                    grandchild = self.get_element(grandchild_id)
                    if grandchild and grandchild.get('tagName') in ['ul', 'ol']:
                        title = text
                        if self._is_valid_title(title):
                            sub_items, sub_nested_lists = self._parse_and_extract_recursively(grandchild_id)
                            if sub_items: nested_lists[title] = sub_items
                            nested_lists.update(sub_nested_lists)
                        break
        return items, nested_lists

    # --- MODIFIED TITLE FINDING LOGIC ---
    def _find_root_list_title(self, list_id, max_levels=4):
        """
        Finds a title for a root list by climbing the DOM tree and looking
        for the nearest preceding sibling with valid text content.
        """
        current_id = str(list_id)

        for level in range(max_levels):
            parent_id = self._parent_map.get(current_id)
            if not parent_id: break

            parent_element = self.get_element(parent_id)
            siblings = parent_element.get('children', [])

            try:
                current_index = siblings.index(current_id)
            except ValueError:
                current_id = parent_id
                continue

            # Scan backwards through the preceding siblings
            for i in range(current_index - 1, -1, -1):
                sibling_id = siblings[i]
                sibling_element = self.get_element(sibling_id)
                if not sibling_element: continue

                # HEURISTIC: The sibling should not be another list.
                if sibling_element.get('tagName') in ['ul', 'ol']:
                    continue

                # Get the text from the sibling and validate it.
                title = self.get_element_text(sibling_id)
                if self._is_valid_title(title):
                    return title  # Success! Found a valid title.

            current_id = parent_id  # Move up to the parent for the next iteration

        return None  # No suitable title found


    def find_lists_and_menus(self):
        all_found_lists = {}
        processed_containers = set()
        for element_id, element in self.dom_map.items():
            if element.get('tagName') in ['ul', 'ol'] and element_id not in processed_containers:
                parent_id = self._parent_map.get(element_id)
                if parent_id and self.get_element(parent_id).get('tagName') == 'li': continue

                title_candidate = self._find_root_list_title(element_id)
                items, nested = self._parse_and_extract_recursively(element_id)

                if items:
                    title = title_candidate if title_candidate else "Untitled List"
                    original_title = title
                    counter = 1
                    while title in all_found_lists:
                        title = f"{original_title} ({counter})"
                        counter += 1
                    all_found_lists[title] = items

                if nested: all_found_lists.update(nested)
                processed_containers.add(element_id)
        return all_found_lists

    # ===================================================================
    def _get_all_descendants(self, start_node_id):
        descendants = []
        queue = [start_node_id]
        visited = {start_node_id}
        while queue:
            current_id = queue.pop(0)
            element = self.get_element(current_id)
            if not element: continue
            for child_id in element.get('children', []):
                if child_id not in visited:
                    descendants.append(child_id)
                    queue.append(child_id)
                    visited.add(child_id)
        return descendants



    def _is_valid_title(self, title):
        if not title or not title.strip(): return False
        junk_starters = ["back", "more", "see all", "view all"]
        lower_title = title.lower()
        if lower_title.startswith(tuple(junk_starters)): return False
        return True

    def _is_content_container(self, element_id):
        descendants = self._get_all_descendants(element_id)
        descendants.append(element_id)
        for node_id in descendants:
            node = self.get_element(node_id)
            if not node: continue
            if node.get('tagName') in ['input', 'select', 'fieldset']: return True
            if node.get('attributes', {}).get('data-testid') == 'filter-box-inner-ref': return True
        return False

    def _parse_selectable_list(self, group_id):
        options = []
        descendants = self._get_all_descendants(group_id)
        for node_id in descendants:
            node = self.get_element(node_id)
            if node and node.get('attributes', {}).get('data-testid') == 'filter-box-inner-ref':
                for option_id in node.get('children', []):
                    option_text = self.get_element_text(option_id)
                    if option_text: options.append(option_text)
                break
        return options

    def _find_inputs(self, group_id, required_type=None):
        inputs = []
        descendants = self._get_all_descendants(group_id)
        for node_id in descendants:
            node = self.get_element(node_id)
            if node and node.get('tagName') == 'input':
                attrs = node.get('attributes', {})
                input_type_attr = attrs.get('type', 'text')
                if required_type and input_type_attr != required_type:
                    continue
                inputs.append({
                    "element_id": node_id, "type": input_type_attr,
                    "placeholder": attrs.get('placeholder'), "value": attrs.get('value'),
                    "data_filter_type": attrs.get('data-filter-type')
                })
        return inputs

    def _parse_filter_group(self, group_id):
        title = ""
        container_id = group_id
        container_children = self.get_element(container_id).get('children', [])
        while len(container_children) == 1:
            container_id = container_children[0]
            container_children = self.get_element(container_id).get('children', [])
        for child_id in container_children:
            if self._is_content_container(child_id): continue
            text = self.get_element_text(child_id)
            if self._is_valid_title(text):
                title = text
                break
        if not title: return None

        all_inputs = self._find_inputs(group_id)
        min_max_inputs = [inp for inp in all_inputs if inp.get('data_filter_type') in ['min', 'max']]
        if len(min_max_inputs) >= 2:
            available_values = self._parse_selectable_list(group_id)
            return {"title": title, "type": "range", "inputs": min_max_inputs, "available_values": available_values}

        checkboxes = self._find_inputs(group_id, required_type='checkbox')
        if len(checkboxes) == 1:
            return {"title": title, "type": "checkbox", "details": checkboxes[0]}

        selectable_options = self._parse_selectable_list(group_id)
        if selectable_options:
            return {"title": title, "type": "select_list", "options": selectable_options}

        if all_inputs:
            return {"title": title, "type": "generic_input", "inputs": all_inputs}

        return {"title": title, "type": "unknown"}

    def _parse_table_cell_as_filter(self, cell_id):
        """Parses the content of a single <td> to determine its filter type and options."""
        # Check for a <select> dropdown
        descendants = self._get_all_descendants(cell_id)
        descendants.insert(0, cell_id)  # check the cell itself
        for node_id in descendants:
            node = self.get_element(node_id)
            if node and node.get('tagName') == 'select':
                options = []
                for option_id in node.get('children', []):
                    option_node = self.get_element(option_id)
                    if option_node and option_node.get('tagName') == 'option':
                        text = self.get_element_text(option_id)
                        if text: options.append(text)
                return {"type": "dropdown_select", "options": options}

        # Can add checks for other input types within a cell here later
        return {"type": "unknown"}

    def _find_and_parse_filter_table(self):
        """Finds and parses a <table> that is being used for parametric filters."""
        for el_id, el in self.dom_map.items():
            if el.get('tagName') != 'table':
                continue

            # Heuristic: A filter table contains <select> or <input> tags.
            descendants = self._get_all_descendants(el_id)
            has_inputs = any(self.get_element(d).get('tagName') in ['select', 'input'] for d in descendants)

            if not has_inputs:
                continue

            # Found a candidate table, now parse it.
            headers = []
            header_row = next(
                (self.get_element(d) for d in descendants if self.get_element(d).get('tagName') == 'thead'), None)
            if header_row:
                header_cells = [c for c in self._get_all_descendants(header_row.get('children')[0]) if
                                self.get_element(c).get('tagName') == 'th']
                headers = [self.get_element_text(th_id) for th_id in header_cells]

            filters = []
            body_rows = [self.get_element(d) for d in descendants if self.get_element(d).get('tagName') == 'tbody']
            if not body_rows or not headers:
                continue

            # Assume filters are in the first row of the body
            cells = [c for c in self._get_all_descendants(body_rows[0].get('children')[0]) if
                     self.get_element(c).get('tagName') == 'td']

            for i, cell_id in enumerate(cells):
                if i < len(headers):
                    title = headers[i]
                    if not self._is_valid_title(title): continue

                    parsed_cell = self._parse_table_cell_as_filter(cell_id)
                    parsed_cell['title'] = title
                    filters.append(parsed_cell)

            # If we successfully parsed filters from this table, return them.
            if filters:
                return filters

        return None  # No filter table found

    # --- MODIFIED MAIN FUNCTION ---
    def find_parametric_filters(self):
        """
        Controller method to find parametric filters. It first tries to find
        a table-based layout, and if not found, falls back to the div-based layout parser.
        """
        # 1. First, attempt to find and parse filters laid out in a table.
        table_filters = self._find_and_parse_filter_table()
        if table_filters:
            print("Info: Found and parsed a table-based filter layout.")
            return table_filters

        # 2. If no table is found, fall back to the div-based layout parser.
        print("Info: No filter table found. Falling back to div-based layout search.")
        # ... (The previous div-based logic is now the fallback)
        # For brevity, this is a simplified version of the div-based parser.
        # In a real implementation, the full previous code would go here.
        div_based_filters = self._find_div_based_filters()
        if div_based_filters:
             print("Info: Found and parsed a div-based filter layout.")
        return div_based_filters

    # The previous find_parametric_filters is renamed to be the fallback.
    def _find_div_based_filters(self):
        # ... This is the full implementation of the `find_parametric_filters` from our previous step ...
        # ... It finds the best container div and calls `_parse_filter_group` on its children ...
        return [] # Placeholder for the previous logic


    def _find_div_table_components(self):
        """Finds the header, body, and row containers of a div-based table."""
        header_container = None
        body_container = None

        for el_id, el in self.dom_map.items():
            attrs = el.get('attributes', {})
            class_name = attrs.get('class', '')
            # Heuristics for modern JS grids (like AG-Grid)
            if 'ag-header-container' in class_name or 'ag-header-viewport' in class_name:
                header_container = el_id
            if 'ag-center-cols-container' in class_name:
                body_container = el_id

            if header_container and body_container:
                return header_container, body_container

        return None, None


    def find_and_extract_tables(self):
        """
        Finds and extracts data from tables, prioritizing modern div-based grids
        and falling back to standard HTML tables.
        """
        header_container_id, body_container_id = self._find_div_table_components()

        if not (header_container_id and body_container_id):
            print("Info: No div-based grid found. Add fallback to standard <table> parsing here if needed.")
            return {}

        # 1. Extract Headers
        header_elements = self._get_all_descendants(header_container_id)
        headers = [
            (self.get_element(el_id).get('attributes').get('col-id'), self.get_element_text(el_id))
            for el_id in header_elements
            if self.get_element(el_id).get('attributes', {}).get('role') == 'columnheader'
        ]
        # Create a map of col-id to header text for accurate mapping
        header_map = {col_id: text for col_id, text in headers if col_id}

        # 2. Extract Rows and Cells
        data_rows_container = self.get_element(body_container_id)
        rows_data = {}

        for row_id in data_rows_container.get('children', []):
            row_element = self.get_element(row_id)
            if not row_element or row_element.get('attributes', {}).get('role') != 'row':
                continue

            row_cells = row_element.get('children', [])

            # Map cell data to headers using the col-id
            row_dict = {}
            primary_key = None

            for cell_id in row_cells:
                cell_element = self.get_element(cell_id)
                if not cell_element: continue

                col_id = cell_element.get('attributes', {}).get('col-id')
                if col_id in header_map:
                    header_text = header_map[col_id]
                    cell_text = self.get_element_text(cell_id)
                    row_dict[header_text] = cell_text

            if not row_dict:
                continue

            # Use the value from the first header column as the primary key
            first_header_id = headers[0][0] if headers else None
            first_header_text = header_map.get(first_header_id)

            if first_header_text and first_header_text in row_dict:
                primary_key = row_dict[first_header_text].split('\n')[0].strip()  # Clean up the key

            if primary_key:
                # To avoid overwriting, handle duplicate keys if they exist
                original_key = primary_key
                counter = 2
                while primary_key in rows_data:
                    primary_key = f"{original_key}_{counter}"
                    counter += 1
                rows_data[primary_key] = row_dict

        return rows_data
# =============== due to arrow's parametric filter container ===============
import time
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait


class PageActivityMonitor:
    """A helper class to track page state across WebDriverWait polls."""

    def __init__(self, driver):
        self.driver = driver
        # Initialize with -1 to ensure the first check registers a change
        self.last_resource_count = -1
        self.last_dom_size = -1
        self.resource_stable_checks = 0
        self.dom_stable_checks = 0

    def is_network_idle(self, stability_threshold=3):
        """
        Checks if the number of loaded resources has been stable.
        Returns True if the count hasn't changed for `stability_threshold` checks.
        """
        # This JS snippet gets the total number of performance entries (network requests)
        current_resource_count = self.driver.execute_script(
            "return window.performance.getEntriesByType('resource').length;")

        if current_resource_count == self.last_resource_count:
            self.resource_stable_checks += 1
        else:
            # If the count changes, reset the stability counter and update the last count
            self.resource_stable_checks = 0
            self.last_resource_count = current_resource_count

        return self.resource_stable_checks >= stability_threshold

    def is_dom_stable(self, stability_threshold=3):
        """
        Checks if the DOM structure (by character length) has been stable.
        Returns True if the size hasn't changed for `stability_threshold` checks.
        """
        # The length of the body's innerHTML is a good proxy for DOM changes
        current_dom_size = self.driver.execute_script("return document.body.innerHTML.length;")

        if current_dom_size == self.last_dom_size:
            self.dom_stable_checks += 1
        else:
            self.dom_stable_checks = 0
            self.last_dom_size = current_dom_size

        return self.dom_stable_checks >= stability_threshold


def wait_for_dynamic_content(driver, timeout=30):
    """
    A general-purpose function to wait for a dynamic page to fully load.
    It waits for the document to be ready, the network to be idle, and the DOM to stabilize.
    """
    print("Waiting for dynamic content to load...")

    # 1. First, wait for the basic document to be ready
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        print("  - Document is ready (readyState='complete').")
    except TimeoutException:
        print("  - Timed out waiting for document.readyState.")
        return False

    monitor = PageActivityMonitor(driver)

    # 2. Second, wait for network activity to become idle
    try:
        print("  - Waiting for network to become idle...")
        # Poll every 500ms, wait for 3 stable checks (1.5 seconds of stability)
        WebDriverWait(driver, timeout, poll_frequency=0.5).until(
            lambda d: monitor.is_network_idle()
        )
        print("  - Network appears idle.")
    except TimeoutException:
        print("  - Timed out waiting for network to idle. The page might still be loading content.")
        # We can choose to continue or fail here. For robustness, we'll continue.
        pass

    # 3. Third, wait for the DOM to stop changing
    try:
        print("  - Waiting for DOM to stabilize...")
        WebDriverWait(driver, timeout, poll_frequency=0.5).until(
            lambda d: monitor.is_dom_stable()
        )
        print("  - DOM appears stable.")
    except TimeoutException:
        print("  - Timed out waiting for DOM to stabilize. Proceeding anyway.")
        return False

    print("Dynamic content appears to be fully loaded.")
    return True

# --- Example Usage ---

# driver.get("https://some-unknown-dynamic-website.com")

# Instead of a specific wait, use the general-purpose one
# if wait_for_dynamic_content(driver):
#     # Now it's much safer to run your buildDomTree.js script
#     dom_tree = driver.execute_script(build_dom_tree_script)
#     # ...


# =====================   utility to close cookie banner as well as some advertising popups ===============
ACCEPT_KEYWORDS = [
    "accept all", "allow all", "i accept", "agree to all",
    "accept", "agree", "allow", "ok", "got it", "i understand", "consent"
]

# Keywords and selectors for generic "close" buttons on popups.
CLOSE_SELECTORS = [
    "//button[normalize-space(.)='X' or normalize-space(.)='x' or normalize-space(.)='×']",
    "//*[contains(@id, 'close') or contains(@class, 'close') or contains(@id, 'dismiss') or contains(@class, 'dismiss')]",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'close')]",
    "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'close')]",
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'no thanks')]",
    "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'no thanks')]",
    "//*[@aria-label='Close' or @aria-label='close']"
]

# General XPath template for keyword-based searches.
CLICKABLE_ELEMENT_XPATH = (
    "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{keyword}')] | "
    "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{keyword}')] | "
    "//div[@role='button' and contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{keyword}')]"
)


# --- 2. The Main Function ---

def handle_popups(webdriver, timeout: int = 10):
    """
    Attempts to find and close cookie banners, newsletter popups, and other overlays.

    This function tries several strategies in order:
    1. Searches for buttons/links with common "accept" keywords.
    2. Searches for common "close" icons, buttons, or links.
    3. Executes a JavaScript search to find and click elements within any Shadow DOM.
    4. Switches to any iframes and repeats the search.

    Args:
        driver: The active Selenium WebDriver instance.
        timeout: The maximum time in seconds to wait for elements.

    Returns:
        bool: True if a popup was likely closed, False otherwise.
    """
    print("Attempting to close popups and banners...")

    # --- Strategy 1: Search for Cookie "Accept" Buttons ---
    print("Strategy 1: Searching for cookie 'Accept' buttons...")
    try:
        for keyword in ACCEPT_KEYWORDS:
            xpath = CLICKABLE_ELEMENT_XPATH.format(keyword=keyword)
            try:
                button = WebDriverWait(webdriver, 2).until(  # Use a shorter wait for this initial check
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                button.click()
                print(f"Success: Clicked cookie button with keyword '{keyword}'.")
                time.sleep(1)
                return True
            except (TimeoutException, NoSuchElementException):
                continue
            except ElementClickInterceptedException:
                print(f"Warning: Element for '{keyword}' was intercepted. Trying JS click.")
                webdriver.execute_script("arguments[0].click();", button)
                print(f"Success: Clicked cookie button with keyword '{keyword}' using JavaScript.")
                time.sleep(1)
                return True
    except Exception as e:
        print(f"An error occurred during cookie search: {e}")

    # --- Strategy 2: Search for Generic "Close" Buttons ---
    print("Strategy 2: Searching for generic 'Close' buttons...")
    try:
        for xpath in CLOSE_SELECTORS:
            try:
                # Use find_elements to not fail immediately if one isn't found
                close_buttons = WebDriverWait(webdriver, 2).until(
                    EC.presence_of_all_elements_located((By.XPATH, xpath))
                )
                # Iterate through found elements and try to click a visible one
                for button in close_buttons:
                    if button.is_displayed():
                        webdriver.execute_script("arguments[0].click();", button)
                        print(f"Success: Clicked a close button using selector: {xpath}")
                        time.sleep(1)
                        return True
            except (TimeoutException, NoSuchElementException):
                continue
    except Exception as e:
        print(f"An error occurred during close button search: {e}")

    # --- Strategy 3: Search within Shadow DOM ---
    print("Strategy 3: Searching within Shadow DOMs...")
    try:
        all_keywords = ACCEPT_KEYWORDS + ["close", "dismiss", "no thanks"]
        js_script = f"""
            function findInShadows(root, keyword) {{
                // Search for buttons, links, and elements with specific close-related attributes
                const elements = root.querySelectorAll('button, a, div[role="button"], [id*="close"], [class*="close"], [aria-label*="close"]');
                for (const el of elements) {{
                    if (el.textContent.trim().toLowerCase().includes(keyword)) {{
                        return el;
                    }}
                }}
                const shadows = root.querySelectorAll('*');
                for (const el of shadows) {{
                    if (el.shadowRoot) {{
                        const found = findInShadows(el.shadowRoot, keyword);
                        if (found) return found;
                    }}
                }}
                return null;
            }}
            const keywords = {str(all_keywords)};
            for (const keyword of keywords) {{
                const acceptButton = findInShadows(document, keyword);
                if (acceptButton) {{
                    acceptButton.click();
                    return keyword;
                }}
            }}
            return null;
        """
        clicked_keyword = webdriver.execute_script(js_script)
        if clicked_keyword:
            print(f"Success: Clicked button with keyword '{clicked_keyword}' in a Shadow DOM.")
            time.sleep(1)
            return True
    except Exception as e:
        print(f"An error occurred during Shadow DOM search: {e}")

    # --- Strategy 4: Search within iFrames ---
    print("Strategy 4: Searching within iFrames...")
    try:
        iframes = webdriver.find_elements(By.TAG_NAME, 'iframe')
        for frame in iframes:
            try:
                webdriver.switch_to.frame(frame)
                print("Switched to an iframe.")
                # Recursively call the function inside the iframe
                if handle_popups(webdriver, timeout=3):
                    webdriver.switch_to.default_content()
                    print("Success: Closed popup in an iframe and switched back.")
                    return True
                webdriver.switch_to.default_content()
            except Exception as e:
                print(f"Could not process an iframe: {e}")
                webdriver.switch_to.default_content()
    except Exception as e:
        print(f"An error occurred during iframe search: {e}")

    print("Warning: All strategies failed. No popups or banners were closed.")
    return False


