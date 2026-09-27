"""eBay developer app settings: environment, hosts, marketplaces, credentials.

Credentials live in the secure store (OS keyring), per eCan user and per eBay
environment -- never in files or prompts. Environment variables are the
fallback (``ECAN_EBAY_CLIENT_ID`` ...), handy for a headless box.

Store them once with::

    python -m agent.ec_skills.listing.ebay_api.config set --env production

(prompts for the App ID, Cert ID and RuName; the Cert ID is read hidden).
"""
import argparse
import getpass
import os
from typing import Dict, Optional

ENVS = {
    "production": {"api": "https://api.ebay.com", "apim": "https://apim.ebay.com",
                   "auth": "https://auth.ebay.com"},
    "sandbox": {"api": "https://api.sandbox.ebay.com", "apim": "https://apim.sandbox.ebay.com",
                "auth": "https://auth.sandbox.ebay.com"},
}

SCOPES = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.account",
]

# marketplace -> (currency, Content-Language)
MARKETPLACES = {
    "EBAY_US": ("USD", "en-US"), "EBAY_MOTORS_US": ("USD", "en-US"),
    "EBAY_CA": ("CAD", "en-CA"), "EBAY_GB": ("GBP", "en-GB"), "EBAY_AU": ("AUD", "en-AU"),
    "EBAY_DE": ("EUR", "de-DE"), "EBAY_FR": ("EUR", "fr-FR"), "EBAY_IT": ("EUR", "it-IT"),
    "EBAY_ES": ("EUR", "es-ES"), "EBAY_AT": ("EUR", "de-AT"), "EBAY_IE": ("EUR", "en-IE"),
    "EBAY_NL": ("EUR", "nl-NL"), "EBAY_BE": ("EUR", "nl-BE"), "EBAY_CH": ("CHF", "de-CH"),
    "EBAY_PL": ("PLN", "pl-PL"), "EBAY_HK": ("HKD", "zh-HK"), "EBAY_SG": ("SGD", "en-SG"),
}

_FIELDS = ("CLIENT_ID", "CLIENT_SECRET", "RU_NAME")


def current_env() -> str:
    env = (os.environ.get("ECAN_EBAY_ENV") or _store_get("EBAY_ENV") or "production").strip().lower()
    return env if env in ENVS else "production"


def hosts(env: Optional[str] = None) -> Dict[str, str]:
    return ENVS[env or current_env()]


def marketplace(mkt: str) -> tuple:
    m = (mkt or "EBAY_US").strip().upper()
    if not m.startswith("EBAY_"):
        m = "EBAY_" + {"UK": "GB"}.get(m, m)
    if m not in MARKETPLACES:
        raise ValueError(f"unknown eBay marketplace {mkt!r}; one of {sorted(MARKETPLACES)}")
    currency, lang = MARKETPLACES[m]
    return m, currency, lang


def _username() -> Optional[str]:
    try:
        from utils.env.secure_store import get_current_username
        return get_current_username()
    except Exception:
        return None


def _store_get(key: str) -> Optional[str]:
    try:
        from utils.env.secure_store import secure_store
        return secure_store.get(key, username=_username())
    except Exception:
        return None


def _store_set(key: str, value: str) -> bool:
    from utils.env.secure_store import secure_store
    return secure_store.set(key, value, username=_username())


def _store_delete(key: str) -> None:
    try:
        from utils.env.secure_store import secure_store
        secure_store.delete(key, username=_username())
    except Exception:
        pass


def key(env: str, name: str) -> str:
    return f"EBAY_{env.upper()}_{name}"


def credentials(env: Optional[str] = None) -> Dict[str, str]:
    """App ID / Cert ID / RuName for *env*; missing values are ''."""
    env = env or current_env()
    out = {}
    for f in _FIELDS:
        out[f.lower()] = (_store_get(key(env, f))
                          or os.environ.get(f"ECAN_EBAY_{f}")
                          or "").strip()
    return out


def save_credentials(env: str, client_id: str, client_secret: str, ru_name: str) -> None:
    for f, v in zip(_FIELDS, (client_id, client_secret, ru_name)):
        if not _store_set(key(env, f), v.strip()):
            raise RuntimeError(f"could not store {f} in the secure store")


def get_secret(env: str, name: str) -> Optional[str]:
    return _store_get(key(env, name))


def set_secret(env: str, name: str, value: str) -> None:
    _store_set(key(env, name), value)


def delete_secret(env: str, name: str) -> None:
    _store_delete(key(env, name))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Store eBay developer app credentials in the keyring.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set")
    s.add_argument("--env", choices=sorted(ENVS), default="production")
    sub.add_parser("show")
    args = ap.parse_args(argv)
    if args.cmd == "set":
        cid = input("App ID (Client ID): ")
        sec = getpass.getpass("Cert ID (Client Secret): ")
        ru = input("RuName (eBay Redirect URL name): ")
        save_credentials(args.env, cid, sec, ru)
        _store_set("EBAY_ENV", args.env)
        print(f"saved for {args.env}; it is now the active eBay environment")
    else:
        env = current_env()
        c = credentials(env)
        print(f"env={env} client_id={'set' if c['client_id'] else 'MISSING'} "
              f"client_secret={'set' if c['client_secret'] else 'MISSING'} ru_name={c['ru_name'] or 'MISSING'}")


if __name__ == "__main__":
    main()
