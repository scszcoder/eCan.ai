# Emulation harness

Moved here from the git-ignored `customer_logs/emulation/` on 2026-09-19 so it
is actually in version control. See **`docs/EMULATION_HARNESS.md`** for what it
is, how to run it, and what it does not yet do.

`HARNESS_README.md` and `CDP_CHAOS_USAGE.md` beside this file are the original
in-depth docs and still apply — with one correction: paths in them refer to the
old `customer_logs/emulation/` location.

Quick start (full version in `docs/EMULATION_HARNESS.md` §4):

```bash
python tools/emulation/server.py            # http://127.0.0.1:9876/im.jinritemai.com/
./check_monitor.ps1                         # confirm MONITOR LIVE before trusting a run
python tools/emulation/measure.py --label clean
```

One difference from the original directory: `sample0.png` here is a **generated
placeholder**. The original was a real screenshot captured from the live site
and is deliberately not tracked; it only backs the 图文 image bubbles, and any
image of the right shape does that job.
