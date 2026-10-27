"""Every done part in <Vendor>/status.md has <Vendor>/docs/<cat>/<part>/index.json on the NAS; count its entries and errors,
and check each indexed file exists in the shared store.  PYTHONPATH=. python verify_nas.py <Vendor>"""
import json, re, tempfile, os, threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dotenv import load_dotenv
from utils.run_env import run_env_path
load_dotenv(run_env_path(), override=False)
from agent.ec_skills.nas import ugreen_nas as nas

import sys as _s
V = _s.argv[1]
ROOT = Path("C:/chip_docs") / V
cat = {x["part"]: x["category"] for x in json.loads((ROOT / "raw/parts.json").read_text(encoding="utf-8"))["parts"]}
parts = [c[0] for line in (ROOT / "status.md").read_text(encoding="utf-8").splitlines()
         if (c := [x.strip() for x in line.strip().strip("|").split("|")]) and len(c) >= 9 and c[3] == "done"]
print(len(parts), "done parts,", len(cat), "planned")
lock = threading.Lock(); st = Counter(); bad = []; files = set(); tmp = tempfile.mkdtemp()

def check(p):
    rel = f"{V}/docs/{cat[p]}/{p}/index.json"
    try:
        idx = json.loads(nas.nas_read_text(rel))
    except Exception as e:
        with lock: st["missing"] += 1; bad.append(f"{p}: {e}")
        return
    rs = [e for e in idx if e.get("restricted")]; ok = [e for e in idx if e.get("file")]
    with lock:
        st["indexed"] += 1; st["entries"] += len(idx); st["files"] += len(ok); st["errors"] += len(idx) - len(ok) - len(rs); st["restricted"] += len(rs); errs = [e for e in idx if not e.get("file") and not e.get("restricted")]; bad.extend(f"{p}: {e.get('error') or e}"[:200] for e in errs[:1])
        files.update(e["file"] for e in ok)
        if not ok: bad.append(f"{p}: no files in index")

with ThreadPoolExecutor(8) as ex: list(ex.map(check, parts))
# every referenced shared file exists
by_folder = {}
for f in files:
    by_folder.setdefault(f.rsplit("/", 1)[0], set()).add(f.rsplit("/", 1)[1].lower())
missing = 0
for folder, names in by_folder.items():
    have = {e["name"].lower() for e in nas.nas_list(V + "/" + folder) if not e["is_dir"]}
    missing += len(names - have)
    for n in list(names - have)[:3]: bad.append(f"not in store: {folder}/{n}")
print(dict(st), "unique shared files", len(files), "missing in store", missing)
for b in bad[:30]: print("  ", b)

# stray part folders: on the NAS but not a done part of that category
done_by_cat = Counter()
stray = []
for c in sorted(set(cat.values())):
    names = {e["name"] for e in nas.nas_list(f"{V}/docs/{c}") if e["is_dir"]}
    want = {p for p in parts if cat[p] == c}
    stray += [f"{c}/{n}" for n in sorted(names - want)]
    lost = want - names
    if lost: print("done but no folder:", c, sorted(lost)[:5])
print("stray folders", len(stray), stray[:20])
