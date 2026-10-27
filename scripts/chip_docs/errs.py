"""Count failed (error) entries in a vendor's NAS part indexes, grouped by URL.  PYTHONPATH=. python errs.py <Vendor> <out.json>"""
import sys, json, collections, logging
sys.stdout.reconfigure(encoding="utf-8"); logging.disable(logging.WARNING)
from agent.ec_skills.nas import ugreen_nas as n
v = sys.argv[1]; out = collections.defaultdict(lambda: [0, "", ""])
for c in n.nas_list(f"{v}/docs"):
    for p in n.nas_list(f"{v}/docs/{c['name']}"):
        try: idx = json.loads(n.nas_read_text(f"{v}/docs/{c['name']}/{p['name']}/index.json"))
        except Exception: continue
        for e in idx:
            if e.get("error"): o = out[e["url"]]; o[0] += 1; o[1] = e["error"][:60]; o[2] = e.get("title", "")[:70]
print(len(out), "unique failing urls")
for u, (k, er, t) in sorted(out.items(), key=lambda x: -x[1][0]): print(k, er, "|", t, "|", u)
json.dump(list(out), open(sys.argv[2], "w"))
