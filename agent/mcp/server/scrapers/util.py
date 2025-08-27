import asyncio
import csv
import re
from pathlib import Path
from typing import Dict, List, Tuple
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_agent_by_id, get_traceback


def clean_text(txt: str) -> str:
    txt = re.sub(r"\s+", " ", txt or "").strip()
    return txt


def write_csv(rows: List[Dict[str, str]], header_order: List[str], out_path: Path):
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header_order, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
    except Exception as e:
        err_trace = get_traceback(e, "ErrorWriteCSV")
        logger.debug(err_trace)

def compute_header_order(special: List[str], all_rows: List[Dict[str, str]], dynamic_order: List[str]) -> List[str]:
    """Special fields first, then dynamic columns, then any leftovers."""
    dyn = [k for k in dynamic_order if k not in special]
    leftovers = []
    seen = set(special) | set(dyn)
    for r in all_rows:
        for k in r.keys():
            if k not in seen:
                leftovers.append(k)
                seen.add(k)
    return special + dyn + leftovers
