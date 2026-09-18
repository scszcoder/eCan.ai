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
| `gui/ipc/w2p_handlers/browser_profile_handler.py` | the `browser_profile.*` IPC facade. Its DTO is the GUI's contract and is deliberately not the registry's storage shape |
| `gui_v2/src/pages/Settings/components/BrowserProfiles.tsx` | Settings -> Browser Profiles: CRUD, proxy, fingerprint, launch/stop, import |
| `cli/browser/commands.py` | `ecan browser list / show / import / remove` |

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

## Managing profiles

**Settings -> Browser Profiles** is the full surface: create, edit, launch,
stop, import and remove, with the proxy and fingerprint on the same form and a
live status column. Launching from there is also the better place to do it --
the SOCKS relay lives in whichever process starts the browser, so one opened by
the app keeps a working proxy for as long as the app runs, while one opened by
a single CLI command loses its relay when that command exits.

The page talks to `browser_profile.*` over IPC, and that handler
(`gui/ipc/w2p_handlers/browser_profile_handler.py`) is a deliberate boundary:
its DTO is not the registry's storage shape, the proxy password never crosses
it (only `has_password`), and `status` is read from the live browser on every
call rather than cached. If the model behind profiles changes -- a cloud half,
a vendor driven in place, a different fingerprint approach -- the mapping
functions absorb it and the page does not change.

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
pick the identity from the **Browser Profile** dropdown, which lists what is
registered on this machine. (A skill authored elsewhere may name a profile this
machine does not have; the node keeps that value and marks it rather than
silently blanking the field.) That is the whole configuration -- no CDP port,
no vendor app, no API key. The node launches the profile, attaches
over CDP, and injects the fingerprint the profile names (if it names one).

Several nodes in one skill share the single running browser; it closes when the
last of them is shut down, not the first.

## Using it from code

    from agent.ec_skills.browser_use_extension.fingerprint import (
        fingerprint_browser as fb)

    br = fb.launch_profile("etsy")   # no port: one is chosen, see below
    ...                              # drive br.cdp_url
    fb.close_profile("etsy")         # flushes cookies; do NOT kill the process

## The CDP port

**There is no fixed debug port, and you should not pick one.** Profiles are
separate identities and several run at once, so a constant would collide.
`launch_profile()` takes a free port unless you name one, and hands back the
endpoint:

    br = fb.launch_profile("etsy")
    br.cdp_url      # 'http://127.0.0.1:63283'
    br.debug_port   # 63283

A node passes its CDP Port field through if you set one, and 0 (the default)
otherwise.

To find a browser **another process** started — the GUI asking about a profile
a skill run opened, a skill run finding the one the GUI opened — read the port
file Chromium's user-data-dir carries:

    C:\ecan_browser_data\<id>_<salt>\.ecan_cdp.json
    {"port": 63283, "pid": 43256, "relay_port": 63294, "started": 1789752145}

or, better, ask:

    fb.profile_status("etsy")
    # {'running': True, 'port': 63283, 'cdp_url': 'http://127.0.0.1:63283',
    #  'pid': 43256, 'relay_port': 63294, 'relay_alive': True,
    #  'started': 1789752145, 'owned': False}

`owned` is whether *this* process launched it, and it is the field that
matters: **only the launcher holds the SOCKS relay.** When `running` is true
and `relay_alive` is false, the browser is up but its proxy is gone with the
process that started it — it would now egress from this machine's own address.
`launch_profile` refuses to attach in that state rather than leak it, and
`close_profile` will still shut it down cleanly from any process.

Command line:

    ecan browser list          # a RUNNING column
    ecan browser show etsy     # port, pid, relay, and whether the relay is up

The registry lives in `browser_profiles.json` (git-ignored) and the profile
directories under `C:\ecan_browser_data\<id>_<salt>` — short and outside
AppData on purpose, because Chromium profile paths get deep enough to hit
Windows MAX_PATH and the caches are hundreds of MB.

**The relay belongs to the process that launched the browser.** A second
process can attach to a running profile, but if the launcher has exited its
relay is gone and the browser would silently egress from this machine's own IP;
`launch_profile` refuses to attach in that case rather than leak the address.

## Status

As of 2026-09-18, **every phase of the plan (0–4) is built, and profiles have
a management GUI** (Settings → Browser Profiles) alongside the CLI.

The GUI is built and compiles into the bundle, but it has not yet been driven
in the running app — the handlers were exercised directly and the page was
type-checked and built, not clicked through.

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

**The reboot leg of the gate passed on 2026-09-18.** After a real Windows
restart, `launch_profile("etsy")` landed on the Shop Manager dashboard signed
in, through the proxy, about three seconds after launch — no login prompt, no
re-verification.

What remains is not code. The plan gates trusting any of this on a profile
surviving a reboot **and a week of idleness**; only the first half is now
evidence. Fingerprint parity with the vendor is not achievable and our
stealth-JS substitute is still untested over weeks, which is the risk that
would invalidate the approach, and no amount of tooling addresses it. Re-run
the same check around 2026-09-25 without touching the profile in between.
