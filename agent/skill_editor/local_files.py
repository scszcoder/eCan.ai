"""Describe the local files and folders a skill request names.

The skill editor's LLM cannot see the user's computer, so a request like "follow the template in
C:/work/" makes it guess the template's layout. The desktop side calls describe_local_files() on
the user's message and answers and sends the result along (canvas_context["local_files"]); the
agent keeps it in the conversation so the generator writes code against the real files.

Only folder listings and spreadsheet contents are read. Other files are named with their size,
never read: text files next to a template often hold logins.
"""
import os
import re
import time
from typing import Iterable, List

_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"'<>|*?，。、；：（）()【】「」]*")
_SHEETS = (".xlsx", ".xlsm", ".csv")
# Columns whose example values are a real person's details: shown masked
_PERSONAL = re.compile(r"姓名|电话|手机|地址|邮编|邮箱|城市|name|phone|address|e-?mail|zip|postal|city", re.I)
MAX_CHARS = 8000


def find_local_paths(text: str) -> List[str]:
    """Windows paths in the text that exist on this computer, in order, without repeats."""
    found = []
    for m in _PATH_RE.finditer(text or ""):
        p = m.group().rstrip(".,;:!")
        while p and not os.path.exists(p):
            p = p[:-1]      # "C:/work/a.xlsx和图片" -> trim trailing text until the path exists
        if p and len(p) > 3:
            norm = os.path.normcase(os.path.abspath(p))
            if norm not in (os.path.normcase(os.path.abspath(f)) for f in found):
                found.append(p)
    return found


def _cell(v) -> str:
    s = "" if v is None else str(v).replace("\n", " ")
    return s[:40] + "…" if len(s) > 40 else s


def _rows(rows, limit: int = 6) -> List[str]:
    """The first rows that have a value, trailing empty cells dropped; personal columns masked
    below the header row that names them."""
    out, personal = [], set()
    for i, row in enumerate(rows):
        if len(out) >= limit or i >= 50:
            break
        cells = [_cell(c) for c in row]
        while cells and not cells[-1]:
            cells.pop()
        if not cells:
            continue
        shown = ["***" if j in personal and c else c for j, c in enumerate(cells)]
        personal |= {j for j, c in enumerate(cells) if _PERSONAL.search(c)}
        out.append(f"row {i + 1}: " + " | ".join(shown))
    return out


def _describe_sheet(path: str) -> List[str]:
    out = []
    try:
        if path.lower().endswith(".csv"):
            import csv
            with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
                return ["    " + r for r in _rows(csv.reader(f))]
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for ws in wb.worksheets[:3]:
            out.append(f"    sheet '{ws.title}':")
            out += ["      " + r for r in _rows(ws.iter_rows(values_only=True))]
        wb.close()
    except Exception as e:
        out.append(f"    (could not read: {e})")
    return out


def _entry(path: str) -> str:
    st = os.stat(path)
    when = time.strftime("%Y-%m-%d", time.localtime(st.st_mtime))
    return f"{os.path.basename(path)} ({st.st_size} bytes, {when})"


def describe_local_files(texts: Iterable[str]) -> str:
    """A text block describing every existing local path named in the texts ("" if none)."""
    lines: List[str] = []
    shown = set()
    for p in find_local_paths("\n".join(t for t in texts if t)):
        if os.path.isdir(p):
            names = sorted(os.listdir(p), key=lambda n: os.path.getmtime(os.path.join(p, n)), reverse=True)
            lines.append(f"- Folder {p} ({len(names)} entries, newest first):")
            lines += [f"    {_entry(os.path.join(p, n))}" + ("/" if os.path.isdir(os.path.join(p, n)) else "")
                      for n in names[:40]]
            for n in [n for n in names if n.lower().endswith(_SHEETS)][:2]:
                lines.append(f"  Spreadsheet {n}:")
                lines += _describe_sheet(os.path.join(p, n))
                shown.add(os.path.normcase(os.path.abspath(os.path.join(p, n))))
        else:
            lines.append(f"- File {p}: {_entry(p)}")
            if p.lower().endswith(_SHEETS) and os.path.normcase(os.path.abspath(p)) not in shown:
                lines += _describe_sheet(p)
    if not lines:
        return ""
    block = "## LOCAL FILES (read on the user's computer; write code against these exact names and layouts):\n" + "\n".join(lines)
    return block[:MAX_CHARS]
