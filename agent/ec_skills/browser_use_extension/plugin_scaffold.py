"""
Plugin scaffolding CLI.

Usage::

    python -m agent.ec_skills.browser_use_extension.plugin_scaffold my_plugin
    python -m agent.ec_skills.browser_use_extension.plugin_scaffold my_plugin --dest C:/work

Creates a working starter bundle with:

    my_plugin/
      hook.yaml          ← manifest with kind + gui blocks
      hooks.py           ← one quick-reply hook
      README.md
      gui/
        bridge.js        ← vendorable bridge shim (copy of the reference bundle's)
        config.html
        node.html
        status.html
        theme.css
      tests/test_my_plugin.py

After scaffolding::

    cd my_plugin
    # install into the user plugins dir for live testing:
    python -m agent.ec_skills.browser_use_extension.plugin_installer ...
    # or just point the Plugins page → Install… at this directory.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import textwrap
from pathlib import Path


# Bundled template files are read at runtime from the in-tree reference
# bundle: the first directory under hooks/external/ that ships a gui/ tree.
_EXTERNAL_BUNDLES_DIR = Path(__file__).parent / "hooks" / "external"


def _reference_gui_dir() -> Path:
    for child in sorted(_EXTERNAL_BUNDLES_DIR.iterdir()):
        if child.is_dir() and (child / "gui").is_dir():
            return child / "gui"
    raise RuntimeError(
        f"no reference bundle with a gui/ tree under {_EXTERNAL_BUNDLES_DIR}"
    )


# Per-name slugs we substitute into templated files.
_NAME_PLACEHOLDER = "my_site"


def _valid_name(name: str) -> bool:
    if not name or not (name[0].isalpha() or name[0] == "_"):
        return False
    for ch in name:
        if not (ch.isalnum() or ch in "_-"):
            return False
    return True


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _scaffold_manifest(name: str) -> str:
    return textwrap.dedent(
        f"""\
        api_version: 1
        kind: hook_bundle
        bundle: {name}
        version: 0.1.0
        author: "you"
        description: >
          One-sentence description of what this plugin does.

        # Bundle-level defaults — users override via the Plugins page (global)
        # or per-node via the skill editor's hookBundles field.
        config:
          cooldown_ms: 1500

        # JSON-Schema description consumed by the auto-form renderer when
        # the plugin doesn't ship a gui/config.html.
        config_schema:
          type: object
          properties:
            cooldown_ms:
              type: integer
              title: "Cooldown (ms)"
              minimum: 0
              default: 1500

        # Phase 3 GUI surface.  Drop the gui: block entirely to fall back
        # to the schema-driven auto-form.
        gui:
          host_api_version: 1
          slots:
            config_panel:
              entrypoint: "gui/config.html"
              height: 520
            node_config:
              entrypoint: "gui/node.html"
              height: 360
            status_widget:
              entrypoint: "gui/status.html"
              height: 96
          permissions:
            storage_namespace: {name}
            bridge_methods:
              - config.get
              - config.set
              - storage.get
              - storage.set
              - ui.resize
              - ui.notify
              - host.context
            tools_ui: []

        hooks:
          - name: {name}_quick_reply
            entrypoint: "hooks.py:QuickReplyHook"
            stage: on_event_normalized
            tier: 1
            priority: 20
            permissions:
              tools: []
              network: none
            budget:
              timeout_ms: 200
            matches:
              event_type: ["chat_message"]
            state: memory
        """
    )


def _scaffold_hooks_py(name: str) -> str:
    return textwrap.dedent(
        f'''\
        """
        {name} — Python hook implementations.

        See docs/HOOK_BUNDLES.md for the full HookContext / Decision API.
        """
        from __future__ import annotations
        from agent.ec_skills.browser_use_extension.hook_api import HookResult


        class QuickReplyHook:
            """on_event_normalized — return BYPASS when a deterministic reply applies."""

            manifest = None  # set by loader

            def __init__(self, config=None, manifest=None):
                self.config = config or {{}}
                self.manifest = manifest

            async def run(self, ctx, payload):
                if not isinstance(payload, dict):
                    return HookResult.cont(reason="not-a-dict")
                # Insert your deterministic logic here. Return:
                #   HookResult.cont()              — let the LLM handle it
                #   HookResult.bypass([...])       — skip LLM, do these actions
                #   HookResult.drop()              — ignore this event entirely
                return HookResult.cont()
        '''
    )


def _scaffold_readme(name: str) -> str:
    return textwrap.dedent(
        f"""\
        # {name}

        TODO: one-sentence description.

        ## Layout

        ```
        {name}/
          hook.yaml       ← manifest (required)
          hooks.py        ← Python hook implementations
          gui/
            bridge.js     ← copy of the bridge shim (do not modify)
            config.html   ← global config panel
            node.html     ← per-node config panel
            status.html   ← status widget
            theme.css     ← visual styling
          tests/test_{name}.py
        ```

        ## Develop

        1. Edit `hooks.py` to implement your behavior.
        2. Edit `gui/config.html` to expose user-facing settings — the
           bridge methods on `window.ecan.plugin.*` are documented in
           `docs/PLUGIN_AUTHORING.md`.
        3. Open the eCan app → Plugins → Install… and point at this
           directory.  Toggle the plugin on; it'll be warm-loaded.
        4. Open Plugins → select your plugin → Config tab to see your
           iframe rendered.

        ## Test

        ```
        python -m pytest tests/test_{name}.py -v
        ```
        """
    )


def _scaffold_test_py(name: str) -> str:
    return textwrap.dedent(
        f'''\
        """Smoke test for {name}."""

        import os
        import sys
        import unittest
        from pathlib import Path

        # Allow ``python -m pytest`` from the bundle root.
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


        class {name.title().replace("_", "")}BundleTest(unittest.TestCase):
            def test_manifest_is_readable(self):
                from agent.ec_skills.browser_use_extension.hook_loader import (
                    _read_manifest_file,
                )
                bundle_dir = Path(__file__).resolve().parents[1]
                data = _read_manifest_file(bundle_dir)
                self.assertEqual(data.get("bundle"), "{name}")
                self.assertEqual(len(data.get("hooks") or []), 1)


        if __name__ == "__main__":
            unittest.main()
        '''
    )


def _copy_gui_templates(dest_gui_dir: Path) -> None:
    """Copy the gui/ tree from the reference bundle as a starting point."""
    ref_gui = _reference_gui_dir()
    dest_gui_dir.mkdir(parents=True, exist_ok=True)
    for child in ref_gui.iterdir():
        target = dest_gui_dir / child.name
        if child.is_file():
            shutil.copy2(child, target)


def scaffold(name: str, dest: Path) -> Path:
    if not _valid_name(name):
        raise SystemExit(f"invalid plugin name: {name!r} (allowed: a-z A-Z 0-9 _ -)")
    bundle_dir = (dest / name).resolve()
    if bundle_dir.exists():
        raise SystemExit(f"refusing to overwrite existing dir: {bundle_dir}")
    bundle_dir.mkdir(parents=True, exist_ok=True)

    _write(bundle_dir / "hook.yaml", _scaffold_manifest(name))
    _write(bundle_dir / "hooks.py", _scaffold_hooks_py(name))
    _write(bundle_dir / "README.md", _scaffold_readme(name))
    _write(bundle_dir / "tests" / f"test_{name}.py", _scaffold_test_py(name))
    _copy_gui_templates(bundle_dir / "gui")

    return bundle_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plugin_scaffold")
    parser.add_argument("name", help="plugin name (snake_case)")
    parser.add_argument(
        "--dest", default=".", help="parent directory (default: current dir)"
    )
    args = parser.parse_args(argv)
    dest_path = Path(args.dest).resolve()
    out = scaffold(args.name, dest_path)
    print(f"Scaffolded plugin at: {out}")
    print("Next steps:")
    print(f"  1. cd {out}")
    print("  2. Edit hooks.py + gui/config.html.")
    print("  3. eCan app → Plugins → Install… → point at this directory.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
