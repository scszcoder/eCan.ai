#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minibuild core: a simplified, maintainable build pipeline for PyInstaller.

Design goals:
- Single spec generator with tiny dynamic-import detection
- Minimal config surface (reuse build_system/build_config.json where possible)
- Default to onedir; onefile optional per mode
- Works on Windows and macOS; supports macOS .app (BUNDLE) and PKG via existing InstallerBuilder
- Very small hook surface (reuse existing build_system/pyinstaller_hooks)
"""
from __future__ import annotations

import ast
import json
import sys
import subprocess
import os
from pathlib import Path
from typing import Dict, List, Set, Any, Optional
import shutil


class MiniSpecBuilder:
    def __init__(self, project_root: Optional[Path] = None, config_path: str = "build_system/build_config.json"):
        self.project_root = project_root or Path.cwd()
        self.config_path = self.project_root / config_path
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.cfg: Dict[str, Any] = json.load(f)
        # Generated hooks directory (for pre_safe_import_module)
        self.gen_hooks_dir = self.project_root / "build" / "pyinstaller_hooks_gen"
        self.pre_safe_dir = self.gen_hooks_dir / "pre_safe_import_module"

    # ---- Public API ----
    def build(self, mode: str = "fast") -> bool:
        # Ensure minimal pre-safe hooks for modules that parse argv at import-time
        # Generate pre-safe hooks for known offenders + dynamically detected argparse-at-import modules
        cfg_pre_safe = set(self.cfg.get("pyinstaller", {}).get("force_pre_safe", []) or [])
        candidates = {"lightrag", "lightrag.api", "lightrag.api.config", "jaraco", "jaraco.text", "jaraco.functools", "more_itertools", "argparse"}
        detected = set(self._detect_argparse_import_side_effects())
        self._ensure_pre_safe_hooks(sorted(cfg_pre_safe | candidates | detected))
        self._ensure_global_sitecustomize()

        # On macOS, clean up potential symlink conflicts BEFORE writing the spec
        if sys.platform == "darwin":
            self._clean_macos_symlinks_before_build()

        # Write spec after cleanup so it won't be removed inadvertently
        self._last_spec_path = self._write_spec(mode)
        
        cmd = [sys.executable, "-m", "PyInstaller", str(self._last_spec_path), "--noconfirm", "--clean"]
        print(f"[MINIBUILD] Running: {' '.join(cmd)}")
        env = os.environ.copy()
        py_path = str(self.gen_hooks_dir)
        env["PYTHONPATH"] = (py_path + (os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else ""))
        env["PYTHONUTF8"] = "1"
        
        result = subprocess.run(cmd, cwd=str(self.project_root), env=env)
        if result.returncode != 0:
            print(f"[MINIBUILD] Build failed with code {result.returncode}")
            # Auto-heal: if argparse-side-effect detected in logs, add to pre-safe and retry once
            repaired = self._auto_heal_and_retry(mode)
            if repaired:
                return True
            return False
        print("[MINIBUILD] Build succeeded")
        return True

    def _auto_heal_and_retry(self, mode: str) -> bool:
        """Parse last PyInstaller logs from Analysis failure and auto-generate pre-safe hooks for
        modules that import argparse and fail due to unrecognized arguments. Retry once.
        """
        try:
            # Read the latest build log from stderr/stdout is not trivial here; we heuristically
            # add a broader set of pre-safe modules and retry once.
            broaden = {
                "lightrag", "lightrag.api", "lightrag.api.config",
                "jaraco", "jaraco.text", "jaraco.functools", "jaraco.context",
                "jaraco.collections", "jaraco.itertools", "jaraco.classes", "jaraco.logging",
                "jaraco.path", "jaraco.stream", "more_itertools", "argparse"
            }
            self._ensure_pre_safe_hooks(sorted(broaden))
            # Re-run PyInstaller once
            cmd = [sys.executable, "-m", "PyInstaller", str(self._last_spec_path), "--noconfirm", "--clean"]
            print(f"[MINIBUILD] Auto-heal: retrying build with broader pre-safe hooks...")
            env2 = os.environ.copy()
            py_path = str(self.gen_hooks_dir)
            env2["PYTHONPATH"] = (py_path + (os.pathsep + env2.get("PYTHONPATH", "") if env2.get("PYTHONPATH") else ""))
            env2["PYTHONUTF8"] = "1"
            result = subprocess.run(cmd, cwd=str(self.project_root), env=env2)
            if result.returncode == 0:
                print("[MINIBUILD] Auto-heal succeeded")
                return True
            print(f"[MINIBUILD] Auto-heal retry still failed (code {result.returncode})")
            return False
        except Exception as e:
            print(f"[MINIBUILD] Auto-heal failed to execute: {e}")
            return False

    def _ensure_pre_safe_hooks(self, modules: List[str]) -> None:
        try:
            if not modules:
                return
            self.pre_safe_dir.mkdir(parents=True, exist_ok=True)
            tmpl = (
                "# Auto-generated by minibuild_core: pre-safe import hook for {mod}\n"
                "def pre_safe_import_module(api):\n"
                "    import sys, argparse\n"
                "    try:\n"
                "        # Patch both parse_args and parse_known_args to avoid argv side-effects\n"
                "        _orig_parse_args = argparse.ArgumentParser.parse_args\n"
                "        _orig_parse_known_args = argparse.ArgumentParser.parse_known_args\n"
                "        def _safe_parse_args(self, args=None, namespace=None):\n"
                "            return _orig_parse_args(self, args=[], namespace=namespace)\n"
                "        def _safe_parse_known_args(self, args=None, namespace=None):\n"
                "            return _orig_parse_known_args(self, args=[], namespace=namespace)\n"
                "        argparse.ArgumentParser.parse_args = _safe_parse_args\n"
                "        argparse.ArgumentParser.parse_known_args = _safe_parse_known_args\n"
                "    except Exception:\n"
                "        pass\n"
            )
            for mod in modules:
                (self.pre_safe_dir / f"hook-{mod}.py").write_text(tmpl.format(mod=mod), encoding="utf-8")
        except Exception:
            pass

    def _ensure_global_sitecustomize(self) -> None:
        """Ensure a sitecustomize.py that patches argparse globally for isolated child processes."""
        try:
            self.gen_hooks_dir.mkdir(parents=True, exist_ok=True)
            sc = self.gen_hooks_dir / "sitecustomize.py"
            content = (
                "# Auto-generated by minibuild_core: global sitecustomize for PyInstaller isolated child\n"
                "import sys, os, argparse\n"
                "try:\n"
                "    prog = ''\n"
                "    if hasattr(sys, 'argv') and isinstance(sys.argv, list) and len(sys.argv) > 0:\n"
                "        try:\n"
                "            prog = os.path.basename(sys.argv[0]).lower()\n"
                "        except Exception:\n"
                "            prog = str(sys.argv[0]).lower()\n"
                "    # Only patch when running PyInstaller's isolated child (_child.py),\n"
                "    # so we do not break the parent PyInstaller CLI argparse.\n"
                "    if prog.endswith('_child.py'):\n"
                "        _orig_parse_args = argparse.ArgumentParser.parse_args\n"
                "        _orig_parse_known_args = argparse.ArgumentParser.parse_known_args\n"
                "        def _safe_parse_args(self, args=None, namespace=None):\n"
                "            return _orig_parse_args(self, args=[], namespace=namespace)\n"
                "        def _safe_parse_known_args(self, args=None, namespace=None):\n"
                "            return _orig_parse_known_args(self, args=[], namespace=namespace)\n"
                "        argparse.ArgumentParser.parse_args = _safe_parse_args\n"
                "        argparse.ArgumentParser.parse_known_args = _safe_parse_known_args\n"
                "except Exception:\n"
                "    pass\n"
            )
            sc.write_text(content, encoding="utf-8")
        except Exception:
            pass

    # ---- Spec generation ----
    def _write_spec(self, mode: str) -> Path:
        app = self.cfg.get("app_info", {})
        app_name = app.get("name", "app")
        main_script = app.get("main_script", "main.py")
        icon_win = app.get("icon_windows", "eCan.ico")
        icon_mac = app.get("icon_macos", "eCan.icns")

        bmodes = self.cfg.get("build_modes", {})
        mode_cfg = bmodes.get(mode, {})
        onefile = bool(mode_cfg.get("onefile", False))
        console = bool(mode_cfg.get("console", app.get("console", False)))
        debug = bool(mode_cfg.get("debug", app.get("debug", False)))

        datas_lines = self._datas_from_config()
        hiddenimports = self._hiddenimports_minimal()

        spec_lines: List[str] = []
        spec_lines.append("# -*- mode: python ; coding: utf-8 -*-")
        spec_lines.append("import sys")
        spec_lines.append("from pathlib import Path")
        spec_lines.append("project_root = Path(r'" + str(self.project_root) + "')")
        spec_lines.append("")
        spec_lines.append("import os as _os, sys as _sys")
        spec_lines.append("")
        spec_lines.append("data_files = []")
        spec_lines.append("binaries = []")
        spec_lines.append("hiddenimports = " + repr(hiddenimports))
        spec_lines.extend(datas_lines)
        spec_lines.append("")

        # Collect all resources/hiddenimports/binaries for configured packages (e.g., 'browser_use')
        collect_pkgs = self.cfg.get("pyinstaller", {}).get("collect_all", []) or []
        if collect_pkgs:
            spec_lines.append("from PyInstaller.utils.hooks import collect_all")
            spec_lines.append("hooked_bins = []")
            spec_lines.append("hooked_hidden = []")
            spec_lines.append("for _pkg in " + repr(collect_pkgs) + ":")
            spec_lines.append("    _d, _b, _h = collect_all(_pkg)")
            spec_lines.append("    data_files += _d")
            spec_lines.append("    binaries += _b")
            spec_lines.append("    hiddenimports += _h")
            spec_lines.append("")

        # collect data-only for some packages that cannot be imported in isolated child (e.g., lightrag)
        collect_data_only = self.cfg.get("pyinstaller", {}).get("collect_data_only", []) or []
        if collect_data_only:
            spec_lines.append("from PyInstaller.utils.hooks import collect_data_files")
            spec_lines.append("for _pkg in " + repr(collect_data_only) + ":")
            spec_lines.append("    data_files += collect_data_files(_pkg)")
            spec_lines.append("")
        spec_lines.append("a = Analysis([")
        spec_lines.append(f"    r'{main_script}'",
        )
        spec_lines.append("],")
        spec_lines.append("    pathex=[str(project_root)],")
        spec_lines.append("    binaries=binaries,")
        spec_lines.append("    datas=data_files,")
        spec_lines.append("    hiddenimports=hiddenimports,")
        spec_lines.append("    hookspath=[],  # Use PyInstaller's default hooks for PySide6/QtWebEngine")
        spec_lines.append("    hooksconfig={},")
        spec_lines.append("    runtime_hooks=[],")
        spec_lines.append("    excludes=" + repr(self.cfg.get("pyinstaller", {}).get("excludes", [])) + ",")
        
        # Add codesign exclusions for macOS
        if sys.platform == 'darwin':
            codesign_excludes = self.cfg.get("pyinstaller", {}).get("codesign_exclude", [])
            if codesign_excludes:
                spec_lines.append("    # macOS codesign exclusions")
                spec_lines.append("    # These files will be treated as data, not binaries")
                for exclude in codesign_excludes:
                    spec_lines.append(f"    # codesign_exclude: {exclude}")
                spec_lines.append("")
        spec_lines.append("    win_no_prefer_redirects=False,")
        spec_lines.append("    win_private_assemblies=False,")
        # Get optimization settings
        opt_cfg = self.cfg.get("pyinstaller", {}).get("optimization", {})
        copy_metadata = opt_cfg.get("copy_metadata", True)
        
        spec_lines.append("    cipher=None,")
        spec_lines.append("    noarchive=False,")
        spec_lines.append(f"    copy_metadata={copy_metadata},")
        spec_lines.append(")")
        spec_lines.append("")
        
        # Add runtime hook processing for codesign exclusions
        spec_lines.append("# Process codesign exclusions for Playwright browsers")
        spec_lines.append("if _sys.platform == 'darwin':")
        spec_lines.append("    # Move problematic files from binaries to datas to avoid codesign on macOS")
        spec_lines.append("    excluded_binaries = []")
        spec_lines.append("    for binary in a.binaries[:]:")
        spec_lines.append("        binary_path = str(binary[0])")
        spec_lines.append("        # Only exclude specific Playwright browser executables")
        spec_lines.append("        if ('ms-playwright' in binary_path and")
        spec_lines.append("            ('/Chromium.app/Contents/MacOS/Chromium' in binary_path or")
        spec_lines.append("             '/chrome-mac/Chromium.app/Contents/MacOS/Chromium' in binary_path or")
        spec_lines.append("             '/chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium' in binary_path or")
        spec_lines.append("             '/chrome-linux/chrome' in binary_path or")
        spec_lines.append("             '/chrome-win/chrome.exe' in binary_path)):")
        spec_lines.append("            excluded_binaries.append(binary)")
        spec_lines.append("            a.binaries.remove(binary)")
        spec_lines.append("            if binary not in a.datas:")
        spec_lines.append("                a.datas.append(binary)")
        spec_lines.append("    print(f'[SPEC] Moved {len(excluded_binaries)} Playwright browser executables from binaries to datas')")
        spec_lines.append("")
        
        spec_lines.append("")
        spec_lines.append("# Remove duplicate data files to prevent conflicts")
        spec_lines.append("seen_datas = set()")
        spec_lines.append("unique_datas = []")
        spec_lines.append("for data in a.datas:")
        spec_lines.append("    # data: (dest_name, source_path, type)")
        spec_lines.append("    data_key = (data[0], data[1])")
        spec_lines.append("    if data_key not in seen_datas:")
        spec_lines.append("        seen_datas.add(data_key)")
        spec_lines.append("        unique_datas.append(data)")
        spec_lines.append("    else:")
        spec_lines.append("        try:")
        spec_lines.append("            print(f'[SPEC] Removed duplicate data file: {data[0]} -> {data[1]}')")
        spec_lines.append("        except Exception:")
        spec_lines.append("            print('[SPEC] Removed duplicate data (unprintable)')")
        spec_lines.append("a.datas = unique_datas")
        spec_lines.append("print(f'[SPEC] Cleaned up data files: {len(unique_datas)} unique files')")
        spec_lines.append("")
        
        # De-duplicate binaries to avoid framework/link collisions (e.g., Qt Chromium Framework)
        spec_lines.append("# Remove duplicate binaries to prevent conflicts")
        spec_lines.append("seen_bins = set()")
        spec_lines.append("unique_bins = []")
        spec_lines.append("for b in a.binaries:")
        spec_lines.append("    try:")
        spec_lines.append("        # b is a TOC entry like (dest_name, source_path, type)")
        spec_lines.append("        key = (b[0], b[1])")
        spec_lines.append("    except Exception:")
        spec_lines.append("        key = str(b)")
        spec_lines.append("    if key not in seen_bins:")
        spec_lines.append("        seen_bins.add(key)")
        spec_lines.append("        unique_bins.append(b)")
        spec_lines.append("    else:")
        spec_lines.append("        try:")
        spec_lines.append("            print(f'[SPEC] Removed duplicate binary: {b[0]} -> {b[1]}')")
        spec_lines.append("        except Exception:")
        spec_lines.append("            print('[SPEC] Removed duplicate binary (unprintable)')")
        spec_lines.append("a.binaries = unique_bins")
        spec_lines.append("print(f'[SPEC] Cleaned up binaries: {len(unique_bins)} unique entries')")
        spec_lines.append("")

        # Normalize by destination path: prefer binaries over datas when duplicates share same dest
        spec_lines.append("# Normalize TOC by destination path: prefer binaries over datas")
        spec_lines.append("by_dest = {}  # dest -> ('bin'|'data', entry)")
        spec_lines.append("# Index binaries")
        spec_lines.append("for b in a.binaries:")
        spec_lines.append("    try:")
        spec_lines.append("        dest = str(b[0])")
        spec_lines.append("    except Exception:")
        spec_lines.append("        continue")
        spec_lines.append("    by_dest[dest] = ('bin', b)")
        spec_lines.append("# Index datas only if dest not already a binary")
        spec_lines.append("for d in a.datas:")
        spec_lines.append("    try:")
        spec_lines.append("        dest = str(d[0])")
        spec_lines.append("    except Exception:")
        spec_lines.append("        continue")
        spec_lines.append("    if dest not in by_dest:")
        spec_lines.append("        by_dest[dest] = ('data', d)")
        spec_lines.append("# Rebuild lists")
        spec_lines.append("new_bins, new_datas = [], []")
        spec_lines.append("for dest, (kind, entry) in by_dest.items():")
        spec_lines.append("    if kind == 'bin': new_bins.append(entry)")
        spec_lines.append("    else: new_datas.append(entry)")
        spec_lines.append("removed_bins = len(a.binaries) - len(new_bins)")
        spec_lines.append("removed_datas = len(a.datas) - len(new_datas)")
        spec_lines.append("a.binaries = new_bins")
        spec_lines.append("a.datas = new_datas")
        spec_lines.append("print(f'[SPEC] Dest-path normalization removed {removed_bins} bin and {removed_datas} data duplicates')")
        spec_lines.append("")

        # On macOS, enforce framework symlink safety but allow Qt WebEngine components
        # Typical layout: Foo.framework/{Headers,Resources,Modules,Helpers} are
        # top-level symlinks -> Versions/Current/<Name>.
        spec_lines.append("if _sys.platform == 'darwin':")
        spec_lines.append("    def _is_framework_symlink_root(path: str) -> bool:")
        spec_lines.append("        p = path.replace('\\\\', '/')")
        spec_lines.append("        parts = p.split('/')")
        spec_lines.append("        try:")
        spec_lines.append("            idx = parts.index('*.app'.replace('*', ''))  # dummy to keep same indent")
        spec_lines.append("        except ValueError:")
        spec_lines.append("            pass")
        spec_lines.append("        return any(seg.endswith('.framework') for seg in parts)")
        spec_lines.append("    def _is_symlink_leaf_name(name: str) -> bool:")
        spec_lines.append("        return name in ('Headers', 'Resources', 'Modules', 'Helpers')")
        spec_lines.append("    def _should_drop_entry(dest_name: str) -> bool:")
        spec_lines.append("        if '.framework/' not in dest_name and not dest_name.endswith('.framework'):")
        spec_lines.append("            return False")
        spec_lines.append("        # Extract last path component to detect symlink leaves")
        spec_lines.append("        name = dest_name.rsplit('/', 1)[-1]")
        spec_lines.append("        if _is_symlink_leaf_name(name):")
        spec_lines.append("            # Root leaf itself must be a symlink; let COLLECT create it via link")
        spec_lines.append("            return False")
        spec_lines.append("        # Check macOS framework whitelist from config")
        spec_lines.append("        whitelist_config = " + repr(self.cfg.get("pyinstaller", {}).get("macos_framework_whitelist", {})) + "")
        spec_lines.append("        if whitelist_config.get('enabled', False):")
        spec_lines.append("            # Qt WebEngine whitelist")
        spec_lines.append("            qt_config = whitelist_config.get('qt_webengine', {})")
        spec_lines.append("            if qt_config.get('enabled', False):")
        spec_lines.append("                for pattern in qt_config.get('patterns', []):")
        spec_lines.append("                    if pattern in dest_name:")
        spec_lines.append("                        return False")
        spec_lines.append("            # Playwright whitelist")
        spec_lines.append("            pw_config = whitelist_config.get('playwright', {})")
        spec_lines.append("            if pw_config.get('enabled', False):")
        spec_lines.append("                # Check executables")
        spec_lines.append("                for pattern in pw_config.get('executables', []):")
        spec_lines.append("                    if pattern in dest_name:")
        spec_lines.append("                        return False")
        spec_lines.append("                # Check frameworks")
        spec_lines.append("                for pattern in pw_config.get('frameworks', []):")
        spec_lines.append("                    if pattern in dest_name:")
        spec_lines.append("                        return False")
        spec_lines.append("                # Check resources")
        spec_lines.append("                for pattern in pw_config.get('resources', []):")
        spec_lines.append("                    if pattern in dest_name:")
        spec_lines.append("                        return False")
        spec_lines.append("        # If the path begins with a framework leaf (e.g., Helpers/foo), the leaf should be a symlink; drop nested files")
        spec_lines.append("        for leaf in ('Headers/', 'Resources/', 'Modules/', 'Helpers/'):")
        spec_lines.append("            if f'.framework/{leaf}' in dest_name:")
        spec_lines.append("                # Allow only the leaf itself; nested entries risk creating directories before symlinks")
        spec_lines.append("                return True")
        spec_lines.append("        return False")
        spec_lines.append("    # Filter a.datas and a.binaries")
        spec_lines.append("    filtered_datas = []")
        spec_lines.append("    dropped_datas = 0")
        spec_lines.append("    for d in a.datas:")
        spec_lines.append("        dest = str(d[0])")
        spec_lines.append("        if _should_drop_entry(dest):")
        spec_lines.append("            dropped_datas += 1")
        spec_lines.append("        else:")
        spec_lines.append("            filtered_datas.append(d)")
        spec_lines.append("    a.datas = filtered_datas")
        spec_lines.append("    filtered_bins = []")
        spec_lines.append("    dropped_bins = 0")
        spec_lines.append("    for b in a.binaries:")
        spec_lines.append("        dest = str(b[0])")
        spec_lines.append("        if _should_drop_entry(dest):")
        spec_lines.append("            dropped_bins += 1")
        spec_lines.append("        else:")
        spec_lines.append("            filtered_bins.append(b)")
        spec_lines.append("    a.binaries = filtered_bins")
        spec_lines.append("    print(f'[SPEC] macOS framework filter: dropped {dropped_bins} binaries, {dropped_datas} datas')")
        
        spec_lines.append("pyz = PYZ(a.pure, a.zipped_data, cipher=None)")
        spec_lines.append("")

        if onefile:
            # onefile EXE
            spec_lines.append("exe = EXE(")
            spec_lines.append("    pyz,")
            spec_lines.append("    a.scripts,")
            spec_lines.append("    a.binaries,")
            spec_lines.append("    a.zipfiles,")
            spec_lines.append("    a.datas,")
            spec_lines.append(f"    name='{app_name}',")
            spec_lines.append(f"    debug={repr(debug)},")
            spec_lines.append("    bootloader_ignore_signals=False,")
            spec_lines.append(f"    strip={'False' if sys.platform.startswith('win') else 'True'},")
            spec_lines.append("    upx=False,")
            spec_lines.append("    upx_exclude=[],")
            spec_lines.append("    runtime_tmpdir=None,")
            spec_lines.append(f"    console={repr(console)},")
            # icon per platform
            spec_lines.append("    icon=(r'" + (icon_mac if sys.platform == 'darwin' else icon_win) + "'),")
            spec_lines.append(")")
        else:
            # onedir EXE + COLLECT
            spec_lines.append("exe = EXE(")
            spec_lines.append("    pyz,")
            spec_lines.append("    a.scripts,")
            spec_lines.append("    [],")
            spec_lines.append("    exclude_binaries=True,")
            spec_lines.append(f"    name='{app_name}',")
            spec_lines.append(f"    debug={repr(debug)},")
            spec_lines.append("    bootloader_ignore_signals=False,")
            spec_lines.append(f"    strip={'False' if sys.platform.startswith('win') else 'True'},")
            spec_lines.append("    upx=False,")
            spec_lines.append("    upx_exclude=[],")
            spec_lines.append("    runtime_tmpdir=None,")
            spec_lines.append(f"    console={repr(console)},")
            spec_lines.append("    icon=(r'" + (icon_mac if sys.platform == 'darwin' else icon_win) + "'),")
            spec_lines.append(")")
            spec_lines.append("")
            spec_lines.append("coll = COLLECT(")
            spec_lines.append("    exe,")
            spec_lines.append("    a.binaries,")
            spec_lines.append("    a.zipfiles,")
            spec_lines.append("    a.datas,")
            spec_lines.append(f"    strip={'False' if sys.platform.startswith('win') else 'True'},")
            spec_lines.append("    upx=False,")
            spec_lines.append("    upx_exclude=[],")
            spec_lines.append("    exclude_binaries=False,")
            spec_lines.append("    name='{app_name}'".format(app_name=app_name))
            spec_lines.append(")")
            spec_lines.append("")
            # macOS app bundle wrapper
            spec_lines.append("if _sys.platform == 'darwin':")
            spec_lines.append("    app = BUNDLE(")
            spec_lines.append("        coll,")
            spec_lines.append(f"        name='{app_name}.app',")
            spec_lines.append("        icon=(r'" + icon_mac + "'),")
            spec_lines.append("    )")

        spec_path = self.project_root / f"{app_name}_{mode}.spec"
        spec_path.write_text("\n".join(spec_lines), encoding="utf-8")
        print(f"[MINIBUILD] Wrote spec: {spec_path}")
        return spec_path

    # ---- Helpers ----
    def _datas_from_config(self) -> List[str]:
        """Generate spec lines for data files/dirs, skipping entries that don't exist.
        This prevents PyInstaller from failing when optional files like .env are absent.
        """
        lines: List[str] = []
        data_cfg = self.cfg.get("data_files", {})
        # Directories
        for d in data_cfg.get("directories", []) or []:
            d_path = (self.project_root / d)
            if d_path.exists():
                lines.append(f"data_files.append((r'{d}', r'{d}'))")
            else:
                print(f"[MINIBUILD] Warning: data directory not found, skipping: {d_path}")
        # Files
        for f in data_cfg.get("files", []) or []:
            f_path = (self.project_root / f)
            if f_path.exists():
                lines.append(f"data_files.append((r'{f}', r'.'))")
            else:
                print(f"[MINIBUILD] Warning: data file not found, skipping: {f_path}")
        return lines

    def _hiddenimports_minimal(self) -> List[str]:
        # Start with a curated baseline for known problematic modules
        base: Set[str] = {
            # Qt WebEngine pieces (let PyInstaller's own hooks pick the rest)
            "PySide6.QtWebEngineCore",
            "PySide6.QtWebEngineWidgets",
            # Avoid explicitly importing modules that cause side-effects at import-time in isolated child
            # e.g., lightrag.api.config parses argv on import; we handle it with pre_safe hooks instead of hiddenimports
        }
        # Merge with any forced includes from config
        for m in self.cfg.get("pyinstaller", {}).get("force_includes", []) or []:
            if isinstance(m, str) and m:
                base.add(m)
        # Merge with force_hiddenimports from config (factory-confirmed)
        for m in self.cfg.get("pyinstaller", {}).get("force_hiddenimports", []) or []:
            if isinstance(m, str) and m:
                base.add(m)
        # Add simple dynamic imports detected from our project code
        base |= set(self._detect_dynamic_imports(self.project_root))
        return sorted(base)

    def _detect_dynamic_imports(self, root: Path) -> List[str]:
        mods: Set[str] = set()
        for py in root.rglob("*.py"):
            p = str(py)
            if any(sk in p for sk in ("venv", "build", "dist", "__pycache__", ".git", "node_modules")):
                continue
            try:
                src = py.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(src)
            except Exception:
                continue
            for node in ast.walk(tree):
                # importlib.import_module("pkg.sub") / from importlib import import_module; import_module("x")
                if isinstance(node, ast.Call):
                    # __import__("mod")
                    if isinstance(node.func, ast.Name) and node.func.id == "__import__":
                        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                            mods.add(node.args[0].value)
                    # importlib.import_module("mod") or import_module("mod")
                    elif isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
                        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                            mods.add(node.args[0].value)
                    elif isinstance(node.func, ast.Name) and node.func.id == "import_module":
                        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                            mods.add(node.args[0].value)
        return sorted(m for m in mods if m and not m.startswith((".", "_")))

    def _detect_argparse_import_side_effects(self) -> List[str]:
        """Heuristic: detect packages that likely parse argv at import time.
        Strategy:
        - Scan installed site-packages for modules that import argparse and call parse_args() at module top-level.
        - Restrict to modules referenced by our codebase (via _detect_dynamic_imports + normal imports in main tree).
        - Keep it fast: string search first, then AST on suspicious files only.
        """
        suspicious: Set[str] = set()
        # 1) candidates from our own dynamic imports
        candidates = set(self._detect_dynamic_imports(self.project_root))
        # 2) add a few known packages that often parse args at import-time
        candidates |= {"lightrag", "jaraco", "more_itertools"}
        sitepkgs = [p for p in sys.path if p.endswith("site-packages")]
        for base in sitepkgs:
            bpath = Path(base)
            for mod in list(candidates):
                # Try to locate module/package directory
                for entry in bpath.rglob(mod.replace('.', '/') + "*.py"):
                    try:
                        txt = entry.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        continue
                    if "import argparse" not in txt and "from argparse" not in txt:
                        continue
                    if "parse_args(" not in txt:
                        continue
                    try:
                        tree = ast.parse(txt)
                    except Exception:
                        suspicious.add(mod)
                        continue
                    # Scan for top-level parse_args calls
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call):
                            # argparse.ArgumentParser(...).parse_args(...)
                            if isinstance(node.func, ast.Attribute) and node.func.attr == "parse_args":
                                suspicious.add(mod)
                                break
        return sorted(suspicious)

    def _clean_macos_symlinks_before_build(self) -> None:
        """Clean up symlink conflicts on macOS"""
        try:
            print("[MINIBUILD] Automatically cleaning macOS symlink conflicts...")
            
            # Clean up potential build artifacts
            dist_dir = self.project_root / "dist"
            build_dir = self.project_root / "build"
            
            if dist_dir.exists():
                print(f"[MINIBUILD] Cleaning dist directory: {dist_dir}")
                self._safe_remove_directory(dist_dir)
            
            if build_dir.exists():
                print(f"[MINIBUILD] Cleaning build directory: {build_dir}")
                self._safe_remove_directory(build_dir)
            
            # Clean up potential .spec file artifacts
            for spec_file in self.project_root.glob("*.spec"):
                if spec_file.exists():
                    print(f"[MINIBUILD] Deleting spec file: {spec_file}")
                    try:
                        spec_file.unlink()
                    except Exception as e:
                        print(f"[MINIBUILD] Warning: Cannot delete {spec_file}: {e}")
            
            # Clean up Python cache
            cache_dirs = [".pyinstaller", "__pycache__"]
            for cache_name in cache_dirs:
                cache_dir = self.project_root / cache_name
                if cache_dir.exists():
                    print(f"[MINIBUILD] Cleaning cache directory: {cache_dir}")
                    self._safe_remove_directory(cache_dir)
                    
        except Exception as e:
            print(f"[MINIBUILD] Warning: Error occurred during cleanup: {e}")
    
    def _safe_remove_directory(self, directory: Path) -> None:
        """Safely remove directory, handling symlink conflicts"""
        if not directory.exists():
            return
            
        try:
            # First delete all symlinks
            for item in directory.rglob("*"):
                if item.is_symlink():
                    try:
                        item.unlink()
                        print(f"[MINIBUILD] Deleting symlink: {item}")
                    except Exception:
                        pass
            
            # Then delete the directory
            shutil.rmtree(directory)
            print(f"[MINIBUILD] Successfully deleted directory: {directory}")
            
        except Exception as e:
            print(f"[MINIBUILD] Warning: Cannot delete {directory}: {e}")
            # Try using system commands to force delete
            try:
                if sys.platform == "darwin":
                    subprocess.run(["rm", "-rf", str(directory)], check=True, capture_output=True)
                    print(f"[MINIBUILD] Force delete successful: {directory}")
                else:
                    subprocess.run(["rmdir", "/s", "/q", str(directory)], check=True, capture_output=True, shell=True)
                    print(f"[MINIBUILD] Force delete successful: {directory}")
            except Exception:
                print(f"[MINIBUILD] Warning: Force delete also failed: {directory}")


__all__ = ["MiniSpecBuilder"]

