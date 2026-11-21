"""Tell which order each downloaded shipping-label PDF belongs to, by what is printed on it.

A label is matched by its tracking number (every carrier label prints it), else its order
number, else its recipient's name. A PDF that matches no order, or more than one, is left
unmatched for a person to check: pairing such PDFs with orders by download order put each
customer's packing note on the other's label (Shopify, 2026-11-20).
"""
import glob
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

from utils.logger_helper import logger_helper as logger


def _digits(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _name(s) -> str:
    return re.sub(r"[^A-Z]", "", str(s or "").upper())


def label_order(text: str, labels: List[Dict]) -> str:
    """The order_id of the one label in ``labels`` this PDF text belongs to, or ""."""
    digits = _digits(text)
    letters = _name(text)
    for test in (
        lambda l: len(_digits(l.get("tracking_number"))) >= 10 and _digits(l.get("tracking_number")) in digits,
        lambda l: _digits(l.get("order_id")) and re.search(
            r"(?:Order|订单)\s*(?:#|No\.?|number)?\s*:?\s*#?\s*" + re.escape(str(l.get("order_id")).lstrip("#")) + r"(?!\d)",
            text, re.I),
        lambda l: len(_name(l.get("recipient"))) >= 6 and _name(l.get("recipient")) in letters,
    ):
        hits = {str(l.get("order_id")) for l in labels if test(l)}
        if len(hits) == 1:
            return hits.pop()
        if len(hits) > 1:
            return ""
    return ""


def match_label_pdfs(folder: str, since: float, labels: List[Dict]) -> Tuple[Dict[str, str], List[str]]:
    """({order_id: pdf}, [unmatched pdfs]) for the PDFs saved in ``folder`` since ``since``
    (minus 5 s). ``labels`` are the label step's rows: order_id, tracking_number, recipient."""
    import fitz
    found: Dict[str, str] = {}
    rest: List[str] = []
    for f in sorted(glob.glob(str(Path(folder) / "*.pdf")), key=os.path.getmtime):
        if os.path.getmtime(f) < since - 5:
            continue
        try:
            with fitz.open(f) as doc:
                text = "\n".join(page.get_text() for page in doc)
        except Exception as e:
            logger.warning(f"[match_pdfs] unreadable download {f}: {e}")
            continue
        oid = label_order(text, labels)
        if oid and oid not in found:
            found[oid] = f
        else:
            rest.append(f)
    return found, rest
