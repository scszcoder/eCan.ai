import os
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime
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
        # Try to extract version from filename
        import re
        # Match version pattern: X.Y.Z (stop before platform name)
        # eCan-1.0.0-macos-aarch64.pkg -> 1.0.0
        # eCan-1.2.3-beta.1-windows-amd64.exe -> 1.2.3-beta.1
        match = re.search(r'-(\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)(?:\.\d+)?)?)(?:-(?:macos|darwin|windows|linux|amd64|aarch64|arm64|x86_64))', filename)
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
            dict: {filename: {file_size, signature, version}}
        """
        dist_path = Path(dist_dir)
        if not dist_path.exists():
            logger.warning(f"[APPCAST] Dist directory not found: {dist_dir}")
            return {}
        
        # Package patterns to search for
        patterns = [
            "eCan-*-macos-*.pkg",
            "eCan-*-macos-*.dmg",
            "eCan-*-windows-*-Setup.exe",
            "eCan-*-windows-*.msi",
            "eCan-*-linux-*.tar.gz",
            "eCan-*-linux-*.AppImage",
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
                
                packages[pkg_file.name] = {
                    "file_size": file_size,
                    "signature": signature,
                    "version": version
                }
        
        return packages

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

