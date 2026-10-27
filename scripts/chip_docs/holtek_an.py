"""Holtek application notes: the crawl lists them restricted (page URL /application-notes/<code>[#zh]) because the
file only comes from POST /webapi/api/ApplicationNote/ApplicationNoteDownload (public, no login/captcha) as a base64
ZIP. Fetch each note once (per code+language), store it in Holtek/files/Application Note/ and turn the index entries
into normal file entries.
   ECAN_NAS_UPLOAD_ROOTS=C:/chip_docs PYTHONPATH=. python holtek_an.py [--dry]"""
import sys, json, os, io, re, time, base64, zipfile, logging, urllib.request
sys.stdout.reconfigure(encoding="utf-8"); logging.disable(logging.WARNING)
from agent.ec_skills.nas import ugreen_nas as n
from agent.ec_skills.browser_use_extension.extension_tools_service import _doc_file_name, _shared_nas_sizes

dry = "--dry" in sys.argv
API = "https://www.holtek.com.cn/webapi/api/ApplicationNote/ApplicationNoteDownload"
FOLDER = "Application Note"; NAS_FOLDER = f"Holtek/files/{FOLDER}"; BUF = "C:/chip_docs/Holtek/files/" + FOLDER
safe = lambda s: "".join("_" if ch in '/\\:*?"<>|' else ch for ch in s).strip()
parts = json.load(open("C:/chip_docs/Holtek/raw/parts.json", encoding="utf-8"))["parts"]
cache = {}  # (code, lang) -> file entry path or Exception text

def fetch(code, lt, e):
    req = urllib.request.Request(API, data=json.dumps({"CCode": code, "CLanguageType": lt}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r: js = json.loads(r.read())
            break
        except Exception:
            if i == 2: raise
            time.sleep(10)
    if not js.get("FileByte"): raise RuntimeError(f"no file: {js.get('Message')}")
    z = zipfile.ZipFile(io.BytesIO(base64.b64decode(js["FileByte"])))
    pdfs = [m for m in z.namelist() if m.lower().endswith(".pdf")]
    if not pdfs: raise RuntimeError(f"zip without pdf: {z.namelist()[:3]}")
    data = z.read(pdfs[0])
    if not data.startswith(b"%PDF"): raise RuntimeError("not a PDF")
    name = _doc_file_name({"url": pdfs[0], "type": e.get("type"), "title": e.get("title")})
    if not _shared_nas_sizes(NAS_FOLDER).get(name.lower()):
        os.makedirs(BUF, exist_ok=True); p = os.path.join(BUF, name)
        open(p, "wb").write(data); n.nas_upload(p, f"{NAS_FOLDER}/{name}")
        _shared_nas_sizes(NAS_FOLDER)[name.lower()] = len(data); os.remove(p)
    time.sleep(1)
    return f"files/{FOLDER}/{name}"

ok = bad = touched = 0
for p in parts:
    rel = f"Holtek/docs/{safe(p['category'])}/{safe(p['part'])}/index.json"
    try: idx = json.loads(n.nas_read_text(rel))
    except Exception: continue
    changed = False
    for e in idx:
        m = re.search(r"/application-notes/([A-Za-z0-9]+)(#zh)?$", e.get("url", ""))
        if not (e.get("restricted") and m): continue
        key = (m.group(1), 2 if (m.group(2) or e.get("lang") == "zh") else 3)
        if dry: cache.setdefault(key, None); continue
        if key not in cache:
            try: cache[key] = fetch(*key, e); ok += 1
            except Exception as x: cache[key] = RuntimeError(str(x)); bad += 1; print("FAIL", key, x, flush=True)
            if (ok + bad) % 25 == 0: print(ok, "fetched", bad, "failed", flush=True)
        if isinstance(cache[key], str):
            e.pop("restricted", None); e["file"] = cache[key]; changed = True
    if changed:
        n.nas_write_text(rel, json.dumps(idx, ensure_ascii=False, indent=1)); touched += 1
print("unique notes", len(cache), "fetched", ok, "failed", bad, "indexes updated", touched)
