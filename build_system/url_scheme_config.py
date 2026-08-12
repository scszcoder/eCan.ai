"""URL scheme resolution.

Single source of truth lives in apps/{app_id}/config/app_manifest.json and
apps/{app_id}/build/build_config_{app_id}.json. We delegate to
utils.app_config_loader helpers so this module never duplicates config lookups.

The loader import is intentionally function-local: importing url_scheme_config
should not cause the build process to touch apps/{app_id}/ config paths (or
any logger_helper / colorlog transitively) at module load time.
"""
import json
from pathlib import Path


def _get_url_scheme(app_id: str) -> str:
    """URL scheme (sans '://') for the given app via the active AppConfigLoader."""
    try:
        from utils.app_config_loader import get_app_config
        return get_app_config(app_id).url_scheme.rstrip('://') or 'ecan'
    except Exception:
        return 'ecan'


class URLSchemeBuildConfig:
    @staticmethod
    def get_pyinstaller_options():
        try:
            from utils.app_config_loader import get_build_config_path
            cfg_path = get_build_config_path()
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)

            installer_cfg = (cfg.get('installer') or {}).get('macos') or {}
            bundle_id = installer_cfg.get('bundle_identifier')
            opts = []
            if bundle_id:
                opts.append(f"--osx-bundle-identifier={bundle_id}")
            return opts
        except Exception:
            return []

    @staticmethod
    def _setup_windows_build():
        """Setup Windows URL scheme based on app_id (sourced from manifest)."""
        try:
            from utils.app_config_loader import get_build_config_path, AppConfigLoader
            cfg_path = get_build_config_path()
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            installer_cfg = cfg.get('installer', {})
            win_cfg = installer_cfg.get('windows', {})
            url_schemes = (win_cfg.get('registry_entries') or [])

            expected_scheme = _get_url_scheme(AppConfigLoader().app_id)

            scheme = expected_scheme
            for entry in url_schemes:
                subkey = entry.get('subkey', '')
                if 'URL Protocol' in entry.get('value_name', ''):
                    # Subkey is "Software\\Classes\\{scheme}" — match by trailing token
                    parts = subkey.split('\\')
                    if parts and parts[-1].lower() == expected_scheme.lower():
                        scheme = expected_scheme
                        break
            print(f"[URL_SCHEME] Windows URL scheme: {scheme}")
            return True
        except Exception:
            return False
