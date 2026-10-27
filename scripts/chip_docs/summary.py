"""Per-vendor document counts from the NAS part indexes: parts, parts with files, entries, files, unique files,
restricted, errors, en/zh. PYTHONPATH=. python summary.py <out.json> <Vendor>..."""
import sys, json, logging, threading
from concurrent.futures import ThreadPoolExecutor
sys.stdout.reconfigure(encoding="utf-8"); logging.disable(logging.WARNING)
from agent.ec_skills.nas import ugreen_nas as n

safe = lambda s: "".join("_" if ch in '/\\:*?"<>|' else ch for ch in s).strip()
out = {}
for v in sys.argv[2:]:
    try:
        parts = json.load(open(f"C:/chip_docs/{v}/raw/parts.json", encoding="utf-8"))["parts"]
    except Exception as e:
        out[v] = {"error": str(e)}; continue
    st = dict(parts=len(parts), with_files=0, entries=0, files=0, restricted=0, errors=0, en=0, zh=0)
    uniq, lock = set(), threading.Lock()

    def one(p):
        try:
            idx = json.loads(n.nas_read_text(f"{v}/docs/{safe(p['category'])}/{safe(p['part'])}/index.json"))
        except Exception:
            return
        with lock:
            ok = [e for e in idx if e.get("file")]
            st["with_files"] += bool(ok); st["entries"] += len(idx); st["files"] += len(ok)
            st["restricted"] += sum(1 for e in idx if e.get("restricted") and not e.get("file"))
            st["errors"] += sum(1 for e in idx if e.get("error") and not e.get("file"))
            for e in ok:
                uniq.add(e["file"].lower()); st["zh" if e.get("lang") == "zh" else "en"] += 1

    with ThreadPoolExecutor(8) as ex:
        list(ex.map(one, parts))
    st["unique_files"] = len(uniq)
    out[v] = st
    print(v, st, flush=True)
json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), indent=1)
