"""
Turn canonical records into retrievable chunks (docs/RAG_ENTERPRISE_PLAN.md §3.4).

Per product:
  summary     title + category + brand + key attributes + selling points
              (identifies the product when the buyer has no product card)
  faq         one chunk per Q/A; the question is embedded, the answer returned
  size_chart  text rendering of the size table
  text        description / care / attached-document text, split by paragraph

Per policy: one chunk per clause (paragraph).
Every chunk text starts with the product title so similar products stay
distinguishable (the sister-document lesson from rag_benchmark).
"""
from __future__ import annotations

from typing import Any, Dict, List

from knowledge.ks.text import POLICY_TOPIC_LABELS, clean_text, join_nonempty

MAX_CHARS = 500
OVERLAP = 60


def split_paragraphs(text: str, max_chars: int = MAX_CHARS) -> List[str]:
    """Split on blank lines / sentence ends, packing pieces up to max_chars."""
    text = clean_text(text)
    if not text:
        return []
    pieces: List[str] = []
    for para in [p.strip() for p in text.split("\n") if p.strip()]:
        while len(para) > max_chars:
            cut = max(para.rfind(sep, 0, max_chars) for sep in ("。", "；", "！", "？", ". ", "; "))
            cut = cut + 1 if cut > max_chars // 3 else max_chars
            pieces.append(para[:cut].strip())
            para = para[max(0, cut - OVERLAP if cut == max_chars else cut):].strip()
        if para:
            pieces.append(para)
    chunks: List[str] = []
    cur = ""
    for p in pieces:
        if cur and len(cur) + 1 + len(p) > max_chars:
            chunks.append(cur)
            cur = p
        else:
            cur = f"{cur}\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def render_size_chart(size_chart: Dict[str, Any]) -> str:
    headers = [str(h) for h in (size_chart or {}).get("headers") or []]
    rows = (size_chart or {}).get("rows") or []
    if not headers or not rows:
        return ""
    lines = []
    for row in rows:
        cells = [str(c) for c in row]
        pairs = [f"{h}{c}" if h.endswith(("：", ":")) else f"{h}:{c}" for h, c in zip(headers, cells) if str(c).strip()]
        lines.append("；".join(pairs))
    return "\n".join(lines)


def embed_text(doc_type: str, text: str, answer: str = "") -> str:
    """What gets embedded for a chunk. FAQ entries embed question + answer
    without the product title, so a paraphrased question still matches; the
    product scope comes from the filter, not from the vector."""
    if doc_type in ("faq", "attribute"):
        return f"{text.split('】', 1)[-1]}\n{answer}".strip()
    return text


def product_header(p: Dict[str, Any]) -> str:
    return f"【{p.get('title', '')}】"


def product_chunks(p: Dict[str, Any]) -> List[Dict[str, Any]]:
    head = product_header(p)
    attrs = p.get("attributes") or {}
    attr_text = "；".join(f"{k}:{v}" for k, v in attrs.items() if str(v).strip())
    summary = join_nonempty([
        head,
        join_nonempty([f"类目:{p.get('category')}" if p.get("category") else "",
                       f"品牌:{p.get('brand')}" if p.get("brand") else ""], "；"),
        attr_text,
        "卖点:" + "；".join(p.get("selling_points") or []) if p.get("selling_points") else "",
    ])
    out = [{"doc_type": "summary", "text": summary}]
    # One chunk per attribute so a question can match a fact by meaning
    # ("几岁能玩" -> 适用年龄), not only by the attribute's name.
    for k, v in attrs.items():
        if str(v).strip():
            out.append({"doc_type": "attribute", "text": f"{head}{k}:{v}", "answer": ""})
    for qa in p.get("faq") or []:
        q, a = clean_text(qa.get("q")), clean_text(qa.get("a"))
        if q and a:
            out.append({"doc_type": "faq", "text": f"{head}{q}", "answer": a})
    chart = render_size_chart(p.get("size_chart") or {})
    if chart:
        out.append({"doc_type": "size_chart", "text": f"{head}尺码表\n{chart}"})
    for part in split_paragraphs(p.get("description") or ""):
        out.append({"doc_type": "text", "text": f"{head}{part}"})
    if p.get("care"):
        out.append({"doc_type": "text", "text": f"{head}洗涤保养:{clean_text(p['care'])}"})
    # What the product's pictures show (product_images.describe): a buyer's photo,
    # described the same way, finds the same or a similar product by appearance.
    from knowledge.ks.product_images import looks_text
    looks = looks_text(p.get("images") or [])
    if looks:
        out.append({"doc_type": "appearance", "text": f"{head}{looks}"})
    return out


def document_chunks(title: str, text: str) -> List[Dict[str, Any]]:
    head = f"【{title}】" if title else ""
    return [{"doc_type": "text", "text": f"{head}{part}"} for part in split_paragraphs(text)]


def policy_chunks(topic: str, title: str, text: str) -> List[Dict[str, Any]]:
    label = title or POLICY_TOPIC_LABELS.get(topic, topic)
    return [{"doc_type": "policy", "text": f"【{label}】{part}"} for part in split_paragraphs(text)]
