"""
Detection-lag analyzer for the flood-test harness (2026-06-03).

The customer's INFO logs can't measure detection lag because they have no
"customer typed" timestamp — only when eCan *detected* the message
(`dom_observed`). The emulation DOES know exactly when each query was sent
(the metrics oracle records `q_sent {cust, text, ts}`), so on the same machine
we can compute the true latency the customer feels:

    detection_lag = dom_observed.ts_ms  -  q_sent.ts

Both are epoch-ms on the same host, so they're directly comparable.

This script joins the emulation's q_sent events (from results/<run_id>.json)
with the app's dom_observed ledger lines (from runlogs/eCan.log), per customer,
nearest-after, and reports the detection-lag distribution. It also parses the
EventMonitor [HB] heartbeat to flag *why* detection stalls — loop starvation
(HB gap >> the 30s cadence) and no_match polls — and marks which high-lag
queries fall inside a starvation / no_match window.

Usage (the round-controller calls this automatically after each round):
  python analyze_detection_lag.py \
      --results results/<run_id>.json \
      --log /path/to/runlogs/eCan.log \
      --out results/<run_id>_detection.json
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Windows consoles default to cp1252; customer names/messages are Chinese.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

EMU_ROOT = Path(__file__).resolve().parent

_LOG_TS = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+)")
_DOM = re.compile(r'"stage":\s*"dom_observed"')
_HB = re.compile(r"\[EventMonitor\]\[HB\].*?status=(\w+)")
HB_STARVE_GAP_S = 45.0      # HB cadence is ~30s; >45s = loop starved
HB_CADENCE_S = 30.0


def _log_dt_to_ms(s: str) -> float:
    # "2026-06-03 13:06:06,645" -> epoch ms (local tz = same machine as the run)
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S,%f")
    return dt.timestamp() * 1000.0


def load_qsent(results_path: Path):
    data = json.loads(results_path.read_text(encoding="utf-8"))
    out = []
    for e in data.get("events") or []:
        if e.get("mtype") == "q_sent":
            out.append({
                "cust": str(e.get("cust") or e.get("cid") or "?"),
                "text": " ".join(str(e.get("text") or "").split()),
                "ts": float(e.get("ts") or 0),
            })
    out.sort(key=lambda x: x["ts"])
    return out


def parse_log(log_path: Path, t_lo_ms: float, t_hi_ms: float):
    """Return (dom_observed[], hb_all[]).

    Each event carries TWO clocks:
      * ``ts``   — epoch ms (dom uses its authoritative ts_ms field). Used to
                   join against q_sent (both epoch, same machine).
      * ``wall`` — the log line's wall-clock as ms. Used ONLY for HB↔dom
                   correlation, so that stays valid regardless of the analyzer
                   host's timezone vs the log's (epoch and wall differ by a
                   constant offset within one log).

    dom is filtered to the epoch window [t_lo, t_hi]; hb is returned unfiltered
    (the caller windows it by the dom wall-clock span)."""
    dom, hb = [], []
    with log_path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _LOG_TS.search(line)
            wall = _log_dt_to_ms(m.group(1)) if m else 0.0
            if "[EventMonitor][HB]" in line:
                st = _HB.search(line)
                hb.append({"wall": wall, "status": st.group(1) if st else "?"})
                continue
            if "[FEIGE-LEDGER]" not in line or not _DOM.search(line):
                continue
            i = line.find("{")
            if i < 0:
                continue
            try:
                blob = json.loads(line[i:])
            except Exception:
                continue
            ts_ms = float(blob.get("ts_ms") or 0)
            if not (t_lo_ms <= ts_ms <= t_hi_ms):
                continue
            dom.append({
                "cust": str(blob.get("customer_name") or blob.get("customer") or "?"),
                "preview": " ".join(str(blob.get("latest_preview") or "").split()),
                "ts": ts_ms,
                "wall": wall,
            })
    dom.sort(key=lambda x: x["ts"])
    hb.sort(key=lambda x: x["wall"])
    return dom, hb


def hb_windows(hb):
    """Return (starvation_windows[(lo,hi)], no_match_windows[(lo,hi)]) in
    wall-clock ms (the same clock dom['wall'] uses)."""
    starve, nomatch = [], []
    for i in range(len(hb) - 1):
        gap = hb[i + 1]["wall"] - hb[i]["wall"]
        if gap > HB_STARVE_GAP_S * 1000:
            starve.append((hb[i]["wall"], hb[i + 1]["wall"]))
    for h in hb:
        if h["status"] == "no_match":
            # a no_match poll blinds detection for ~one cadence around it
            nomatch.append((h["wall"] - HB_CADENCE_S * 1000, h["wall"]))
    return starve, nomatch


def _in_windows(ts, windows):
    return any(lo <= ts <= hi for lo, hi in windows)


def analyze(results_path: Path, log_path: Path):
    qsent = load_qsent(results_path)
    if not qsent:
        return {"error": "no q_sent events in results file", "results": str(results_path)}
    t_lo = min(q["ts"] for q in qsent) - 5000
    t_hi = max(q["ts"] for q in qsent) + 180000
    dom, hb_all = parse_log(log_path, t_lo, t_hi)
    # Window HB to the run's wall-clock span (derived from the matched dom
    # events) so the correlation is timezone-independent.
    if dom:
        w_lo = min(d["wall"] for d in dom) - 5000
        w_hi = max(d["wall"] for d in dom) + 180000
        hb = [h for h in hb_all if w_lo <= h["wall"] <= w_hi]
    else:
        hb = []
    starve, nomatch = hb_windows(hb)

    # Per-customer nearest-after match.
    dom_by_cust = {}
    for d in dom:
        dom_by_cust.setdefault(d["cust"], []).append(d)
    used = {c: set() for c in dom_by_cust}

    rows = []
    for q in qsent:
        cands = dom_by_cust.get(q["cust"], [])
        best = None
        for idx, d in enumerate(cands):
            if idx in used.get(q["cust"], set()):
                continue
            if d["ts"] >= q["ts"] - 250:  # allow 250ms clock skew
                best = (idx, d)
                break
        if best is None:
            rows.append({"cust": q["cust"], "text": q["text"][:24],
                         "lag_s": None, "detected": False})
            continue
        idx, d = best
        used[q["cust"]].add(idx)
        lag = (d["ts"] - q["ts"]) / 1000.0
        rows.append({
            "cust": q["cust"], "text": q["text"][:24], "lag_s": round(lag, 1),
            "detected": True,
            "in_starvation": _in_windows(d["wall"], starve),
            "in_no_match": _in_windows(d["wall"], nomatch),
        })

    lags = sorted(r["lag_s"] for r in rows if r["lag_s"] is not None)
    undetected = sum(1 for r in rows if not r["detected"])

    def pct(p):
        return lags[min(len(lags) - 1, int(len(lags) * p))] if lags else None

    summary = {
        "results_file": str(results_path),
        "log_file": str(log_path),
        "queries": len(qsent),
        "detected": len(lags),
        "undetected": undetected,
        "detection_lag_s": {
            "median": pct(0.5), "p90": pct(0.9),
            "max": lags[-1] if lags else None,
            "mean": round(sum(lags) / len(lags), 1) if lags else None,
        },
        "over_35s": sum(1 for x in lags if x > 35),
        "hb": {
            "count": len(hb),
            "starvation_windows": len(starve),
            "max_starvation_s": round(max((hi - lo) / 1000 for lo, hi in starve), 1) if starve else 0,
            "no_match_polls": sum(1 for h in hb if h["status"] == "no_match"),
        },
        # how many high-lag detections coincide with a starvation / no_match window
        "high_lag_in_starvation": sum(1 for r in rows if r.get("lag_s") and r["lag_s"] > 20 and r.get("in_starvation")),
        "high_lag_in_no_match": sum(1 for r in rows if r.get("lag_s") and r["lag_s"] > 20 and r.get("in_no_match")),
        "rows": rows,
    }
    return summary


def _print_summary(s):
    if "error" in s:
        print(f"[detection-lag] {s['error']}")
        return
    dl = s["detection_lag_s"]
    print(f"[detection-lag] queries={s['queries']} detected={s['detected']} undetected={s['undetected']}")
    print(f"[detection-lag] lag(s): median={dl['median']} p90={dl['p90']} max={dl['max']} mean={dl['mean']}  over35s={s['over_35s']}")
    h = s["hb"]
    print(f"[detection-lag] monitor HB: count={h['count']} starvation_windows={h['starvation_windows']} "
          f"max_starvation={h['max_starvation_s']}s no_match_polls={h['no_match_polls']}")
    print(f"[detection-lag] high-lag(>20s) coinciding with: starvation={s['high_lag_in_starvation']} no_match={s['high_lag_in_no_match']}")
    worst = sorted((r for r in s["rows"] if r["lag_s"] is not None), key=lambda r: -r["lag_s"])[:8]
    if worst:
        print("[detection-lag] worst detections:")
        for r in worst:
            tags = []
            if r.get("in_starvation"):
                tags.append("STARVED")
            if r.get("in_no_match"):
                tags.append("no_match")
            print(f"    {r['cust']:>8}  {r['lag_s']:>6}s  {r['text']}  {' '.join(tags)}")


def main():
    ap = argparse.ArgumentParser(description="Detection-lag analyzer (q_sent vs dom_observed).")
    ap.add_argument("--results", required=True, help="results/<run_id>.json from the metrics oracle")
    ap.add_argument("--log", required=True, help="path to runlogs/eCan.log")
    ap.add_argument("--out", default=None, help="write report JSON here (default: <results>_detection.json)")
    args = ap.parse_args()

    results_path = Path(args.results)
    log_path = Path(args.log)
    if not results_path.is_file():
        print(f"[detection-lag] results file not found: {results_path}")
        return 1
    if not log_path.is_file():
        print(f"[detection-lag] log file not found: {log_path}")
        return 1

    summary = analyze(results_path, log_path)
    _print_summary(summary)

    out = Path(args.out) if args.out else results_path.with_name(results_path.stem + "_detection.json")
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[detection-lag] report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
