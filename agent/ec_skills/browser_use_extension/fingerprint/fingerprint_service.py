"""Fingerprint profile management and stealth JS injection for browser_automation.

Provides:
- load_profile / list_profiles / get_random_profile  — profile CRUD
- prepare_stealth_js — placeholder substitution for stealth_injection.js
- inject_stealth — inject prepared JS into a live browser session via CDP
"""

import json
import os
import random
import hashlib
from pathlib import Path
from typing import Optional

from utils.logger_helper import logger_helper as logger

# ── Directories ──────────────────────────────────────────────────────────────

# Bundled profiles ship with the app (read-only at runtime)
_BUNDLED_PROFILES_DIR = Path(__file__).parent / "profiles"

# User-managed profiles live under appdata (writable)
_user_profiles_dir: Optional[Path] = None


def _get_user_profiles_dir() -> Path:
    """Lazily resolve the user-writable profiles directory."""
    global _user_profiles_dir
    if _user_profiles_dir is None:
        try:
            from config.app_info import app_info
            _user_profiles_dir = Path(app_info.appdata_path) / "fingerprint_profiles"
        except Exception:
            _user_profiles_dir = Path.home() / ".ecan" / "fingerprint_profiles"
        _user_profiles_dir.mkdir(parents=True, exist_ok=True)
    return _user_profiles_dir


# ── Profile loading ──────────────────────────────────────────────────────────

def list_profiles() -> list[dict]:
    """Return all available fingerprint profiles (bundled + user).

    Each entry is the parsed JSON dict with an extra ``_source`` key
    (``"bundled"`` or ``"user"``).
    """
    profiles = []
    seen_ids = set()

    # User profiles take priority (loaded first so they shadow bundled ones
    # with the same id)
    for directory, source in [
        (_get_user_profiles_dir(), "user"),
        (_BUNDLED_PROFILES_DIR, "bundled"),
    ]:
        if not directory.is_dir():
            continue
        for fp in sorted(directory.glob("*.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                pid = data.get("id", fp.stem)
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)
                data["id"] = pid
                data["_source"] = source
                data["_path"] = str(fp)
                profiles.append(data)
            except Exception as exc:
                logger.warning(f"[Fingerprint] Failed to load {fp}: {exc}")

    return profiles


def load_profile(name_or_id: str) -> Optional[dict]:
    """Load a single profile by id or filename stem.

    Checks user directory first, then bundled.
    """
    for directory in [_get_user_profiles_dir(), _BUNDLED_PROFILES_DIR]:
        if not directory.is_dir():
            continue
        # Try exact filename match first
        candidate = directory / f"{name_or_id}.json"
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                pass
        # Fallback: scan by id field
        for fp in directory.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                if data.get("id") == name_or_id or data.get("name") == name_or_id:
                    return data
            except Exception:
                continue
    return None


def get_random_profile(seed: str = "") -> dict:
    """Pick a random profile.  If *seed* is given, the choice is deterministic."""
    profiles = list_profiles()
    if not profiles:
        logger.warning("[Fingerprint] No profiles available, returning minimal default")
        return _minimal_default_profile()
    if seed:
        idx = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(profiles)
        return profiles[idx]
    return random.choice(profiles)


def save_profile(profile: dict) -> str:
    """Save a profile to the user directory.  Returns the file path."""
    pid = profile.get("id") or profile.get("name", "custom")
    safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in str(pid))
    dest = _get_user_profiles_dir() / f"{safe_name}.json"
    # Strip internal keys before saving
    to_save = {k: v for k, v in profile.items() if not k.startswith("_")}
    dest.write_text(json.dumps(to_save, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"[Fingerprint] Saved profile '{pid}' to {dest}")
    return str(dest)


def delete_profile(name_or_id: str) -> bool:
    """Delete a user-managed profile.  Returns True if deleted."""
    user_dir = _get_user_profiles_dir()
    # Try exact filename
    candidate = user_dir / f"{name_or_id}.json"
    if candidate.is_file():
        candidate.unlink()
        logger.info(f"[Fingerprint] Deleted profile: {candidate}")
        return True
    # Scan by id
    for fp in user_dir.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if data.get("id") == name_or_id:
                fp.unlink()
                logger.info(f"[Fingerprint] Deleted profile: {fp}")
                return True
        except Exception:
            continue
    return False


# ── Stealth JS preparation ──────────────────────────────────────────────────

_STEALTH_JS_PATH = Path(__file__).parent / "stealth_injection.js"
_stealth_js_template: Optional[str] = None


def _load_stealth_template() -> str:
    global _stealth_js_template
    if _stealth_js_template is None:
        _stealth_js_template = _STEALTH_JS_PATH.read_text(encoding="utf-8")
    return _stealth_js_template


def prepare_stealth_js(profile: dict) -> str:
    """Substitute placeholders in stealth_injection.js with profile values.

    All ``__PLACEHOLDER__`` tokens in the template are replaced with
    concrete values from *profile*.
    """
    js = _load_stealth_template()

    webgl = profile.get("webgl") or {}
    languages = profile.get("languages") or ["en-US", "en"]
    custom_fonts = profile.get("customFonts") or []
    port_scan_allowed = profile.get("portScanAllowedPorts") or [80, 443]
    # Normalise port list (may arrive as comma-separated string)
    if isinstance(port_scan_allowed, str):
        port_scan_allowed = [int(p.strip()) for p in port_scan_allowed.split(",") if p.strip().isdigit()]

    # Simple string replacements
    replacements = {
        "__CANVAS_SEED__": str(profile.get("canvasNoiseSeed", "default_seed")),
        "__WEBGL_VENDOR__": str(webgl.get("vendor", "Intel Inc.")),
        "__WEBGL_RENDERER__": str(webgl.get("renderer", "Intel(R) UHD Graphics")),
        "__PLATFORM__": str(profile.get("platform", "Win32")),
        "__DISPLAY_LANGUAGE__": str(profile.get("displayLanguage") or ""),
        "__DO_NOT_TRACK__": str(profile.get("doNotTrack") or ""),
        # Boolean toggles → "true" / "false"
        "__NOISE_WEBGL_IMAGE__": "true" if profile.get("noiseWebGLImage", True) else "false",
        "__NOISE_CLIENT_RECTS__": "true" if profile.get("noiseClientRects", True) else "false",
        "__NOISE_SPEECH_VOICES__": "true" if profile.get("noiseSpeechVoices", True) else "false",
        "__NOISE_MEDIA_DEVICES__": "true" if profile.get("noiseMediaDevices", True) else "false",
        "__FONT_PROTECTION__": "true" if profile.get("fontProtection", True) else "false",
        "__PORT_SCAN_PROTECTION__": "true" if profile.get("portScanProtection", True) else "false",
        "__WEBGPU_MODE__": str(profile.get("webgpuMode") or "based_on_webgl"),
        # Numeric
        "__HARDWARE_CONCURRENCY__": str(int(profile.get("hardwareConcurrency") or 0)),
        "__DEVICE_MEMORY__": str(int(profile.get("deviceMemory") or 0)),
    }

    for placeholder, value in replacements.items():
        js = js.replace(placeholder, value)

    # Array literals — need JS syntax
    js = js.replace("__LANGUAGES__", json.dumps(languages))
    js = js.replace("__CUSTOM_FONTS__", json.dumps(custom_fonts))
    js = js.replace("__PORT_SCAN_ALLOWED__", json.dumps(port_scan_allowed))

    return js


# ── CDP injection ────────────────────────────────────────────────────────────

async def inject_stealth(session, profile: dict) -> bool:
    """Inject stealth JS and CDP-level overrides into a live BrowserSession.

    Handles:
    1. Stealth JS injection via ``Page.addScriptToEvaluateOnNewDocument``
    2. Geolocation override via ``Emulation.setGeolocationOverride`` (if configured)

    Args:
        session: A browser_use BrowserSession (must be connected).
        profile: Fingerprint profile dict.

    Returns:
        True if injection succeeded.
    """
    try:
        stealth_js = prepare_stealth_js(profile)
        await session._cdp_add_init_script(stealth_js)
        logger.info(
            f"[Fingerprint] Stealth JS injected "
            f"(profile={profile.get('id', '?')}, "
            f"platform={profile.get('platform', '?')}, "
            f"ua_len={len(profile.get('userAgent', ''))})"
        )
    except Exception as exc:
        logger.error(f"[Fingerprint] Failed to inject stealth JS: {exc}")
        return False

    # Geolocation override via CDP
    geo = profile.get("geolocation")
    geo_mode = profile.get("geoLocationMode", "")
    if geo_mode == "custom" and isinstance(geo, dict):
        try:
            lat = float(geo.get("latitude", 0))
            lng = float(geo.get("longitude", 0))
            acc = float(geo.get("accuracy", 100))
            await session._cdp_set_geolocation(lat, lng, acc)
            logger.info(f"[Fingerprint] Geolocation set to ({lat}, {lng})")
        except Exception as geo_exc:
            logger.warning(f"[Fingerprint] Geolocation override failed (non-fatal): {geo_exc}")
    elif geo_mode == "block":
        # Block geolocation by clearing any override — permissions API patch
        # in stealth JS already returns "denied" for geolocation queries
        try:
            await session._cdp_clear_geolocation()
        except Exception:
            pass

    return True


# ── Profile generation (randomizer) ─────────────────────────────────────────

# Realistic component pools for random profile generation
_UA_TEMPLATES = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{ver}.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{ver}.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{ver}.0.0.0 Safari/537.36",
]

_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 2560, "height": 1440},
]

_TIMEZONES = [
    "America/New_York", "America/Chicago", "America/Denver",
    "America/Los_Angeles", "Europe/London", "Europe/Berlin",
    "Europe/Paris", "Asia/Tokyo", "Asia/Shanghai", "Asia/Singapore",
]

_LOCALES = [
    ("en-US", ["en-US", "en"]),
    ("en-GB", ["en-GB", "en"]),
    ("de-DE", ["de-DE", "de", "en"]),
    ("fr-FR", ["fr-FR", "fr", "en"]),
    ("zh-CN", ["zh-CN", "zh", "en"]),
    ("ja-JP", ["ja-JP", "ja", "en"]),
]

_PLATFORMS = {
    "Windows NT 10.0": "Win32",
    "Macintosh": "MacIntel",
    "X11; Linux": "Linux x86_64",
}

_WEBGL_CONFIGS = [
    {"vendor": "Intel Inc.", "renderer": "Intel(R) UHD Graphics 630"},
    {"vendor": "Intel Inc.", "renderer": "Intel(R) Iris(R) Xe Graphics"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon RX 580, OpenGL 4.6)"},
    {"vendor": "Apple", "renderer": "Apple M1"},
    {"vendor": "Apple", "renderer": "Apple M2 Pro"},
]


def generate_random_profile(profile_id: str = "") -> dict:
    """Generate a realistic random fingerprint profile."""
    if not profile_id:
        profile_id = f"random_{random.randint(10000, 99999)}"

    ua_template = random.choice(_UA_TEMPLATES)
    chrome_ver = random.randint(120, 126)
    ua = ua_template.format(ver=chrome_ver)

    # Determine platform from UA
    platform = "Win32"
    for ua_frag, plat in _PLATFORMS.items():
        if ua_frag in ua:
            platform = plat
            break

    locale_pair = random.choice(_LOCALES)
    viewport = random.choice(_VIEWPORTS)
    webgl = random.choice(_WEBGL_CONFIGS)

    return {
        "id": profile_id,
        "name": f"Random Profile {profile_id}",
        "description": "Auto-generated fingerprint profile",
        "userAgent": ua,
        "viewport": viewport,
        "deviceScaleFactor": random.choice([1, 1.25, 1.5, 2]),
        "isMobile": False,
        "timezone": random.choice(_TIMEZONES),
        "locale": locale_pair[0],
        "displayLanguage": locale_pair[0],
        "platform": platform,
        "languages": locale_pair[1],
        "hardwareConcurrency": random.choice([4, 8, 12, 16]),
        "deviceMemory": random.choice([4, 8, 16]),
        "canvasNoiseSeed": f"seed_{random.randint(100000, 999999)}",
        "webgl": webgl,
        "webrtcPolicy": "block",
        "doNotTrack": "",
        "noiseWebGLImage": True,
        "noiseClientRects": True,
        "noiseSpeechVoices": True,
        "noiseMediaDevices": True,
        "fontProtection": True,
        "customFonts": [],
        "portScanProtection": True,
        "portScanAllowedPorts": [80, 443],
        "webgpuMode": "based_on_webgl",
        "geoLocationMode": "",
        "geolocation": None,
        "hardwareAcceleration": "default",
        "proxy": None,
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _minimal_default_profile() -> dict:
    """Fallback profile when nothing else is available."""
    return {
        "id": "default_fallback",
        "name": "Default Fallback",
        "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "viewport": {"width": 1920, "height": 1080},
        "deviceScaleFactor": 1,
        "isMobile": False,
        "timezone": "America/New_York",
        "locale": "en-US",
        "displayLanguage": "en-US",
        "platform": "Win32",
        "languages": ["en-US", "en"],
        "hardwareConcurrency": 8,
        "deviceMemory": 8,
        "canvasNoiseSeed": "default_seed",
        "webgl": {"vendor": "Intel Inc.", "renderer": "Intel(R) UHD Graphics"},
        "webrtcPolicy": "block",
        "doNotTrack": "",
        "noiseWebGLImage": True,
        "noiseClientRects": True,
        "noiseSpeechVoices": True,
        "noiseMediaDevices": True,
        "fontProtection": True,
        "customFonts": [],
        "portScanProtection": True,
        "portScanAllowedPorts": [80, 443],
        "webgpuMode": "based_on_webgl",
        "geoLocationMode": "",
        "geolocation": None,
        "hardwareAcceleration": "default",
        "proxy": None,
    }


def apply_profile_to_browser_profile(browser_profile, fp_profile: dict) -> None:
    """Set fingerprint fields on a browser_use BrowserProfile object.

    This sets user_agent, viewport, locale, timezone, and adds anti-detection
    Chromium args.  The stealth JS injection happens separately via
    inject_stealth() after the session connects.
    """
    if fp_profile.get("userAgent"):
        browser_profile.user_agent = fp_profile["userAgent"]

    vp = fp_profile.get("viewport")
    if vp:
        browser_profile.viewport = vp

    dsf = fp_profile.get("deviceScaleFactor")
    if dsf:
        browser_profile.device_scale_factor = dsf

    # Anti-detection Chromium CLI args
    extra_args = [
        "--disable-blink-features=AutomationControlled",
    ]
    locale = fp_profile.get("locale")
    if locale:
        extra_args.append(f"--lang={locale}")

    # Do Not Track header
    dnt = fp_profile.get("doNotTrack", "")
    if dnt == "1":
        extra_args.append("--enable-do-not-track")

    # Hardware acceleration
    hw_accel = fp_profile.get("hardwareAcceleration", "default")
    if hw_accel == "off":
        extra_args.append("--disable-gpu")
        extra_args.append("--disable-software-rasterizer")
    elif hw_accel == "on":
        extra_args.append("--enable-gpu-rasterization")

    # Timezone override via TZ environment variable emulation
    tz = fp_profile.get("timezone")
    if tz:
        extra_args.append(f"--timezone={tz}")

    # Merge into existing args without duplicates
    existing = set(browser_profile.args or [])
    for arg in extra_args:
        if arg not in existing:
            browser_profile.args.append(arg)

    # Proxy
    proxy_cfg = fp_profile.get("proxy")
    if proxy_cfg and isinstance(proxy_cfg, dict) and proxy_cfg.get("server"):
        from browser_use.browser.profile import ProxySettings
        browser_profile.proxy = ProxySettings(
            server=proxy_cfg["server"],
            username=proxy_cfg.get("username"),
            password=proxy_cfg.get("password"),
            bypass=proxy_cfg.get("bypass"),
        )
