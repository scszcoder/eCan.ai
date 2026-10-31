"""Let the model see one-character labels (S, M, L, 是, 否, single digits).

browser-use's DOM serializer drops every visible text node whose stripped text is
one character long (``len(text.strip()) > 1``, twice: when it builds the simplified
tree and when it writes the text out; 0.12.2 and 0.12.5). On 拼多多's size picker
the checkboxes S, M and L were therefore invisible while XS, XL and 2XL showed
(KEN 2026-10-31, runs 58/60): the agent hunted for sizes it could not see.

The serializer is only bytecode in the frozen app, so its methods cannot be
rewritten. Instead, before it runs, a one-character visible text gets an invisible
WORD JOINER appended (it then passes the length test), and the joiner is removed
again from the text the model is given. The page itself is never touched; only
browser-use's copy of the DOM.
"""
from __future__ import annotations

from utils.logger_helper import logger_helper as logger

_JOINER = "⁠"
_installed = False


def _mark_short_texts(root) -> int:
    """Append the joiner to visible one-character text nodes under *root*."""
    try:
        from browser_use.dom.views import NodeType
    except Exception:
        return 0
    marked, stack, seen = 0, [root], set()
    while stack:
        node = stack.pop()
        if node is None or id(node) in seen:
            continue
        seen.add(id(node))
        if getattr(node, "node_type", None) == NodeType.TEXT_NODE:
            value = getattr(node, "node_value", "") or ""
            if len(value.strip()) == 1 and getattr(node, "is_visible", False):
                node.node_value = value.strip() + _JOINER
                marked += 1
            continue
        stack.extend(getattr(node, "children_nodes", None) or [])
        stack.extend(getattr(node, "shadow_roots", None) or [])
        doc = getattr(node, "content_document", None)
        if doc is not None:
            stack.append(doc)
    return marked


def install() -> bool:
    """Patch browser-use's DOMTreeSerializer once. False when it is not importable."""
    global _installed
    if _installed:
        return True
    try:
        from browser_use.dom.serializer.serializer import DOMTreeSerializer
    except Exception as exc:
        logger.warning(f"[short-label-patch] browser-use serializer not importable: {exc}")
        return False
    original_init = DOMTreeSerializer.__init__
    original_tree = DOMTreeSerializer.serialize_tree

    def __init__(self, root_node, *args, **kwargs):
        try:
            _mark_short_texts(root_node)
        except Exception as exc:          # never break DOM extraction
            logger.debug(f"[short-label-patch] marking skipped: {exc}")
        original_init(self, root_node, *args, **kwargs)

    def serialize_tree(node, include_attributes, depth=0):
        text = original_tree(node, include_attributes, depth)
        return text.replace(_JOINER, "") if text else text

    DOMTreeSerializer.__init__ = __init__
    DOMTreeSerializer.serialize_tree = staticmethod(serialize_tree)
    _installed = True
    logger.info("[short-label-patch] one-character labels are kept in the DOM the model sees")
    return True
