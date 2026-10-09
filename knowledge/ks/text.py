"""
Text utilities: cleaning, tokenizing (Chinese + ASCII) and question topics.

No external tokenizer: Chinese is split into character unigrams and bigrams,
which is what keyword search needs for exact product terms (面料, 尺码, 型号)
without shipping a dictionary.
"""
from __future__ import annotations

import html
import re
import unicodedata
from typing import Dict, Iterable, List, Optional

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_TAG_RE = re.compile(r"<\s*(?:br|/p|/div|/li|/tr|/h[1-6])\s*/?\s*>", re.I)
# Full-width ASCII letters/digits -> ASCII. Chinese punctuation (，：；) is kept.
_FULLWIDTH_ALNUM = {c: c - 0xFEE0 for r in ((0xFF10, 0xFF19), (0xFF21, 0xFF3A), (0xFF41, 0xFF5A))
                    for c in range(r[0], r[1] + 1)}
_WS_RE = re.compile(r"[ \t　\xa0]+")
_ASCII_RE = re.compile(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*")
_CJK_RE = re.compile(r"[一-鿿]+")

# Function words that carry no retrieval signal.
_STOP_UNIGRAMS = set("的了吗呢吧啊呀么是在有和与或就也都这那个么我你他她它们请问下一")
_STOP_BIGRAMS = {"请问", "一下", "这个", "那个", "什么", "怎么", "可以", "有没", "没有", "是不", "不是", "你们", "我们", "亲亲", "在吗"}
_STOP_ASCII = {"the", "a", "an", "is", "are", "of", "to", "and", "or", "in", "on", "for", "do", "does", "it", "this", "what", "how"}


def signal_terms(tokens: List[str]) -> List[str]:
    """Distinctive query terms: CJK bigrams and ASCII words (not single chars)."""
    return [t for t in dict.fromkeys(tokens) if len(t) > 1]


def clean_text(value: object) -> str:
    """Strip HTML, normalise full-width characters and collapse whitespace."""
    if value is None:
        return ""
    s = str(value)
    if "<" in s and ">" in s:
        s = _BLOCK_TAG_RE.sub("\n", s)
        s = _TAG_RE.sub("", s)
    s = html.unescape(s)
    s = s.translate(_FULLWIDTH_ALNUM)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(_WS_RE.sub(" ", line).strip() for line in s.split("\n"))
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def tokenize(text: str) -> List[str]:
    """Tokens for keyword search: ASCII words/numbers plus CJK uni+bigrams."""
    if not text:
        return []
    s = unicodedata.normalize("NFKC", text).lower()
    tokens: List[str] = []
    for word in _ASCII_RE.findall(s):
        if word not in _STOP_ASCII:
            tokens.append(word)
    for run in _CJK_RE.findall(s):
        for ch in run:
            if ch not in _STOP_UNIGRAMS:
                tokens.append(ch)
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            # Bigrams straddling a function word (麻的, 有亚) are noise.
            if bg not in _STOP_BIGRAMS and bg[0] not in _STOP_UNIGRAMS and bg[1] not in _STOP_UNIGRAMS:
                tokens.append(bg)
    return tokens


# Policy topics and the words buyers use for them.
POLICY_TOPICS: Dict[str, List[str]] = {
    "returns": ["退货", "退款", "换货", "七天无理由", "7天无理由", "退换", "return", "refund", "exchange"],
    "shipping": ["发货", "快递", "物流", "几天到", "包邮", "运费", "什么时候到", "配送", "shipping", "delivery", "ship"],
    "invoice": ["发票", "开票", "invoice"],
    "after_sales": ["售后", "保修", "质保", "维修", "坏了", "warranty", "repair"],
    "payment": ["付款", "支付", "分期", "花呗", "payment"],
    "promotion": ["优惠", "优惠券", "满减", "活动", "折扣", "coupon", "discount"],
}

POLICY_TOPIC_LABELS = {
    "returns": "退换货",
    "shipping": "发货与物流",
    "invoice": "发票",
    "after_sales": "售后与保修",
    "payment": "付款",
    "promotion": "优惠活动",
    "other": "其他",
}

# Product attribute families and the words buyers use for them.
ATTRIBUTE_SYNONYMS: Dict[str, List[str]] = {
    "material": ["材质", "面料", "成分", "材料", "布料", "含棉", "纯棉", "material", "fabric"],
    "size": ["尺码", "码数", "尺寸", "大小", "多大", "身高", "体重", "偏大", "偏小", "size"],
    "color": ["颜色", "色号", "配色", "color", "colour"],
    "weight": ["重量", "多重", "克重", "weight"],
    "origin": ["产地", "哪里产", "origin"],
    "care": ["洗涤", "清洗", "机洗", "手洗", "保养", "wash", "care"],
    "spec": ["规格", "型号", "参数", "spec", "model"],
}


def detect_topics(query: str) -> List[str]:
    q = (query or "").lower()
    return [topic for topic, words in POLICY_TOPICS.items() if any(w in q for w in words)]


def detect_attribute_families(query: str) -> List[str]:
    q = (query or "").lower()
    return [fam for fam, words in ATTRIBUTE_SYNONYMS.items() if any(w in q for w in words)]


def attribute_family(key: str) -> Optional[str]:
    """Which family an attribute key belongs to (材质 -> material)."""
    k = (key or "").lower()
    for fam, words in ATTRIBUTE_SYNONYMS.items():
        if any(w in k for w in words):
            return fam
    return None


def join_nonempty(parts: Iterable[str], sep: str = "\n") -> str:
    return sep.join(p for p in parts if p)
