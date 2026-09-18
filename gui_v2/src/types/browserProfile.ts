/**
 * Browser profiles — one logged-in identity on one site.
 *
 * A profile binds four things that have to travel together: the user-data-dir
 * holding the session, the proxy that site has seen it egress through, the
 * fingerprint it presents, and the Chromium build that wrote the profile.
 *
 * These types mirror the DTO in `gui/ipc/w2p_handlers/browser_profile_handler.py`,
 * which is deliberately NOT the storage shape. The registry file can change
 * without this changing. Two properties of that boundary are load-bearing:
 *
 *   - the proxy password never arrives here, only `has_password`;
 *   - `status` is read from the live browser on every call, so it is never a
 *     cached value the page has to invalidate.
 *
 * Do not widen these to match `browser_profiles.json` — if a field is missing,
 * add it to the DTO on the Python side so the CLI and the GUI keep agreeing.
 */

/** Live state of a profile's browser. All-false when it is not running. */
export interface BrowserProfileStatus {
  profile_id?: string;
  running: boolean;
  port: number;
  cdp_url: string;
  pid: number;
  relay_port: number;
  /**
   * Whether the local SOCKS relay in front of an authenticated proxy is up.
   * The relay lives in the process that launched the browser, so `running`
   * with `relay_alive: false` means the browser is open but now egressing
   * from this machine's own address — the one thing a profile must not do.
   */
  relay_alive: boolean;
  started?: number;
  /** Whether the desktop app launched it, as opposed to a CLI or skill run. */
  owned: boolean;
}

export interface BrowserProfileProxy {
  scheme: string;
  host: string;
  port: number;
  username: string;
  /** The password is in the OS keyring. This is all the UI is told about it. */
  has_password: boolean;
  bypass: string[];
}

export interface BrowserProfile {
  id: string;
  label: string;
  domain: string;
  locale: string;
  /** Assigned by the registry on create; the UI shows it but cannot move it. */
  user_data_dir: string;
  browser: { path: string; version: string };
  proxy: BrowserProfileProxy;
  fingerprint_profile: string;
  imported_from: { vendor?: string; profile_id?: string };
  status: BrowserProfileStatus;
}

/** A bundled or user fingerprint preset a profile can present. */
export interface FingerprintPreset {
  id: string;
  name: string;
  description: string;
  platform: string;
  locale: string;
  timezone: string;
  source: 'bundled' | 'user' | string;
}

/**
 * An anti-detect browser we can import from. Served as data rather than
 * hard-coded in the page, so supporting a second vendor is a backend change.
 */
export interface BrowserVendor {
  id: string;
  name: string;
  /** What that vendor calls a profile id ("Profile serial" for AdsPower). */
  id_label: string;
  default_api_port: number;
}

export interface BrowserProfileOptions {
  fingerprints: FingerprintPreset[];
  /** What a profile with no recorded binary would run today. */
  default_browser_path: string;
  vendors: BrowserVendor[];
}

export const emptyBrowserProfile = (): BrowserProfile => ({
  id: '',
  label: '',
  domain: '',
  locale: 'en-US',
  user_data_dir: '',
  browser: { path: '', version: '' },
  proxy: { scheme: 'socks5', host: '', port: 0, username: '', has_password: false, bypass: [] },
  fingerprint_profile: '',
  imported_from: {},
  status: {
    running: false, port: 0, cdp_url: '', pid: 0,
    relay_port: 0, relay_alive: false, owned: false,
  },
});
