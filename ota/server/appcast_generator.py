import os
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from jinja2 import Environment, FileSystemLoader
from utils.logger_helper import logger_helper as logger

class AppcastGenerator:
    def __init__(self, server_root, signatures_dir, template_name='appcast_template.xml'):
        self.server_root = server_root
        self.signatures_dir = signatures_dir
        self.env = Environment(loader=FileSystemLoader(server_root))
        self.template = self.env.get_template(template_name)
    
    def _calculate_sha256(self, file_path):
        """Calculate SHA256 hash of a file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def _extract_version_from_filename(self, filename):
        """Extract version from filename like eCan-1.0.0-macos-aarch64.pkg"""
        import re
        # Try eCan-{version}-{platform} pattern (macOS/Windows/Linux standard naming)
        # eCan-1.0.0-macos-aarch64.pkg -> 1.0.0
        # eCan-1.2.3-beta.1-windows-amd64-Setup.exe -> 1.2.3-beta.1
        match = re.search(r'-(\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)(?:\.\d+)?)?)(?:-(?:macos|darwin|windows|linux|amd64|aarch64|arm64|x86_64))', filename)
        if match:
            return match.group(1)

        # Try ecan-{version}_{arch}.deb pattern (DEB package naming) - OLD format
        # ecan-1.0.0_amd64.deb -> 1.0.0
        # Non-greedy +? is required: without it, \d+ greedily consumes "1.0.0_a"
        # leaving nothing for the trailing "_" to match.
        match = re.search(r'ecan-(\d+?\.\d+?\.\d+?(?:-(?:alpha|beta|rc)(?:\.\d+)?)?)_', filename)
        if match:
            return match.group(1)
        
        # Try eCan-{version}-linux-{arch}.deb pattern (NEW format)
        # eCan-1.0.0-linux-amd64.deb -> 1.0.0
        match = re.search(r'eCan-(\d+?\.\d+?\.\d+?(?:-(?:alpha|beta|rc)(?:\.\d+)?)?)-linux-', filename)
        if match:
            return match.group(1)

        # Fallback: read from VERSION file
        try:
            project_root = Path(self.server_root).parent.parent
            version_file = project_root / "VERSION"
            if version_file.exists():
                return version_file.read_text().strip()
        except Exception:
            pass
        
        return None
    
    def _get_release_notes_from_changelog(self, version, language='en-US'):
        """
        Read release notes from CHANGELOG.md for specified version (with i18n support)
        
        Args:
            version: Version number (e.g., "1.0.1")
            language: Language code (e.g., 'en-US', 'zh-CN')
        
        Returns:
            HTML formatted release notes
        """
        try:
            project_root = Path(self.server_root).parent.parent
            
            # Select CHANGELOG for the specified language
            if language == 'zh-CN':
                changelog_path = project_root / "CHANGELOG.zh-CN.md"
            else:
                changelog_path = project_root / "CHANGELOG.md"
            
            if not changelog_path.exists():
                logger.warning(f"[APPCAST] CHANGELOG not found: {changelog_path}")
                return f"<h2>eCan.ai {version}</h2><p>Release notes not available.</p>"
            
            with open(changelog_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse Markdown and extract content for the specified version
            pattern = rf'## \[{re.escape(version)}\].*?\n(.*?)(?=\n## \[|\Z)'
            match = re.search(pattern, content, re.DOTALL)
            
            if not match:
                return f"<h2>eCan.ai {version}</h2><p>Release notes not available.</p>"
            
            notes_markdown = match.group(1).strip()
            
            # Simple Markdown to HTML conversion
            html = self._markdown_to_html(notes_markdown)
            
            return f"<h2>eCan.ai {version}</h2>{html}"
        
        except Exception as e:
            logger.warning(f"[APPCAST] Could not read release notes: {e}")
            return f"<h2>eCan.ai {version}</h2><p>Release notes not available.</p>"
    
    def _markdown_to_html(self, markdown_text):
        """Simple Markdown to HTML conversion"""
        html_lines = []
        current_list = []
        
        for line in markdown_text.split('\n'):
            line = line.strip()
            
            if not line:
                if current_list:
                    html_lines.append('<ul>')
                    html_lines.extend(current_list)
                    html_lines.append('</ul>')
                    current_list = []
                continue
            
            # ### heading
            if line.startswith('### '):
                if current_list:
                    html_lines.append('<ul>')
                    html_lines.extend(current_list)
                    html_lines.append('</ul>')
                    current_list = []
                title = line[4:].strip()
                html_lines.append(f'<h3>{title}</h3>')
            
            # - list item
            elif line.startswith('- '):
                item = line[2:].strip()
                item = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', item)
                item = re.sub(r'`(.*?)`', r'<code>\1</code>', item)
                current_list.append(f'  <li>{item}</li>')
            
            # Regular paragraph
            else:
                if current_list:
                    html_lines.append('<ul>')
                    html_lines.extend(current_list)
                    html_lines.append('</ul>')
                    current_list = []
                line = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
                line = re.sub(r'`(.*?)`', r'<code>\1</code>', line)
                html_lines.append(f'<p>{line}</p>')
        
        # Handle final list
        if current_list:
            html_lines.append('<ul>')
            html_lines.extend(current_list)
            html_lines.append('</ul>')
        
        return '\n'.join(html_lines)
    
    def _scan_dist_directory(self, dist_dir):
        """
        Scan dist directory and dynamically calculate file info

        Returns:
            dict: ``{filename: {file_size, sha256, version, os_type, arch}}``

            ``os_type`` is one of ``"macos"``, ``"windows"``, ``"linux"``.
            ``arch`` is one of ``"amd64"``, ``"aarch64"``. Existing appcast
            callers (Sparkle XML render) only read ``file_size`` /
            ``sha256`` / ``version``; the new keys are additive and let
            ``build_latest_json`` map packages to the
            ``platforms.{platform}-{arch}`` slots used by the public
            latest.json schema.
        """
        dist_path = Path(dist_dir)
        if not dist_path.exists():
            logger.warning(f"[APPCAST] Dist directory not found: {dist_dir}")
            return {}

        # Package patterns to search for
        # NOTE: Pattern order matters - more specific patterns first to avoid false matches
        patterns = [
            "eCan-*-macos-*.pkg",
            "eCan-*-macos-*.dmg",
            "eCan-*-windows-*-Setup.exe",
            "eCan-*-windows-*.msi",
            "eCan-*-linux-*.tar.gz",
            "eCan-*-linux-*.AppImage",
            # DEB packages: eCan-{version}-linux-amd64.deb
            "eCan-*-linux-amd64.deb",
            "eCan-*-linux-aarch64.deb",
        ]

        packages = {}

        for pattern in patterns:
            for pkg_file in dist_path.glob(pattern):
                if not pkg_file.is_file():
                    continue

                logger.info(f"[APPCAST] 📦 Found package: {pkg_file.name}")

                # Extract version from filename
                version = self._extract_version_from_filename(pkg_file.name)
                if version:
                    logger.info(f"[APPCAST]    Version: {version}")

                # Calculate file size
                file_size = pkg_file.stat().st_size
                logger.info(f"[APPCAST]    Size: {file_size:,} bytes ({file_size / (1024**3):.2f} GB)")

                # Calculate SHA256
                logger.info(f"[APPCAST]    Calculating SHA256...")
                signature = self._calculate_sha256(pkg_file)
                logger.info(f"[APPCAST]    SHA256: {signature[:16]}...")

                os_type = (
                    "macos" if ("darwin" in pkg_file.name or "macos" in pkg_file.name)
                    else "windows" if "windows" in pkg_file.name
                    else "linux"
                )
                arch = self._extract_arch_from_filename(pkg_file.name)

                packages[pkg_file.name] = {
                    "file_size": file_size,
                    "sha256": signature,
                    # Keep ``signature`` for backward compat with the existing
                    # Sparkle XML template (``item.signature``).
                    "signature": signature,
                    "version": version,
                    "os_type": os_type,
                    "arch": arch,
                }

        return packages

    def _extract_arch_from_filename(self, filename: str) -> Optional[str]:
        """Extract CPU arch from an ``eCan-{version}-{platform}-{arch}.ext``
        filename.

        Returns ``"aarch64"`` / ``"amd64"`` / ``"x86_64"`` / ``"arm64"`` or
        ``None`` if no arch token is found. Only one arch is reported per
        filename — callers that need a canonical key should map ``arm64``
        and ``x86_64`` to ``aarch64`` / ``amd64`` themselves.
        """
        for arch_token in ("aarch64", "amd64", "arm64", "x86_64"):
            if f"-{arch_token}" in filename or f"_{arch_token}" in filename:
                return arch_token
        return None

    # Legacy methods removed - use generate_dynamic() instead
    # Old signature-file-based methods are no longer needed
    
    def generate_dynamic(self, base_url, dist_dir=None, version=None, language='en-US'):
        """
        Dynamically generate appcast by scanning dist directory (with i18n support)
        No pre-generated signature files needed
        
        Args:
            base_url: Base URL for downloads
            dist_dir: Distribution directory (default: project_root/dist)
            version: Version number (default: auto-detect from VERSION file)
            language: Language code (e.g., 'en-US', 'zh-CN')
        
        Returns:
            str: Generated XML content or None if failed
        """
        try:
            # Determine dist directory
            if dist_dir is None:
                project_root = Path(self.server_root).parent.parent
                dist_dir = project_root / "dist"
            else:
                dist_dir = Path(dist_dir)
            
            # Determine version
            if version is None:
                project_root = Path(self.server_root).parent.parent
                version_file = project_root / "VERSION"
                if version_file.exists():
                    version = version_file.read_text().strip()
                else:
                    logger.warning("[APPCAST] VERSION file not found, using default 1.0.0")
                    version = "1.0.0"
            
            logger.info(f"[APPCAST] 🚀 Generating dynamic appcast for version {version}")
            logger.info(f"[APPCAST] 📁 Scanning dist directory: {dist_dir}")
            
            # Scan dist directory and calculate file info
            packages = self._scan_dist_directory(dist_dir)
            
            if not packages:
                logger.warning("[APPCAST] ⚠️  No packages found in dist directory")
                return None
            
            # Build items for template
            items = []
            for filename, data in packages.items():
                os_type = "macos" if ("darwin" in filename or "macos" in filename) else "windows" if "windows" in filename else "linux"
                
                # Use version from filename if available, otherwise use parameter
                pkg_version = data.get('version') or version
                
                # Get description from CHANGELOG (with language support)
                description = self._get_release_notes_from_changelog(pkg_version, language=language)
                
                item = {
                    'title': f'Version {pkg_version}',
                    'description': description,
                    'pub_date': datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000'),
                    'download_url': f'{base_url}/downloads/{filename}',
                    'version': pkg_version,
                    'os': os_type,
                    'file_size': data.get('file_size', 0),
                    'signature': data.get('signature', '')
                }
                items.append(item)
            
            if not items:
                logger.warning("[APPCAST] ⚠️  No items to add to appcast")
                return None
            
            # Render template
            xml_content = self.template.render(
                base_url=base_url,
                build_date=datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000'),
                items=items
            )
            
            # Save to file
            output_path = os.path.join(self.server_root, 'appcast.xml')
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)
            
            logger.info(f"[APPCAST] ✅ Dynamic appcast generated: {output_path}")
            logger.info(f"[APPCAST] 📦 Contains {len(items)} update items")
            
            return xml_content
            
        except Exception as e:
            logger.error(f"[APPCAST] ❌ Dynamic generation failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    # Legacy generate_appcast() method removed
    # Use generate_dynamic() instead - it scans dist directory automatically

    def build_latest_json(self, base_url: str, dist_dir=None,
                          channel: str = "stable",
                          environment: str = "development") -> Optional[dict]:
        """
        Build a ``latest.json`` payload that mirrors what
        ``build_system/scripts/generate_appcast.py::generate_latest_json``
        uploads to S3/COS. Used by the local OTA test server's
        ``/latest.json`` route so dev-environment builds don't have to
        round-trip through public storage.

        The schema is intentionally the same on-wire shape (same
        top-level keys, same per-platform sub-keys) so a dev client
        reads either source identically. Differences vs the remote
        upload path:

          - ``url`` is built from ``base_url + /downloads/{filename}``
            (the local server's static download mount), not from the
            S3/COS bucket.
          - ``accelerated_url`` is omitted because the local server
            has no CloudFront / COS CDN variant.
          - No incremental merge: each request rebuilds from ``dist/``
            in full. This is fine for the dev test server (single
            producer, single consumer) and avoids the read-modify-write
            state that the remote pipeline needs.

        Args:
            base_url: Origin serving this server, e.g.
                ``"http://127.0.0.1:8080"``. Used to build per-platform
                ``url`` fields so a click-through on dev downloads
                from the local file, not from S3.
            dist_dir: Directory to scan for built packages. Defaults
                to ``<project_root>/dist``.
            channel: Release channel label written into the payload
                (``"stable"`` unless caller overrides).
            environment: Environment label written into the payload
                (``"development"`` unless caller overrides).

        Returns:
            ``dict`` ready to ``json.dumps(...)`` or ``None`` if no
            packages were found in ``dist_dir``.
        """
        from packaging import version as _pkg_version

        if dist_dir is None:
            project_root = Path(self.server_root).parent.parent
            dist_dir = project_root / "dist"
        else:
            dist_dir = Path(dist_dir)

        packages = self._scan_dist_directory(dist_dir)
        if not packages:
            logger.warning("[LATEST] ⚠️  No packages found in dist — cannot build latest.json")
            return None

        # Group packages by ``{os_type}-{arch}`` slot. The remote
        # generator iterates (platform × arch) explicitly; we recover
        # the same slot from each filename so the local server does
        # not need a hardcoded platform/arch list.
        # Map filename-token arch keys to the canonical pair the
        # public schema uses (aarch64 / amd64).
        arch_aliases = {
            "aarch64": "aarch64", "arm64": "aarch64",
            "amd64": "amd64", "x86_64": "amd64",
        }
        slots: Dict[str, dict] = {}
        for filename, data in packages.items():
            os_type = data.get("os_type")
            arch_raw = data.get("arch")
            if not os_type or not arch_raw:
                logger.warning(
                    f"[LATEST] Skipping {filename} — cannot derive "
                    f"(os_type, arch) from filename"
                )
                continue
            arch = arch_aliases.get(arch_raw, arch_raw)
            slot = f"{os_type}-{arch}"
            # If multiple builds share a slot, keep the one with the
            # highest version so the dev client sees the most recent
            # drop (mirrors the remote "max over platforms" rule).
            existing = slots.get(slot)
            if existing is None:
                slots[slot] = {"filename": filename, **data}
            else:
                try:
                    if _pkg_version.parse(data.get("version") or "0.0.0") > \
                       _pkg_version.parse(existing.get("version") or "0.0.0"):
                        slots[slot] = {"filename": filename, **data}
                except Exception:
                    # Fall back to lexical compare if ``packaging``
                    # can't parse either version.
                    if (data.get("version") or "") > (existing.get("version") or ""):
                        slots[slot] = {"filename": filename, **data}

        if not slots:
            logger.warning("[LATEST] ⚠️  No usable platform/arch slots — cannot build latest.json")
            return None

        base_url = base_url.rstrip("/")
        platforms: Dict[str, dict] = {}
        for slot, info in slots.items():
            version = info.get("version") or "0.0.0"
            platforms[slot] = {
                "version": version,
                "url": f"{base_url}/downloads/{info['filename']}",
                "file_size": info.get("file_size", 0),
                "sha256": info.get("sha256") or info.get("signature", ""),
                "signature": info.get("signature", ""),
            }

        # Global ``version`` is the max version across all platforms
        # (mirrors the remote generator's invariant).
        all_versions = [p.get("version", "0.0.0") for p in platforms.values()]
        try:
            global_version = max(all_versions, key=lambda v: _pkg_version.parse(v))
        except Exception:
            global_version = max(all_versions) if all_versions else "0.0.0"

        payload = {
            "version": global_version,
            "channel": channel,
            "environment": environment,
            "updated_at": datetime.now().isoformat(),
            "platforms": platforms,
        }
        logger.info(
            f"[LATEST] ✅ Built latest.json: version={global_version}, "
            f"platforms={sorted(platforms.keys())}"
        )
        return payload

