# Own Fingerprint Browser — pointer

The design and plan live in the **`eCan_lambda`** repo:

    docs/OWN_FINGERPRINT_BROWSER_PLAN.md

It is kept there because it is backend/infra design and carries operational
detail — bucket layouts, pod lifecycle, and proxy topology — that does not
belong in this repo.

## What is in this repo

| path | what |
|---|---|
| `agent/ec_skills/browser_use_extension/fingerprint/profile_registry.py` | the registry: which user-data-dir, proxy, browser binary and fingerprint belong to one identity. Proxy passwords go to the OS keyring, never to the JSON. |
| `agent/ec_skills/browser_use_extension/fingerprint/fingerprint_browser.py` | `launch_profile()` / `close_profile()` — owns the proxy relay's lifetime, attaches to an already-running browser instead of racing it, and closes gracefully so the session is flushed |
| `agent/ec_skills/browser_use_extension/fingerprint/fingerprint_service.py` | fingerprint profile CRUD, stealth JS preparation, `inject_stealth` over CDP. Already called by the browser node. |
| `agent/ec_skills/browser_use_extension/fingerprint/socks_relay.py` | local no-auth SOCKS5 front for an authenticated upstream proxy |
| `agent/ec_skills/browser_use_extension/fingerprint/stealth_injection.js` | the injected stealth script |
| `agent/ec_skills/browser_use_extension/fingerprint/profiles/` | bundled fingerprint profiles |

## Three findings worth knowing before touching any of it

1. **Chromium cannot authenticate to a SOCKS5 proxy.** There is no
   command-line form, and the extension `onAuthRequired` hook that rescues
   authenticated HTTP proxies never fires for SOCKS. Anti-detect vendors solve
   it by patching the browser; we use `socks_relay.py`.
2. **An anti-detect profile's real config is only on the RUNNING process's
   command line.** The vendor's app data holds the Electron app and browser
   binaries, not the profiles — and the process may not be named `chrome.exe`.
3. **Cookies do not cross platforms.** A Windows profile's cookie key is
   wrapped with DPAPI and bound to the Windows account; a Linux pod cannot read
   it, and Chromium treats the cookies as empty rather than erroring. This is
   the single biggest constraint on the cloud design — see the plan.

## Using it

    from agent.ec_skills.browser_use_extension.fingerprint import (
        fingerprint_browser as fb)

    br = fb.launch_profile("etsy", debug_port=9668)
    ...                         # drive br.cdp_url
    fb.close_profile("etsy")    # flushes cookies; do NOT kill the process

The registry lives in `browser_profiles.json` (git-ignored) and the profile
directories under `C:\ecan_browser_data\<id>_<salt>` — short and outside
AppData on purpose, because Chromium profile paths get deep enough to hit
Windows MAX_PATH and the caches are hundreds of MB.

**The relay belongs to the process that launched the browser.** A second
process can attach to a running profile, but if the launcher has exited its
relay is gone and the browser would silently egress from this machine's own IP;
`launch_profile` refuses to attach in that case rather than leak the address.

## Status

As of 2026-09-17, plan phases 0–2 are built and verified end to end against the
live Etsy profile: launch → attach from a second process → egress confirmed at
the proxy exit (Pasadena, CA) → close → cold relaunch, still signed in to the
Shop Manager dashboard with no login prompt.

Not built: phase 3 (browser-node integration, so a skill can name a profile
instead of a port) and phase 4 (import tooling for vendor profiles — the Etsy
one was migrated by hand).
