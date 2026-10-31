"""One-character labels reach the model (拼多多 size picker S/M/L, KEN 2026-10-31)."""

from types import SimpleNamespace

from agent.ec_skills.browser_use_extension import short_label_patch as p


def test_one_character_visible_texts_are_marked_and_the_mark_is_invisible():
    from browser_use.dom.views import NodeType
    text = lambda v, vis=True: SimpleNamespace(node_type=NodeType.TEXT_NODE, node_value=v, is_visible=vis)
    m, xl, hidden = text("M"), text("XL"), text("S", vis=False)
    box = SimpleNamespace(node_type=NodeType.ELEMENT_NODE, children_nodes=[m, xl, hidden], shadow_roots=None,
                          content_document=None)
    assert p._mark_short_texts(box) == 1
    assert m.node_value == "M" + p._JOINER and len(m.node_value.strip()) == 2   # passes browser-use's > 1 test
    assert xl.node_value == "XL" and hidden.node_value == "S"


def test_the_patch_installs_and_the_writer_drops_the_mark():
    from browser_use.dom.serializer.serializer import DOMTreeSerializer
    assert p.install() and p.install()                                        # idempotent
    assert DOMTreeSerializer.serialize_tree(None, []) in ("", None)
