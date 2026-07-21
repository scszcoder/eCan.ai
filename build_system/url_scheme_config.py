import json
from pathlib import Path


def _get_url_scheme(app_id: str) -> str:
    """Resolve the URL scheme for the given app via utils.app_config_loader.

    Single source of truth lives in apps/{app_id}/config/app_manifest.json —
    falls back to 'ecan' when the manifest can't be read.
    """
    try:
        from utils.app_config_loader import AppConfigLoader
        return AppConfigLoader(app_id).url_scheme.rstrip('://') or 'ecan'
    except Exception:
        return 'ecan'


def _get_config_path() -> Path:
    """Resolve build config path via utils.app_config_loader (single source of truth).

    Loads apps/{app_id}/build/build_config_{app_id}.json when available,
    falling back to build_system/build_config.json.
    """
    try:
        from utils.app_config_loader import AppConfigLoader
        loader = AppConfigLoader()
        app_id = loader.app_id
    except Exception:
        import os
        app_id = os.environ.get('ECAN_APP_ID', 'intl')

    project_root = Path(__file__).resolve().parent.parent
    per_app = project_root / 'apps' / app_id / 'build' / f'build_config_{app_id}.json'
    if per_app.exists():
        return per_app
    return project_root / 'build_system' / 'build_config.json'


class URLSchemeBuildConfig:
    @staticmethod
    def get_pyinstaller_options():
        try:
            cfg_path = _get_config_path()
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
            cfg_path = _get_config_path()
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            installer_cfg = cfg.get('installer', {})
            win_cfg = installer_cfg.get('windows', {})
            url_schemes = (win_cfg.get('registry_entries') or [])

            # Determine the app's URL scheme from app_manifest.json (single source
            # of truth). Subkeys in registry_entries follow the pattern
            # "Software\\Classes\\{scheme}" so we resolve once and pick the entry.
            try:
                from utils.app_config_loader import AppConfigLoader
                app_id = AppConfigLoader().app_id
            except Exception:
                import os
                app_id = os.environ.get('ECAN_APP_ID', 'intl')
            expected_scheme = _get_url_scheme(app_id)

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
