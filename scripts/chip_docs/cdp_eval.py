"""Run a chip-docs collector script in a REAL Chrome on this machine (own profile, driven over CDP), the way the
crawler's evaluate_to_file runs it: open <start_url>, wait, then evaluate `(<script>)(<args>)` in that page.
For sites that plain HTTP (curl / run_collector.js under Node) cannot reach: bot checks, cookies, same-origin APIs.

  python -I cdp_eval.py <script.js> <start_url> [--args JSON] [--out result.json] [--profile NAME] [--wait 10]
                        [--timeout 900] [--keep-open]

--profile picks the Chrome user-data dir under C:/chip_docs/browser_profiles/ (default: the start URL's host), so
each vendor keeps its own cookies. Prints a short summary (row count / total) and writes the result to --out.
Use --script-inline '<js expression>' instead of a file to evaluate a quick expression (e.g. to explore a page).
Never uses the user's own Chrome or the Claude-in-Chrome extension.
"""
import argparse, json, socket, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

ap = argparse.ArgumentParser()
ap.add_argument("script", nargs="?")
ap.add_argument("start_url")
ap.add_argument("--args", default=None)
ap.add_argument("--out", default=None)
ap.add_argument("--profile", default=None)
ap.add_argument("--wait", type=float, default=10)
ap.add_argument("--timeout", type=float, default=900)
ap.add_argument("--script-inline", default=None)
ap.add_argument("--keep-open", action="store_true")
a = ap.parse_args()

code = a.script_inline if a.script_inline else Path(a.script).read_text(encoding="utf-8")
args = json.loads(a.args) if a.args else None
prof = Path("C:/chip_docs/browser_profiles") / (a.profile or urlparse(a.start_url).hostname or "default")
prof.mkdir(parents=True, exist_ok=True)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
chrome = subprocess.Popen([CHROME, f"--remote-debugging-port={port}", f"--user-data-dir={prof}", "--no-first-run",
                           "--no-default-browser-check", "--window-size=1280,900", "about:blank"])
result, err = None, None
try:
    for _ in range(40):
        try:
            socket.create_connection(("127.0.0.1", port), 0.5).close()
            break
        except OSError:
            time.sleep(0.5)
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        page = b.contexts[0].pages[0] if b.contexts[0].pages else b.contexts[0].new_page()
        page.set_default_timeout(a.timeout * 1000)
        page.goto(a.start_url, timeout=120000, wait_until="domcontentloaded")
        time.sleep(a.wait)
        try:
            if a.script_inline:
                result = page.evaluate(f"async () => ({code})")
            else:
                result = page.evaluate(f"async (arg) => ({code})(arg)", args)
        except Exception as e:
            err = str(e)
        if not a.keep_open:
            b.close()
finally:
    if not a.keep_open:
        chrome.terminate()
if err:
    print("ERROR", err[:2000])
    sys.exit(1)
text = json.dumps(result, ensure_ascii=False, indent=1)
if a.out:
    Path(a.out).write_text(text, encoding="utf-8")
if isinstance(result, list):
    print(f"{len(result)} rows")
elif isinstance(result, dict) and "total" in result:
    print(f"total {result['total']}")
print(text[:4000])
