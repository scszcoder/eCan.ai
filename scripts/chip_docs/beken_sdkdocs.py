"""Beken Armino SDK documentation (docs.bekencorp.com, public, no WAF): mirror every doc set (kit x chip x language)
as an offline copy, zip it, store the zip on the NAS (Beken/files/SDK Documentation/) and list it in the chip's part
index. Pages/assets are fetched only from inside the set's own root, gently.
   ECAN_NAS_UPLOAD_ROOTS=C:/chip_docs PYTHONPATH=. python beken_sdkdocs.py <sets.json> [--dry]"""
import sys, json, os, re, time, zipfile, shutil, logging, urllib.request, urllib.parse
from collections import deque
sys.stdout.reconfigure(encoding="utf-8"); logging.disable(logging.WARNING)
from agent.ec_skills.nas import ugreen_nas as n
from agent.ec_skills.browser_use_extension.extension_tools_service import _doc_file_name, _shared_nas_sizes

sets = json.load(open(sys.argv[1])); dry = "--dry" in sys.argv
BUF = "C:/chip_docs/Beken/sdkdocs_buf"; FOLDER = "SDK Documentation"; NAS_FOLDER = f"Beken/files/{FOLDER}"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
REF = re.compile(r"""(?:href|src)\s*=\s*["']([^"'#?]+)""", re.I)
SKIP = re.compile(r"/_sources/|\.(zip|rar|7z|tar|gz|bin|exe|msi)$", re.I)
MAX_FILES, MAX_BYTES = 4000, 20_000_000
PDFS = os.path.join(os.path.dirname(sys.argv[1]), "outside_pdfs.json")
PARTS = {  # chip folder -> (part, category); sets that are not about one chip go to a common unit
    "bk3633": ("BK3633", "Bluetooth LE SoCs"), "bk3298": ("BK3298", "Dual-mode Bluetooth SoCs")}
COMMON = ("Beken Armino SDK Tools", "SDK Tools")


def get(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.geturl(), r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410): return None
            time.sleep(5 * (i + 1))
        except Exception:
            time.sleep(5 * (i + 1))
    return None


def mirror(root, out):
    seen, q, files, pdfs = {root + "index.html"}, deque([root + "index.html"]), 0, set()
    while q and files < MAX_FILES:
        url = q.popleft()
        r = get(url); time.sleep(0.25)
        if not r: continue
        final, ctype, body = r
        if not final.startswith(root) or len(body) > MAX_BYTES: continue
        rel = urllib.parse.unquote(final[len(root):]) or "index.html"
        if rel.endswith("/"): rel += "index.html"
        p = os.path.join(out, *rel.split("/")); os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(body); files += 1
        if "html" in ctype or rel.endswith((".html", ".css")):
            for ref in REF.findall(body.decode("utf-8", "replace")) + re.findall(r"url\(['\"]?([^'\")#?]+)", body.decode("utf-8", "replace")):
                u = urllib.parse.urljoin(final, ref.strip())
                if u.lower().endswith(".pdf") and not u.startswith(root): pdfs.add(u)
                if u.startswith(root) and u not in seen and not SKIP.search(u):
                    seen.add(u); q.append(u)
    return files, pdfs


def unit(root):
    m = re.search(r"/(?:armino|arminodoc)/(?:(bk_[a-z_]+)/)?(?:smp_doc/)?([a-z0-9_]+)/(en|zh_CN|zh-cn)/(?:([^/]+)/)?$", root)
    kit, chip, lang, ver = m.group(1) or "armino", m.group(2), m.group(3), m.group(4) or "latest"
    if "smp_doc" in root: kit = "bk_avdk_smp"
    if re.fullmatch(r"bk\d{4}[a-z]?", chip):
        part = PARTS.get(chip) or (chip.upper(), None)
    else:
        part = COMMON
    zh = lang != "en"
    title = " ".join(x for x in ("Armino", "" if kit == "armino" else kit, chip, "SDK documentation", ver) if x) + (" 中文" if zh else "")
    return part, title, ("zh" if zh else "en")


parts = {p["part"]: p for p in json.load(open("C:/chip_docs/Beken/raw/parts.json", encoding="utf-8"))["parts"]}
added = {}
for root in sets:
    (part, cat), title, lang = unit(root)
    cat = cat or (parts[part]["category"] if part in parts else None)
    if not cat:
        print("NO PART", root); continue
    name = _doc_file_name({"url": "x.zip", "type": "SDK Documentation", "title": title})
    print(part, "|", name, flush=True)
    if dry: continue
    if not _shared_nas_sizes(NAS_FOLDER).get(name.lower()):
        out = os.path.join(BUF, name[:-4]); shutil.rmtree(out, ignore_errors=True)
        files, pdfs = mirror(root, out)
        if files < 3:
            print("  too few files", files); continue
        z = out + ".zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for d, _, fs in os.walk(out):
                for f in fs: zf.write(os.path.join(d, f), os.path.relpath(os.path.join(d, f), out))
        n.nas_upload(z, f"{NAS_FOLDER}/{name}"); _shared_nas_sizes(NAS_FOLDER)[name.lower()] = os.path.getsize(z)
        print(f"  {files} files, {os.path.getsize(z) // 1024} KB zip, outside PDFs: {sorted(pdfs)[:5]}", flush=True)
        found = json.load(open(PDFS, encoding="utf-8")) if os.path.exists(PDFS) else {}
        for u in pdfs: found.setdefault(u, []).append(part)
        json.dump(found, open(PDFS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.remove(z); shutil.rmtree(out, ignore_errors=True)
    added.setdefault((part, cat), []).append({"type": "SDK Documentation", "title": title, "url": root, "lang": lang,
                                              "file": f"files/{FOLDER}/{name}"})

safe = lambda s: "".join("_" if ch in '/\\:*?"<>|' else ch for ch in s).strip()
for (part, cat), entries in added.items():
    rel = f"Beken/docs/{safe(cat)}/{safe(part)}/index.json"
    try: idx = json.loads(n.nas_read_text(rel))
    except Exception: idx = []
    have = {e.get("url") for e in idx}
    idx += [e for e in entries if e["url"] not in have]
    n.nas_write_text(rel, json.dumps(idx, ensure_ascii=False, indent=1))
    print("index", part, len(idx))
