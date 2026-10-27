"""Add documents a vendor's crawl missed to its NAS part indexes (shared store), from a {part: [docs]} sweep.
   ECAN_NAS_UPLOAD_ROOTS=C:/chip_docs PYTHONPATH=. python add_docs.py <Vendor> <sweep.json> [--dry]
A doc is missing when neither its URL nor its file name is in the part's index. Parts with no index yet get one
(folder <category>/<part> from raw/parts.json). Prints per part what was added."""
import sys, json, os, logging, types
sys.stdout.reconfigure(encoding="utf-8"); logging.disable(logging.WARNING)
from agent.ec_skills.nas import ugreen_nas as n
from agent.ec_skills.browser_use_extension.extension_tools_service import _save_shared, _doc_file_name
v, sweep_path = sys.argv[1], sys.argv[2]
dry = "--dry" in sys.argv
sweep = json.load(open(sweep_path, encoding="utf-8"))
parts = {p["part"]: p for p in json.load(open(f"C:/chip_docs/{v}/raw/parts.json", encoding="utf-8"))["parts"]}
params = types.SimpleNamespace(shared_dir=f"C:/chip_docs/{v}/files", nas_shared_dir=f"{v}/files")
safe = lambda s: "".join("_" if ch in '/\\:*?"<>|' else ch for ch in s).strip()
added = failed = 0
for part, docs in sweep.items():
    if not isinstance(docs, list):
        print(part, "SWEEP", docs); continue
    rel = f"{v}/docs/{safe(parts[part]['category'])}/{safe(part)}/index.json"
    try: idx = json.loads(n.nas_read_text(rel))
    except Exception: idx = []
    urls = {e.get("url") for e in idx}
    names = {os.path.basename(e.get("file", "")) for e in idx}
    new = [d for d in docs if d["url"] not in urls and _doc_file_name(d) not in names]
    if not new: continue
    print(part, f"+{len(new)}", "(new index)" if not idx else "", [d["title"] for d in new][:6], flush=True)
    if dry: continue
    for d in new:
        e = dict(d)
        if e.get("restricted"):  # listed only (login-only, or fetched later by a vendor script)
            idx.append(e); continue
        folder = _doc_file_name({"url": "x.pdf", "title": e.get("type") or "Other"})[:-4]
        name = _doc_file_name(e)
        try:
            _save_shared(e["url"], folder, name, params); e["file"] = f"files/{folder}/{name}"; added += 1
        except Exception as x:
            e["error"] = str(x); failed += 1
        idx.append(e)
    n.nas_write_text(rel, json.dumps(idx, ensure_ascii=False, indent=1))
print("added", added, "failed", failed)
