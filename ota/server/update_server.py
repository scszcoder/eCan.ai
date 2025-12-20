#!/usr/bin/env python3
"""
Simple OTA Update Server
For testing and development, supports dynamic appcast.xml generation
"""

import logging
import os
import sys
from flask import Flask, jsonify, request, send_file, Response
from pathlib import Path

# Add project root to Python path to resolve imports when run as a script
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ota.server.appcast_generator import AppcastGenerator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize appcast generator
server_dir = Path(__file__).parent
appcast_gen = AppcastGenerator(server_dir, server_dir)

# Server configuration
SERVER_CONFIG = {
    "host": "0.0.0.0",
    "port": 8080,
    "debug": False
}

def _markdown_to_html(markdown_text: str) -> str:
    """
    Simple Markdown to HTML conversion
    Supports: ### headings, - lists, **bold**, `code`
    
    Args:
        markdown_text: Markdown text
    
    Returns:
        HTML text
    """
    import re
    html_lines = []
    current_list = []
    
    for line in markdown_text.split('\n'):
        line = line.strip()
        
        if not line:
            # Empty line: end current list
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
            # Handle **bold**
            item = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', item)
            # Handle `code`
            item = re.sub(r'`(.*?)`', r'<code>\1</code>', item)
            current_list.append(f'  <li>{item}</li>')
        
        # Regular paragraph
        else:
            if current_list:
                html_lines.append('<ul>')
                html_lines.extend(current_list)
                html_lines.append('</ul>')
                current_list = []
            # Handle **bold**
            line = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
            # Handle `code`
            line = re.sub(r'`(.*?)`', r'<code>\1</code>', line)
            html_lines.append(f'<p>{line}</p>')
    
    # Handle final list
    if current_list:
        html_lines.append('<ul>')
        html_lines.extend(current_list)
        html_lines.append('</ul>')
    
    return '\n'.join(html_lines)

def _find_installation_package(requested_filename: str, dist_dir: Path) -> Path:
    """
    Intelligently find installation package file
    
    Strategy:
    1. Direct filename match
    2. Fuzzy match (ignore version number)
    3. Match platform and architecture
    
    Args:
        requested_filename: Requested filename
        dist_dir: dist directory path
    
    Returns:
        Path: Found file path, returns None if not found
    """
    if not dist_dir.exists():
        logger.warning(f"Dist directory not found: {dist_dir}")
        return None
    
    # 1. Direct match
    direct_path = dist_dir / requested_filename
    if direct_path.exists():
        logger.info(f"Found exact match: {direct_path}")
        return direct_path
    
    # 2. Extract key information from requested file
    import re
    
    # Extract platform and architecture information
    platform_patterns = {
        'macos': r'(macos|darwin)',
        'windows': r'windows',
        'linux': r'linux'
    }
    
    arch_patterns = {
        'aarch64': r'(aarch64|arm64)',
        'amd64': r'(amd64|x86_64|x64)',
        'x86': r'(x86|i386)'
    }
    
    # Extract file extension
    ext = Path(requested_filename).suffix
    
    # Detect platform
    detected_platform = None
    for platform, pattern in platform_patterns.items():
        if re.search(pattern, requested_filename, re.IGNORECASE):
            detected_platform = platform
            break
    
    # Detect architecture
    detected_arch = None
    for arch, pattern in arch_patterns.items():
        if re.search(pattern, requested_filename, re.IGNORECASE):
            detected_arch = arch
            break
    
    logger.info(f"Searching for: platform={detected_platform}, arch={detected_arch}, ext={ext}")
    
    # 3. Search for matching files in dist directory
    candidates = []
    
    for file_path in dist_dir.glob(f"*{ext}"):
        if not file_path.is_file():
            continue
        
        filename = file_path.name
        score = 0
        
        # Match platform
        if detected_platform:
            for pattern in platform_patterns[detected_platform].split('|'):
                if pattern.strip('()') in filename.lower():
                    score += 10
                    break
        
        # Match architecture
        if detected_arch:
            for pattern in arch_patterns[detected_arch].split('|'):
                if pattern.strip('()') in filename.lower():
                    score += 5
                    break
        
        # Match extension (already filtered by glob)
        score += 1
        
        if score > 0:
            candidates.append((score, file_path))
    
    # Sort by score and return best match
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_match = candidates[0][1]
        logger.info(f"Found best match (score={candidates[0][0]}): {best_match}")
        return best_match
    
    logger.warning(f"No matching file found for: {requested_filename}")
    return None

# Update information configuration
# NOTE: This legacy config is no longer used. 
# The system now uses dynamic appcast generation from /appcast.xml endpoint.
# Keeping this for backward compatibility with /api/check endpoint.
UPDATE_CONFIG = {
    "latest_version": "1.0.0",  # Read from VERSION file or dist directory
    "min_version": "1.0.0",
    "updates": {}  # Dynamically populated from dist directory
}

@app.route('/api/check', methods=['GET'])
@app.route('/api/check-update', methods=['GET'])
def check_update():
    """Check update API"""
    try:
        # Get client information
        app_name = request.args.get('app', 'ecan')
        current_version = request.args.get('version', '1.0.0')
        platform = request.args.get('platform', 'windows')
        arch = request.args.get('arch', 'x64')
        
        logger.info(f"Update check: {app_name} v{current_version} on {platform}-{arch}")
        
        # Check if update is available - read from VERSION file
        try:
            project_root = Path(__file__).parent.parent.parent
            version_file = project_root / "VERSION"
            if version_file.exists():
                base_version = version_file.read_text().strip()
                # For testing: increment patch version to simulate available update
                # e.g., 1.0.0 -> 1.0.1
                import re
                match = re.match(r'(\d+)\.(\d+)\.(\d+)', base_version)
                if match:
                    major, minor, patch = match.groups()
                    latest_version = f"{major}.{minor}.{int(patch) + 1}"
                    logger.info(f"[TEST MODE] Simulating update: {base_version} -> {latest_version}")
                else:
                    latest_version = base_version
            else:
                latest_version = UPDATE_CONFIG['latest_version']
        except Exception:
            latest_version = UPDATE_CONFIG['latest_version']
        # Semantic version comparison (simplified implementation without third-party dependencies)
        def _to_version_tuple(v: str):
            import re
            parts = re.split(r'[.+-]', v)
            nums = []
            for p in parts:
                if p.isdigit():
                    nums.append(int(p))
                else:
                    # Stop at non-numeric segment to avoid including pre-release tags in comparison
                    break
            # Normalize length to avoid inconsistent comparison between 1.2 and 1.2.0
            while len(nums) < 3:
                nums.append(0)
            return tuple(nums[:3])
        has_update = _to_version_tuple(current_version) < _to_version_tuple(latest_version)
        
        response = {
            "update_available": has_update,
            "current_version": current_version,
            "latest_version": latest_version
        }
        
        if has_update:
            # ✅ Dynamically read description from CHANGELOG.md
            description = ""
            try:
                project_root = Path(__file__).parent.parent.parent
                changelog_path = project_root / "CHANGELOG.md"
                
                logger.info(f"[CHECK] Reading CHANGELOG from: {changelog_path}")
                
                if not changelog_path.exists():
                    logger.warning(f"[CHECK] CHANGELOG not found at: {changelog_path}")
                    description = f"<h2>eCan.ai {latest_version}</h2><p>Release notes not available.</p>"
                else:
                    with open(changelog_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Parse Markdown and extract content for the specified version
                    import re
                    pattern = rf'## \[{re.escape(latest_version)}\].*?\n(.*?)(?=\n## \[|\Z)'
                    match = re.search(pattern, content, re.DOTALL)
                    
                    if not match:
                        logger.warning(f"[CHECK] Version {latest_version} not found in CHANGELOG")
                        description = f"<h2>eCan.ai {latest_version}</h2><p>Release notes not available.</p>"
                    else:
                        notes_markdown = match.group(1).strip()
                        
                        # Simple Markdown to HTML conversion
                        html = _markdown_to_html(notes_markdown)
                        
                        description = f"<h2>eCan.ai {latest_version}</h2>{html}"
                        logger.info(f"[CHECK] Successfully loaded release notes for version {latest_version}")
                        
            except Exception as e:
                logger.error(f"[CHECK] Error loading release notes: {e}", exc_info=True)
                description = f"<h2>eCan.ai {latest_version}</h2><p>Release notes not available.</p>"
            
            # ✅ Dynamically scan dist directory to get file information
            signature = ""
            file_size = 0
            
            try:
                project_root = Path(__file__).parent.parent.parent
                dist_dir = project_root / "dist"
                
                # Find corresponding file based on platform
                patterns = {
                    'darwin': ["eCan-*-macos-*.pkg", "eCan-*-macos-*.dmg"],
                    'windows': ["eCan-*-windows-*-Setup.exe", "eCan-*-windows-*.msi"],
                    'linux': ["eCan-*-linux-*.tar.gz", "eCan-*-linux-*.AppImage"]
                }
                
                if platform in patterns:
                    for pattern in patterns[platform]:
                        for pkg_file in dist_dir.glob(pattern):
                            # Calculate file size
                            file_size = pkg_file.stat().st_size
                            
                            # Calculate SHA256
                            import hashlib
                            sha256_hash = hashlib.sha256()
                            with open(pkg_file, "rb") as f:
                                for byte_block in iter(lambda: f.read(4096), b""):
                                    sha256_hash.update(byte_block)
                            signature = sha256_hash.hexdigest()
                            
                            logger.info(f"[CHECK] Found package: {pkg_file.name}, size: {file_size}, sha256: {signature[:16]}...")
                            break
                        if file_size > 0:
                            break
            except Exception as e:
                logger.warning(f"Failed to scan dist directory: {e}")
            
            response.update({
                "description": description,
                "release_date": "",  # Can be extracted from CHANGELOG if needed
                "download_url": f"http://127.0.0.1:{SERVER_CONFIG['port']}/downloads/eCan-{latest_version}-{platform}-{arch}.pkg",
                "file_size": file_size,
                "signature": signature
            })
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download', methods=['GET'])
@app.route('/api/download-latest', methods=['GET'])
def download_latest():
    """Download latest version API"""
    try:
        platform = request.args.get('platform', 'windows')
        arch = request.args.get('arch', 'x64')
        
        # This should return the actual update file
        # For demonstration, we return a sample response
        return jsonify({
            "error": "Download not implemented in demo server",
            "message": "In production, this would return the actual update file"
        }), 501
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/appcast.xml', methods=['GET'])
def appcast():
    """Dynamically generate Sparkle/winSparkle appcast file by scanning dist directory (with i18n support)"""
    try:
        # Get request parameters
        version = request.args.get('version')  # Specified version
        base_url = request.args.get('base_url', f"http://{request.host}")
        
        # Auto-detect language if not specified
        language = request.args.get('language')
        if not language:
            # Try to detect from i18n system
            try:
                from ota.gui.i18n import _tr
                detected_lang = _tr.language  # e.g., 'zh-CN' or 'en-US'
                if detected_lang.startswith('zh'):
                    language = 'zh-CN'
                else:
                    language = 'en-US'
                logger.info(f"[APPCAST] Auto-detected language from i18n: {language}")
            except Exception as e:
                # Fallback to Accept-Language header
                accept_lang = request.headers.get('Accept-Language', '')
                if 'zh' in accept_lang.lower():
                    language = 'zh-CN'
                else:
                    language = 'en-US'
                logger.info(f"[APPCAST] Auto-detected language from Accept-Language: {language}")
        
        logger.info(f"[APPCAST] Request received: version={version}, base_url={base_url}, language={language}")
        
        # Get dist directory
        project_root = Path(__file__).parent.parent.parent
        dist_dir = project_root / "dist"
        
        # ✅ Use dynamic generation - scans dist directory and calculates signatures
        logger.info("[APPCAST] 🚀 Using dynamic generation (no signature files needed)")
        xml_content = appcast_gen.generate_dynamic(
            base_url=base_url,
            dist_dir=dist_dir,
            version=version,
            language=language
        )
        
        if not xml_content:
            logger.error("[APPCAST] ❌ Dynamic generation failed")
            return "Appcast generation failed - no packages found in dist directory", 404
        
        # Return generated file
        appcast_path = server_dir / "appcast.xml"
        if appcast_path.exists():
            logger.info(f"[APPCAST] ✅ Serving dynamically generated appcast")
            return send_file(str(appcast_path), mimetype='application/rss+xml')
        else:
            return "Generated appcast not found", 404
            
    except Exception as e:
        logger.error(f"[APPCAST] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return f"Error serving appcast: {str(e)}", 500

@app.route('/admin/generate-appcast', methods=['POST'])
def generate_appcast_admin():
    """Admin API: manually trigger dynamic appcast generation"""
    try:
        data = request.get_json() or {}
        version = data.get('version')
        base_url = data.get('base_url', 'http://127.0.0.1:8080')
        
        # Get dist directory
        project_root = Path(__file__).parent.parent.parent
        dist_dir = project_root / "dist"
        
        # Use dynamic generation
        xml_content = appcast_gen.generate_dynamic(
            base_url=base_url,
            dist_dir=dist_dir,
            version=version
        )
        
        if xml_content:
            return jsonify({
                "success": True,
                "message": "Dynamic appcast generated successfully",
                "appcast_url": f"{base_url}/appcast.xml"
            })
        else:
            return jsonify({
                "success": False,
                "message": "Dynamic appcast generation failed - no packages found"
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    # /admin/signatures route removed - no longer using signature files

@app.route('/downloads/<filename>', methods=['GET'])
def download_file(filename):
    """Provide real installation package download - dynamically finds files"""
    try:
        # Get project root directory
        project_root = Path(__file__).parent.parent.parent
        dist_dir = project_root / "dist"
        
        # ✅ Intelligently find file
        actual_file = _find_installation_package(filename, dist_dir)
        
        if not actual_file:
            logger.warning(f"File not found: {filename}")
            return jsonify({"error": f"File not found: {filename}"}), 404
        
        # Provide file download
        file_size = actual_file.stat().st_size
        logger.info(f"✅ Serving file: {actual_file.name} ({file_size / 1024 / 1024:.2f} MB)")
        
        return send_file(str(actual_file), as_attachment=True, download_name=filename)
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        return jsonify({"error": f"Download failed: {str(e)}"}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({"status": "ok", "service": "eCan.ai Update Server"})

@app.route('/', methods=['GET'])
def index():
    """Home page"""
    return jsonify({
        "service": "eCan.ai Update Server",
        "endpoints": [
            "/api/check-update",
            "/api/download-latest", 
            "/appcast.xml",
            "/health"
        ]
    })

def check_dependencies():
    """Check dependencies"""
    try:
        import flask
        logger.info("✓ Flask installed")
        return True
    except ImportError:
        logger.error("✗ Flask not installed, please run: pip install flask")
        return False

def main():
    """Main function"""
    print("=" * 50)
    print("eCan.ai Local OTA Test Server")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        logger.error("Dependency check failed, cannot start server")
        return
    
    logger.info("Starting eCan.ai Update Server...")
    logger.info("Available endpoints:")
    for rule in app.url_map.iter_rules():
        logger.info(f"  - {rule.methods} {rule.rule}")
    
    print("\nServer Information:")
    print(f"  - Address: http://127.0.0.1:{SERVER_CONFIG['port']}")
    print("  - Endpoints:")
    print("    * GET /api/check-update - Check for updates")
    print("    * GET /appcast.xml - Sparkle appcast file") 
    print("    * GET /health - Health check")
    print("    * GET / - Server information")
    
    print("\nStarting server...")
    print("Press Ctrl+C to stop server")
    print("-" * 50)
    
    try:
        app.run(
            host=SERVER_CONFIG["host"], 
            port=SERVER_CONFIG["port"], 
            debug=SERVER_CONFIG["debug"]
        )
    except KeyboardInterrupt:
        logger.info("Server stopped")

if __name__ == "__main__":
    main()