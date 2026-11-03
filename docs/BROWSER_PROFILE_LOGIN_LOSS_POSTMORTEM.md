# Browser Profile Login Loss Post-Mortem (抖店, KEN 2026-10-29)

**Status: FIXED in code** — commits `42ea6f0cf`, `21636467f`, `fc8f2e7f4` (builds ycx and later).
The store itself still needed a manual re-login: the deleted login could not be recovered.

**Rule that came out of it:** eCan may at most **copy or rename** a browser profile. It never
resets, wipes or deletes one — not automatically, not as a fallback. A profile *is* a store's
login; losing it takes that store's 客服 offline until a person signs in again.

---

## 1. What happened

| Time (KEN) | Event |
|---|---|
| 02:54 | Upgrade install (ycu). The installer's stop step force-closed eCan ("still running after 25s -- forcing it closed"). |
| 02:56:15 | eCan starts the 抖店 fingerprint browser `douyin-55b2a7fb-login`. The new Chromium exits at once with **code 0** and no debug port. |
| 02:56:22 | Self-heal reads that as a crash: clears the profile's cache (incl. `Sessions`, `Session Storage`), retries — code 0 again. |
| 02:56:32 | Self-heal "resets" the profile. Renaming the folder aside **fails** (still locked), so the fallback `shutil.rmtree(..., ignore_errors=True)` **deletes it**. |
| 02:56:36 | A launch on the now-empty folder succeeds. 抖店后台 (fxg) and 飞鸽 show 登录已过期 — **抖店客服 down**. 拼多多 unaffected. |
| 03:06 | The next 商品上架 run stops with 未登录. Only an old `.corrupt-` copy from 10-16 existed; no cookie backup. |

## 2. Root causes (ours, all three)

1. **A busy profile was classified as corrupt.** Chromium exits with code 0 when another
   instance already owns the user-data-dir — it hands its launch over and quits. Here the old
   browser (or its children) still held the folder after the forced stop. Nothing was wrong with
   the profile.
2. **The self-heal escalated to a reset automatically.** Its ladder was retry → clear cache →
   reset profile, with no person in the loop, and the cache clear included session data.
3. **The reset's fallback deleted.** Its docstring promised "the old copy is renamed, not
   deleted"; when the rename failed it `rmtree`'d instead. A folder that will not move is almost
   always *in use*, i.e. the worst moment to delete it.

Contributing: the install force-killed eCan, which can leave the store browser holding its
profile while the new eCan starts.

## 3. Fixes

- **Code 0 = `_ProfileBusy`, not a crash** (`fingerprint_browser.py`): ask the leftover browser to
  close (a request, never a kill), wait for every process on that profile to exit, retry; if it
  is still held, fail with "nothing in the profile was changed".
- **No automatic reset** — `_reset_profile_dir` is gone. A profile that still crashes after a
  cache clear is left exactly as it is; the error tells a person what to do.
- **Cache clear is caches only**: GPU / shader / code caches and Crashpad. `Sessions`,
  `Session Storage` and `Service Worker` (site login state) are never touched, and nothing is
  touched while any process runs the profile.
- **Live locks are kept** (`profile_lock_cleaner.py`): lock files of a running browser are not
  removed — two browsers on one profile is what really corrupts it.
- **Importing over a profile renames the old copy** (`vendor_import.py`, `.replaced-<ts>`), and
  stops with an error if it cannot.
- Tests: `tests/unit/test_fingerprint_profile_self_heal.py`,
  `tests/unit/test_profile_lock_cleaner_orphans.py`.

## 4. Checklist for any code that touches a profile folder

- [ ] Does it delete, `rmtree`, reset or empty a `user_data_dir` or anything inside it other than
      pure caches? → Not allowed. Rename aside instead.
- [ ] If the rename fails, does it stop with an error (never fall back to deleting)?
- [ ] Does it check that no process runs the profile before touching anything in it?
- [ ] Is "the browser exited" distinguished by exit code? Code 0 without a debug port = busy.
- [ ] Is anything that needs a fresh login a person's explicit decision, not an automatic step?

## 5. Still open

- Installs force-closing eCan can leave store browsers behind; the busy handling now copes, but
  a gentler stop (close store browsers first, then eCan) would avoid the race entirely.
- No cookie backup exists. A periodic encrypted copy of each store profile's cookie store
  would have made this recoverable without a re-login.
