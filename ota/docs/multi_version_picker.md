# Multi-version picker + per-user release filtering

**Status:** Design draft (not implemented). Written 2026-05-04.
**Owner:** (assign before implementation)
**Scope:** Help → "Check for new release" flow in `MenuManager.show_update_dialog`.

---

## 1. Why

Today's OTA flow assumes a single linear release timeline (`v0.9.11` →
`v0.9.12` → ...). The application will soon publish **per-user builds**
whose version string encodes both the user and the build timestamp, e.g.:

```
songc_v26.05.03.22.22     # user 'songc', built 2026-05-03 22:22
alice_v26.05.04.09.11     # user 'alice', built 2026-05-04 09:11
v0.9.12                   # universal build, visible to everyone
```

The user-visible goals:

1. User `songc@yahoo.com` clicking **Help → Check for new release** must
   only see items tagged for `songc` plus universal items — never
   `alice_*` builds.
2. If multiple `songc_*` builds exist that are newer than the installed
   version, the dialog must list **all** of them and let the user pick
   which one to install (not just the freshest).
3. A user who is logged out (or whose email we can't resolve) must still
   see universal releases and nothing else.

## 2. How it works today (so we know what we're changing)

| Layer | File | Behavior |
|---|---|---|
| Menu action | `@gui/menu_manager.py:798-940` — `MenuManager.show_update_dialog(manual=True)` | Spawns a background `CheckUpdateThread`, calls `ota_updater.check_for_updates(return_info=True)`, routes result to a single-version confirmation dialog or a "you're up to date" dialog. |
| Orchestrator | `@ota/core/updater.py:92-160` — `OTAUpdater.check_for_updates` | Delegates to a per-OS `platform_updater.check_for_updates(silent, return_info=True)`. No awareness of user identity. |
| Platform fetcher | `@ota/core/platforms.py:67` — `MacOSUpdater._check_via_appcast` (+ Windows / Linux twins) | Resolves appcast URL via `OTAConfig.get_appcast_url(platform, arch, language)`, fetches XML, calls `parse_appcast` then `select_latest_for_platform`. |
| URL builder | `@ota/config/loader.py:152` — `OTAConfig.get_appcast_url` | Keys: platform + arch + language only. **No user dimension.** |
| Parser | `@ota/core/appcast.py:39-113` — `parse_appcast` | Returns `List[AppcastItem]` with `version`, `url`, `os`, `arch`, `length`, signature, release notes, pubDate. **No `user_prefix` field.** |
| Selector | `@ota/core/appcast.py:248-271` — `select_latest_for_platform` | Filters by `os`/`arch`, sorts desc by `compare_versions`, returns **the single item with the highest version that is strictly greater than `current_version`**. Older-but-still-newer items are silently dropped. |
| Comparator | `@ota/core/appcast.py:182-237` — `compare_versions` | Handles arbitrary multi-segment numeric versions, optional leading `v`, prerelease tags. **`26.05.03.22.22` parses as `[26, 5, 3, 22, 22]` and compares correctly with no math changes.** |
| GUI | `@gui/menu_manager.py:883-921` + `ota/gui/dialog.py` — `UpdateDialog`, `VersionCheckDialog` | Single-version confirmation; no list picker. |

## 3. Where user identity lives

`auth/auth_manager.py:240-241` already derives a display name from
`email.split('@')[0]` as a fallback. The user profile is on
`AppContext.get_instance().login.user_profile` once the user is logged
in. The OTA layer does not consult it today.

## 4. Design

### 4.1 Server-side strategy — recommended: **(b) prefix-by-version-string**

Two candidates considered:

- **(a) Per-user appcast file**: `appcast-<plat>-<arch>-<user>.xml`
  next to the existing `appcast-<plat>-<arch>-<lang>.xml`.
  - Pros: clean ACL — a user's client never even sees other users'
    metadata; no client-side parsing heuristics.
  - Cons: build/publish pipeline must emit per-user files; harder to
    "promote" a build from user-specific to universal later.

- **(b) Single appcast, version-prefix encodes the user** (e.g.
  `songc_v26.05.03.22.22`). Items without an underscore prefix (or with
  a prefix that looks numeric, i.e. is part of the version) are
  universal.
  - Pros: zero appcast schema change; zero build-pipeline change beyond
    naming new builds; promoting/demoting a build is just a rename in
    the manifest.
  - Cons: every user's client downloads every item's metadata (release
    notes, sizes, URLs). Not a real security boundary — the download
    URL is presumably S3 pre-signed or signed via Ed25519 anyway.

**Pick (b)** for v1. If we ever need a hard ACL (e.g. confidential
internal builds), add an optional `sparkle:user` XML attribute later
and fall back to the prefix parse when it's absent.

### 4.2 Version string grammar

```
<item-version>       ::= [ <user-prefix> "_" ] [ "v" ] <version-core>
<user-prefix>        ::= [a-z0-9][a-z0-9._-]*     ; must contain at least one non-digit
<version-core>       ::= <dotted-int> [ "-" <prerelease> ] [ "+" <build> ]
<dotted-int>         ::= <int> ( "." <int> )*
```

The **"must contain at least one non-digit"** rule on the prefix is
what disambiguates `songc_v26.05.03.22.22` (prefix=`songc`) from
`26.05.03.22.22` (no prefix) without requiring a schema change.
Existing releases like `v0.9.11` have no `_` and therefore `user_prefix
= None` → universal.

Collisions / edge cases:
- Prefix with digits is fine (`songc2_v...`), as long as at least one
  character is non-numeric.
- A build that legitimately needs a leading word in its version (e.g.
  `rc_v1.0`) would collide. Mitigation: forbid the literal words `rc`,
  `beta`, `alpha`, `preview` as user prefixes — prereleases belong
  after the `-` in the version core (`v1.0-rc.1`), which `compare_versions`
  already handles.
- Case-insensitive match on the prefix (`Songc_v...` matches
  `songc@...`); we normalize both sides with `.lower()`.

### 4.3 Parser changes — `ota/core/appcast.py`

Add `user_prefix: Optional[str]` to `AppcastItem`. Populate in
`parse_appcast`:

```python
def _split_user_prefix(raw_version: str) -> Tuple[Optional[str], str]:
    """'songc_v26.05.03.22.22' -> ('songc', 'v26.05.03.22.22')
       '26.05.03.22.22'         -> (None, '26.05.03.22.22')"""
    if "_" not in raw_version:
        return None, raw_version
    head, rest = raw_version.split("_", 1)
    # Prefix must contain at least one non-digit char; otherwise the
    # '_' is part of the version itself and we leave it alone.
    if not head or head.isdigit() or head.replace(".", "").isdigit():
        return None, raw_version
    return head.lower(), rest
```

No change to `compare_versions` (it already strips leading `v` and
ignores the prefix since the prefix is peeled off before comparison).

### 4.4 Selector changes — `ota/core/appcast.py`

Add a list-returning selector; keep the old one as a wrapper so no
existing caller breaks.

```python
def select_eligible_versions(
    items: List[AppcastItem],
    platform_tag: Optional[str],
    current_version: str,
    arch_tag: Optional[str] = None,
    user_prefix: Optional[str] = None,
) -> List[AppcastItem]:
    """Return items > current_version, filtered by os/arch AND user_prefix,
    sorted newest-first. user_prefix=None means 'logged-out / unknown user'
    and filters to universal items only."""

def select_latest_for_platform(...) -> Optional[AppcastItem]:
    eligible = select_eligible_versions(...)
    return eligible[0] if eligible else None
```

Filter rule (matches the two real use cases):

| item.user_prefix | user_prefix arg | visible? |
|---|---|---|
| `None` (universal) | anything | yes |
| `'songc'` | `'songc'` | yes |
| `'songc'` | `'alice'` | no |
| `'songc'` | `None` (logged out) | no |

### 4.5 Updater plumbing — `ota/core/updater.py`, `ota/core/platforms.py`

1. `OTAUpdater.__init__` resolves `self.user_prefix` once:
   ```python
   self.user_prefix = self._resolve_user_prefix()

   def _resolve_user_prefix(self) -> Optional[str]:
       try:
           from utils.app_context import AppContext
           prof = AppContext.get_instance().login.user_profile or {}
           email = (prof.get("email") or "").strip().lower()
           if "@" in email:
               return email.split("@", 1)[0]
       except Exception:
           pass
       return None
   ```
   Must be lazy/defensive — this code runs during `OTAUpdater` init,
   which can happen before login during auto-check bootstrap.

2. Re-resolve on every `check_for_updates(...)` call (user might have
   logged in between init and the manual check):
   ```python
   self.user_prefix = self._resolve_user_prefix()
   ```

3. Platform updaters pass `user_prefix` into `select_eligible_versions`
   and return it in `update_info`:
   ```python
   update_info = {
       "latest_version": eligible[0].version if eligible else None,
       "available_versions": [
           {"version": it.version, "url": it.url, "size": it.length,
            "pub_date": it.pub_date, "release_notes_html": it.description_html,
            "user_prefix": it.user_prefix}
           for it in eligible
       ],
       # keep all existing keys (download_url, signature, etc.) pointing at
       # eligible[0] so current call sites remain correct.
   }
   ```
   **Back-compat rule:** every existing consumer that reads
   `update_info["latest_version"]` / `update_info["version"]` / the
   single-item fields must keep working. Anyone new gets
   `update_info["available_versions"]`.

### 4.6 GUI changes — `gui/menu_manager.py` + `ota/gui/dialog.py`

In `on_check_completed` inside `MenuManager.show_update_dialog`:

```python
versions = (update_info or {}).get("available_versions") or []
if has_update and len(versions) > 1:
    # New picker dialog
    from ota.gui.version_picker_dialog import VersionPickerDialog
    picker = VersionPickerDialog(self.main_window, versions, ota_updater)
    picker.exec()
elif has_update and len(versions) == 1:
    # Existing single-version flow — no UX regression
    web_gui._show_update_confirmation(versions[0]["version"], update_info, is_manual=True)
else:
    VersionCheckDialog(self.main_window, is_latest=True, version=current_version).exec()
```

New `VersionPickerDialog` (to be added in `ota/gui/version_picker_dialog.py`):

- `QListWidget` with one row per eligible version, showing
  `<version>  ·  <pub_date>  ·  <size>  ·  <first-line-of-release-notes>`.
- Rows for items with a `user_prefix` are visually flagged with a small
  badge (e.g. `[songc]`) so the user knows this is a user-specific build.
- Default-selects the newest (index 0) so one-click **Install** still
  works for the common case.
- **Install** button wires the selected `AppcastItem`'s URL/signature
  into the existing download flow (reuse whatever
  `_show_update_confirmation` calls internally — most likely a
  `download_manager.start_download(item)` equivalent).
- **Release notes** shown in a side panel or on-select expansion; this
  is where we recover the information density we lose by going from a
  single big confirmation card to a compact list.

### 4.7 Auto-check behavior

`OTAUpdater.start_auto_check_in_background` currently notifies the GUI
whenever a newer version is detected and the user hasn't ignored it
(`version_ignore.is_ignored(latest)`). With multiple eligible versions
the sane default is:

- Badge the menu once (as today), using `versions[0]` (newest).
- If the user clicks the notification / menu, open the **picker** dialog
  (not the single-version confirmation) so they see the full list.
- `version_ignore` stays per-version-string, so ignoring
  `songc_v26.05.03.22.22` does not suppress notifications about
  `songc_v26.05.04.09.11`.

### 4.8 Config / env knobs

- `ota.core.updater.OTAUpdater._resolve_user_prefix` honors an
  environment override `ECAN_OTA_USER_PREFIX` so we can test non-logged-in
  scenarios and alpha-gate per-user builds without touching Cognito.
- Empty string in the env var == "universal only" (same as logged out).

## 5. Migration plan

1. **Land parser + selector changes with full back-compat.** Existing
   appcasts (no `_` in any version) behave exactly as today. Ship this
   first as its own PR with unit tests.
2. **Add `user_prefix` resolution in updater + pass-through to `update_info`.** Still no GUI change; `latest_version` remains the single newest eligible item.
3. **Add `VersionPickerDialog` and wire the `len(versions) > 1` branch.**
4. **Publish the first `songc_v*` build and verify end-to-end on staging
   before production.**

## 6. Tests

Unit tests to add in `tests/ota/test_appcast.py` (create if missing):

- `_split_user_prefix` for: `'v0.9.11'`, `'0.9.11'`, `'songc_v26.05.03.22.22'`,
  `'songc_26.05.03.22.22'`, `'26_05_03'` (leading numeric → no prefix),
  `'Rc_v1.0'` (forbidden prefix → no prefix), `'songc2_v1'` (digits ok
  if mixed), `''`.
- `compare_versions('26.05.03.22.22', '26.05.04.09.11')` → negative.
- `compare_versions('0.9.11', '26.05.03.22.22')` → negative. (Confirms
  future-dated builds sort above historical semver correctly, so users
  aren't surprised.)
- `select_eligible_versions` matrix:
  - current=`0.9.11`, user=`None`, items=[universal 0.9.10, universal 0.9.12, `songc_v26.05.03`] → returns `[0.9.12]`.
  - current=`0.9.11`, user=`'songc'`, same items → returns
    `[songc_v26.05.03, 0.9.12]` newest-first.
  - current=`0.9.11`, user=`'alice'`, same items → returns `[0.9.12]`.
  - current=`26.05.03.22.22`, user=`'songc'`, items=[`songc_v26.05.03.22.22`, `songc_v26.05.04.09.11`] → returns `[songc_v26.05.04.09.11]` only (current is excluded).

Smoke test (manual):

1. Put three items in a local appcast XML: one universal newer,
   two `songc_v*` newer, one `alice_v*` newer.
2. Launch app logged in as `songc@yahoo.com`, click Help → Check for
   new release → expect 3 rows in the picker, `alice_*` absent.
3. Launch app with `ECAN_OTA_USER_PREFIX=alice` → expect 2 rows
   (universal + `alice_*`), `songc_*` absent.
4. Launch app logged out / with no email → expect 1 row (universal).

## 7. Out of scope

- Server-side build pipeline changes (producing `<user>_v<yy.mm.dd.hh.mm>`
  artifacts). This doc assumes they exist.
- Downgrade flow. `select_eligible_versions` only returns items
  **strictly greater** than the current version; installing an older
  user-specific build would need a separate "show all builds including
  older" toggle in the picker.
- ACL enforcement. If a `songc_*` URL is not pre-signed, any user who
  knows the URL pattern can download it. Tightening that is a server
  concern, not a client one.
