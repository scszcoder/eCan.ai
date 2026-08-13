"""WS-dispatch sanity check (feige_ws) — read a log from an ECAN_FEIGE_WS_DISPATCH=1
session and verify the live WS detector behaves: every WS detection dispatched
exactly once, the DOM path was suppressed (no double-fire), and every dispatched
message got exactly one reply (no lost replies, no duplicate sends).

Usage: python _feige_ws_dispatch_check.py customer_logs/eCan.log
"""
import sys, re, json
from datetime import datetime
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

L = sys.argv[1] if len(sys.argv) > 1 else "customer_logs/eCan.log"
TS = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+)")
DISP = re.compile(r"\[FEIGE-WS-SHADOW\] mode=DISPATCH customer=(?P<c>'[^']*'|\"[^\"]*\").*?text=(?P<t>.+)$")

def wall(l):
    m = TS.match(l); return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f").timestamp() if m else None
def unq(s):
    s = s.strip()
    return s[1:-1] if len(s) >= 2 and s[0] in "'\"" and s[-1] == s[0] else s
def norm(s): return "".join(str(s or "").split())

ws_disp = []        # (wall, cust, text)
fired = 0           # "dispatched WS detection" lines
dom_suppressed = 0  # DOM dispatch suppressed (flag honored)
dom_fired = 0       # "DOM diff detected event" — should be 0 when dispatch is on
replies = []        # (wall, cust, preview)
errors = []
ws_started = ws_dispatch_on = False

for line in open(L, encoding="utf-8", errors="replace"):
    w = wall(line)
    if "FEIGE-WS-SHADOW] started" in line:
        ws_started = True
    if "mode=DISPATCH" in line:
        ws_dispatch_on = True
        m = DISP.search(line)
        if m and w is not None:
            ws_disp.append((w, unq(m.group("c")), unq(m.group("t"))))
    if "dispatched WS detection" in line:
        fired += 1
    if "DOM dispatch SUPPRESSED" in line:
        dom_suppressed += 1
    if "DOM diff detected event" in line:
        dom_fired += 1
    if "[FEIGE-WS-SHADOW] dispatch" in line and "error" in line:
        errors.append(line.strip()[-120:])
    if '"stage": "direct_feige_send_success"' in line or '"stage": "feige_send_tool_success"' in line:
        i = line.find("{")
        try:
            d = json.loads(line[i:])
            if w is not None:
                replies.append((w, str(d.get("customer") or ""),
                                str(d.get("response_preview") or "")))
        except Exception:
            pass

if not ws_started:
    print(f"No WS observer in {L} (ECAN_FEIGE_WS_READER not set?).")
    sys.exit()
if not ws_dispatch_on:
    print(f"WS observer ran in SHADOW only — no mode=DISPATCH lines (ECAN_FEIGE_WS_DISPATCH not 1).")
    sys.exit()

print(f"WS dispatch detections : {len(ws_disp)}")
print(f"dispatch_fn fired      : {fired}   (should == detections)")
print(f"DOM dispatch SUPPRESSED: {dom_suppressed}")
print(f"DOM dispatch LEAKED    : {dom_fired}   (MUST be 0 — else double-fire risk)")
print(f"dispatch errors        : {len(errors)}")
for e in errors[:5]:
    print(f"   ! {e}")

# every WS-dispatched message -> reply count
reps = sorted(replies)
used = [False] * len(reps)
print("\nper WS-dispatched message:")
no_reply = dup = 0
for w, c, t in ws_disp:
    cands = [j for j, (rw, rc, rp) in enumerate(reps)
             if not used[j] and norm(rc) == norm(c) and rw >= w - 1 and rw <= w + 240]
    n = len(cands)
    if n >= 1:
        used[cands[0]] = True
    tag = "OK" if n == 1 else ("NO REPLY" if n == 0 else f"{n} REPLIES")
    if n == 0: no_reply += 1
    print(f"   {c:<8} {tag:<10} {t[:42]!r}")

# duplicate replies: same customer + same text
seen = {}
for w, c, p in reps:
    k = (norm(c), norm(p))
    seen[k] = seen.get(k, 0) + 1
dups = [(c, p, n) for (c, p), n in seen.items() if n > 1]

print("\n===== VERDICT =====")
ok = (fired == len(ws_disp)) and dom_fired == 0 and not dups and no_reply == 0 and not errors
print(f"  dispatch==detections : {'OK' if fired==len(ws_disp) else f'MISMATCH ({fired} vs {len(ws_disp)})'}")
print(f"  DOM not double-firing: {'OK' if dom_fired==0 else f'LEAK ({dom_fired})'}")
print(f"  no lost replies      : {'OK' if no_reply==0 else f'{no_reply} WS msgs got NO reply'}")
print(f"  no duplicate replies : {'OK' if not dups else f'{len(dups)} duplicate(s): '+str(dups[:3])}")
print(f"  no dispatch errors   : {'OK' if not errors else f'{len(errors)} (cross-loop?)'}")
print(f"\n  {'>>> CLEAN — WS live dispatch healthy' if ok else '>>> ISSUES above — do NOT trust under load yet'}")
