"""WS-shadow vs DOM detection-latency comparator (feige_ws).

Reads a customer eCan.log that ran with BOTH the DOM 新消息 monitor and the
shadow WS observer (ECAN_FEIGE_WS_READER=1), matches each customer message
between the two paths by (customer, text), and reports how much EARLIER the WS
path detected it than the DOM dom_observed.

  delta = dom_observed_walltime - ws_shadow_walltime    (positive = WS won)

Also flags messages only ONE side saw (DOM-missed / WS-missed).

Usage: python _feige_ws_vs_dom.py customer_logs/eCan.log
"""
import sys, re, json
from datetime import datetime
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

L = sys.argv[1] if len(sys.argv) > 1 else "customer_logs/eCan.log"
TS = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+)")
SHADOW = re.compile(r"\[FEIGE-WS-SHADOW\] customer=(?P<c>'[^']*'|\"[^\"]*\")\s+conv=(?P<conv>\S+)\s+"
                    r"msg_id=(?P<mid>\S+)\s+ts_ms=(?P<ts>\S+)\s+type=(?P<ty>\S+)\s+text=(?P<t>.+)$")

def wall(line):
    m = TS.match(line)
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f").timestamp() if m else None

def norm(s):
    return "".join(str(s or "").split())

def unrepr(s):
    s = s.strip()
    if len(s) >= 2 and s[0] in "'\"" and s[-1] == s[0]:
        s = s[1:-1]
    return s

shadow = {}   # msg_id -> (wall, customer, text)
dom = []      # (wall, customer, preview)
win_start = None   # observer is only comparable from when it started
for line in open(L, encoding="utf-8", errors="replace"):
    w = wall(line)
    if w is None:
        continue
    if "[FEIGE-WS-SHADOW] started" in line:
        win_start = w if win_start is None else win_start
    if "[FEIGE-WS-SHADOW]" in line:
        m = SHADOW.search(line)
        if not m:
            continue
        mid = m.group("mid")
        if mid not in shadow:   # earliest occurrence
            shadow[mid] = (w, unrepr(m.group("c")), unrepr(m.group("t")))
    elif '"stage": "dom_observed"' in line:
        i = line.find("{")
        try:
            d = json.loads(line[i:])
        except Exception:
            continue
        dom.append((w, str(d.get("customer") or d.get("customer_name") or ""),
                    str(d.get("latest_preview") or "")))

if not shadow:
    print(f"No [FEIGE-WS-SHADOW] lines in {L} — observer not run (set ECAN_FEIGE_WS_READER=1, rebuild feige_ws, restart).")
    sys.exit()

# Only compare against dom_observed from when the observer was actually running
# (it attaches mid-session; earlier dom_observed have no WS counterpart by design).
if win_start is not None:
    dom = [d for d in dom if d[0] >= win_start - 2]
dom.sort()
dom_used = [False] * len(dom)

def match_dom(cust, text, ws_w):
    """earliest dom_observed for same customer whose preview prefix-matches text."""
    tn = norm(text)
    best = None
    for idx, (dw, dc, dp) in enumerate(dom):
        if dom_used[idx]:
            continue
        if cust and dc and norm(cust) != norm(dc):
            continue
        pn = norm(dp)
        if len(pn) < 2 or len(tn) < 2:
            continue
        if not (tn.startswith(pn) or pn.startswith(tn)):
            continue
        if dw < ws_w - 5:           # dom can't be the match if it's >5s BEFORE ws
            continue
        if best is None or dw < dom[best][0]:
            best = idx
    return best

rows = []
ws_only = 0
for mid, (ws_w, cust, text) in sorted(shadow.items(), key=lambda kv: kv[1][0]):
    idx = match_dom(cust, text, ws_w)
    if idx is None:
        ws_only += 1
        rows.append((ws_w, cust, text, None))
    else:
        dom_used[idx] = True
        rows.append((ws_w, cust, text, dom[idx][0] - ws_w))

print(f"{'cust':<10} {'WS→DOM lead(s)':>14}  text")
print("-" * 70)
leads = []
for ws_w, cust, text, delta in rows:
    if delta is None:
        print(f"{cust[:10]:<10} {'DOM MISSED':>14}  {text[:44]!r}")
    else:
        leads.append(delta)
        print(f"{cust[:10]:<10} {delta:>14.1f}  {text[:44]!r}")
print("-" * 70)

dom_only = sum(1 for u in dom_used if not u)
if leads:
    leads.sort()
    p = lambda q: leads[min(len(leads) - 1, int(len(leads) * q))]
    print(f"matched={len(leads)}  WS-earlier={sum(1 for x in leads if x > 0)}  "
          f"median_lead={p(.5):.1f}s  p90={p(.9):.1f}s  max={leads[-1]:.1f}s  min={leads[0]:.1f}s")
print(f"WS-only (DOM never dom_observed it)={ws_only}   dom_observed-only={dom_only}")
if dom_only:
    print("  dom_observed with no WS match (expected: greetings / system / duplicate re-detections):")
    for idx, (dw, dc, dp) in enumerate(dom):
        if not dom_used[idx]:
            print(f"    {dc} | {dp[:54]}")
print("\nPositive lead = WS detected earlier than the scrape. WS-only = DOM blind spots (e.g. cards).")
