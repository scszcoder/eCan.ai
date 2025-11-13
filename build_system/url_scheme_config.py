import json
from pathlib import Path


class URLSchemeBuildConfig:
    @staticmethod
    def get_pyinstaller_options():
        try:
            # Resolve project root as two levels up from this file (build_system/..)
            project_root = Path(__file__).resolve().parent.parent
            cfg_path = project_root / 'build_system' / 'build_config.json'
            if not cfg_path.exists():
                return []

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
