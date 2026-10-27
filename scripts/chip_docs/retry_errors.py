"""Re-fetch the failed entries of a vendor's NAS part indexes into the shared store and patch the indexes.
   ECAN_NAS_UPLOAD_ROOTS=C:/chip_docs python retry_errors.py <Vendor>
Fixes double-encoded URLs (%2526 -> %26, %252B -> %2B) on the way; patches raw/docs/<part>.json the same way."""
import sys, json, os, logging, types, re, urllib.parse
sys.stdout.reconfigure(encoding="utf-8"); logging.disable(logging.WARNING)
from agent.ec_skills.nas import ugreen_nas as n
from agent.ec_skills.browser_use_extension.extension_tools_service import _save_shared, _doc_file_name
v = sys.argv[1]
params = types.SimpleNamespace(shared_dir=f"C:/chip_docs/{v}/files", nas_shared_dir=f"{v}/files")
fixed = failed = 0
for c in n.nas_list(f"{v}/docs"):
    for p in n.nas_list(f"{v}/docs/{c['name']}"):
        rel = f"{v}/docs/{c['name']}/{p['name']}/index.json"
        try: idx = json.loads(n.nas_read_text(rel))
        except Exception: continue
        if not any(e.get("error") for e in idx): continue
        for e in idx:
            if not e.get("error"): continue
            e["url"] = re.sub(r"%25(?=[0-9A-Fa-f]{2})", "%", e["url"])  # double-encoded (%2526, %252B)
            e["url"] = urllib.parse.quote(e["url"], safe=":/?&=%#+,;@~!$'()*")  # raw non-ASCII (480×272)
            folder = _doc_file_name({"url": "x.pdf", "title": e.get("type") or "Other"})[:-4]
            name = _doc_file_name(e)
            try:
                _save_shared(e["url"], folder, name, params)
                e.pop("error"); e["file"] = f"files/{folder}/{name}"; fixed += 1
            except Exception as x:
                e["error"] = str(x); failed += 1
        n.nas_write_text(rel, json.dumps(idx, ensure_ascii=False, indent=1))
        raw = f"C:/chip_docs/{v}/raw/docs/{p['name']}.json"
        if os.path.exists(raw):
            s = open(raw, encoding="utf-8").read()
            if re.search(r"%25[0-9A-Fa-f]{2}", s): open(raw, "w", encoding="utf-8").write(re.sub(r"%25(?=[0-9A-Fa-f]{2})", "%", s))
        print(p["name"], "errors left", sum(1 for e in idx if e.get("error")), flush=True)
print("fixed", fixed, "still failing", failed)
