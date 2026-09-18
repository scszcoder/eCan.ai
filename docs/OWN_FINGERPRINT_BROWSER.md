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

## Importing a profile

    ecan browser import --from adspower --profile kq15tpi --as etsy_main
    ecan browser list

The vendor profile is started briefly and then stopped — its user-data-dir is
only visible on the running process's command line, not through their API,
while the proxy credentials are only in the API and never on the command line.
Caches are excluded, so a ~760MB profile lands at ~20MB.

Two things are deliberately not imported: their browser binary (a patched
Chromium we cannot drive) and their fingerprint (an opaque blob only that
binary reads). Pass `--fingerprint win_chrome_02` to name one of ours.

## Using it from a skill

In a browser-automation node, set **Browser** to `eCan Fingerprint Browser` and
put the profile id in **Browser Profile**. That is the whole configuration --
no CDP port, no vendor app, no API key. The node launches the profile, attaches
over CDP, and injects the fingerprint the profile names (if it names one).

Several nodes in one skill share the single running browser; it closes when the
last of them is shut down, not the first.

## Using it from code

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

As of 2026-09-17, **every phase of the plan (0–4) is built.**

Phases 0–2 were verified end to end against the live Etsy profile: launch →
attach from a second process → egress confirmed at the proxy exit (Pasadena,
CA) → close → cold relaunch, still signed in to the Shop Manager dashboard with
no login prompt.

Phase 3 was verified through `BrowserManager`, the way the node reaches it:
acquire → CDP endpoint + browser-use session → a second acquire reuses the
running browser → shutting down the first record leaves it alive → shutting
down the last closes it gracefully.

Phase 4 was verified by importing the live AdsPower Etsy profile end to end:
23MB copied in 8s, launched from the new directory, and landed on the Shop
Manager dashboard signed in — on a profile directory that had existed for
seconds.

What remains is not code. The plan gates trusting any of this on proving a
profile survives a reboot and a week of idleness, because fingerprint parity
with the vendor is not achievable and our stealth-JS substitute is untested
over time. That is the risk that would invalidate the approach, and no amount
of tooling addresses it.
