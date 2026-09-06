#!/usr/bin/env python3
"""
Generate Appcast XML files from S3 artifacts (Single Bucket Design)

Usage:
    python3 build_system/scripts/generate_appcast.py --env production
    python3 build_system/scripts/generate_appcast.py --env test --channel beta

Note: This script is backend-agnostic. It requires PyYAML and either:
  - cos-python-sdk-v5  (CN/COS backend)
  - boto3              (Intl/S3 backend)
  The appropriate SDK is imported lazily based on --app so both
  backends can share the same requirements: a COS build only needs
  cos-python-sdk-v5 + pyyaml + packaging; an S3 build needs boto3
  + pyyaml + packaging.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, List, Dict, Optional, Tuple
from xml.etree import ElementTree as ET

if TYPE_CHECKING:
    from qcloud_cos import CosConfig, CosS3Client
    from qcloud_cos.cos_exception import CosServiceError

# Project root
project_root = Path(__file__).parent.parent.parent
# Make repo-root packages importable when this script is invoked directly
# (e.g. `python3 build_system/scripts/generate_appcast.py`); running it as a
# file puts the script directory on sys.path[0] instead of the repo root,
# which breaks `from utils.app_config_loader import ...` and similar imports.
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# boto3 is only needed for the S3/intl backend. COS/CN uses
# cos-python-sdk-v5 exclusively. Import lazily inside the
# AppcastGenerator so the CN build (which only installs
# cos-python-sdk-v5 + pyyaml + packaging) never trips on
# a missing boto3. The HAS_COS flag gates which client gets
# instantiated.
HAS_S3 = False
HAS_COS = False

try:
    import yaml
except ImportError:
    print("[ERROR] PyYAML is required. Install it with: pip install PyYAML")
    sys.exit(1)


def get_git_commits_since_days(days: int = 5, version: str = None) -> List[Dict[str, str]]:
    """
    Get Git commit history from the last N days
    
    Args:
        days: Number of days to look back (default: 5)
        version: Version tag to use as reference point (optional)
    
    Returns:
        List of commit dictionaries with 'hash', 'date', 'author', 'message'
    """
    try:
        # Calculate date threshold
        since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # Build git log command
        # Format: hash|date|author|message
        cmd = [
            'git', 'log',
            f'--since="{since_date}"',
            '--pretty=format:%h|%ad|%an|%s',
            '--date=short',
            '--no-merges'  # Skip merge commits
        ]
        
        # If version tag exists, get commits since previous tag
        if version:
            try:
                # Try to find previous tag
                prev_tag_cmd = ['git', 'describe', '--tags', '--abbrev=0', f'v{version}^']
                result = subprocess.run(prev_tag_cmd, capture_output=True, text=True, cwd=project_root)
                if result.returncode == 0:
                    prev_tag = result.stdout.strip()
                    cmd = [
                        'git', 'log',
                        f'{prev_tag}..v{version}',
                        '--pretty=format:%h|%ad|%an|%s',
                        '--date=short',
                        '--no-merges'
                    ]
            except:
                pass  # Fall back to date-based filtering
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_root)
        
        if result.returncode != 0:
            return []
        
        commits = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('|', 3)
            if len(parts) == 4:
                commits.append({
                    'hash': parts[0],
                    'date': parts[1],
                    'author': parts[2],
                    'message': parts[3]
                })
        
        return commits
    
    except Exception as e:
        print(f"[WARN] Failed to get Git commits: {e}")
        return []


def generate_changelog_from_commits(version: str, commits: List[Dict[str, str]], language: str = 'en-US') -> str:
    """
    Generate CHANGELOG-style HTML from Git commits
    
    Args:
        version: Version number
        commits: List of commit dictionaries
        language: Language code
    
    Returns:
        HTML formatted changelog
    """
    if not commits:
        if language == 'zh-CN':
            return f"<h2>eCan.ai {version}</h2><p>暂无更新说明。</p>"
        else:
            return f"<h2>eCan.ai {version}</h2><p>Release notes not available.</p>"
    
    # Categorize commits by type (conventional commits)
    categorized = {
        'feat': [],
        'fix': [],
        'docs': [],
        'style': [],
        'refactor': [],
        'perf': [],
        'test': [],
        'chore': [],
        'other': []
    }
    
    for commit in commits:
        msg = commit['message']
        # Extract commit type (e.g., "feat:", "fix:")
        type_match = re.match(r'^(\w+)(?:\([^)]+\))?:\s*(.+)', msg)
        if type_match:
            commit_type = type_match.group(1).lower()
            commit_msg = type_match.group(2)
        else:
            commit_type = 'other'
            commit_msg = msg
        
        if commit_type in categorized:
            categorized[commit_type].append(commit_msg)
        else:
            categorized['other'].append(commit_msg)
    
    # Build HTML
    html_parts = [f"<h2>eCan.ai {version}</h2>"]
    
    # Add auto-generated notice
    if language == 'zh-CN':
        html_parts.append('<p style="color: #666; font-style: italic;">📝 以下内容由最近 Git 提交自动生成</p>')
    else:
        html_parts.append('<p style="color: #666; font-style: italic;">📝 Auto-generated from recent Git commits</p>')
    
    # Category labels
    category_labels = {
        'en-US': {
            'feat': 'Added',
            'fix': 'Fixed',
            'docs': 'Documentation',
            'refactor': 'Refactored',
            'perf': 'Performance',
            'other': 'Other Changes'
        },
        'zh-CN': {
            'feat': '新增功能',
            'fix': '问题修复',
            'docs': '文档更新',
            'refactor': '代码重构',
            'perf': '性能优化',
            'other': '其他变更'
        }
    }
    
    labels = category_labels.get(language, category_labels['en-US'])
    
    # Add categorized commits
    for category in ['feat', 'fix', 'docs', 'refactor', 'perf', 'other']:
        items = categorized[category]
        if items:
            label = labels.get(category, category.title())
            html_parts.append(f'<h3>{label}</h3>')
            html_parts.append('<ul>')
            for item in items:
                html_parts.append(f'  <li>{item}</li>')
            html_parts.append('</ul>')
    
    return '\n'.join(html_parts)


def get_release_notes_from_changelog(version: str, changelog_path: Optional[Path] = None, language: str = 'en-US') -> str:
    """
    Read release notes from CHANGELOG.md for specified version (with i18n support)
    Falls back to auto-generating from Git commits if version not found
    
    Args:
        version: Version number (e.g., "1.0.1", "1.0.0-sim", "1.0.0-gui-v2-eefbe438")
        changelog_path: Path to CHANGELOG.md file, defaults to project root
        language: Language code (e.g., 'en-US', 'zh-CN')
    
    Returns:
        HTML formatted release notes
    """
    if changelog_path is None:
        # Prefer localized CHANGELOG for specified language
        if language != 'en-US':
            localized_changelog = project_root / f"CHANGELOG.{language}.md"
            if localized_changelog.exists():
                changelog_path = localized_changelog
            else:
                # Fallback to English version
                changelog_path = project_root / "CHANGELOG.md"
        else:
            changelog_path = project_root / "CHANGELOG.md"
    
    try:
        # Extract base version number (remove suffixes like -sim, -gui-v2-eefbe438)
        base_version_match = re.match(r'(\d+\.\d+\.\d+)', version)
        if base_version_match:
            base_version = base_version_match.group(1)
        else:
            base_version = version
        
        # Try to read from CHANGELOG.md first
        if changelog_path.exists():
            with open(changelog_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse Markdown and extract content for the base version
            # Match format: ## [1.0.1] - 2025-11-21
            pattern = rf'## \[{re.escape(base_version)}\].*?\n(.*?)(?=\n## \[|\Z)'
            match = re.search(pattern, content, re.DOTALL)
            
            if match:
                notes_markdown = match.group(1).strip()
                html = markdown_to_html(notes_markdown)
                return f"<h2>eCan.ai {version}</h2>{html}"
        
        # CHANGELOG not found or version not in CHANGELOG
        # Fall back to auto-generating from Git commits
        print(f"[INFO] Version {base_version} not found in CHANGELOG, auto-generating from Git commits...")
        commits = get_git_commits_since_days(days=5, version=base_version)
        
        if commits:
            print(f"[INFO] Found {len(commits)} commits in the last 5 days")
            return generate_changelog_from_commits(version, commits, language)
        else:
            print(f"[WARN] No Git commits found for auto-generation")
            if language == 'zh-CN':
                return f"<h2>eCan.ai {version}</h2><p>暂无更新说明。</p>"
            else:
                return f"<h2>eCan.ai {version}</h2><p>Release notes not available.</p>"
    
    except Exception as e:
        print(f"[WARN] Could not read release notes from CHANGELOG: {e}")
        # Try Git fallback even on error
        try:
            commits = get_git_commits_since_days(days=5)
            if commits:
                return generate_changelog_from_commits(version, commits, language)
        except:
            pass
        
        if language == 'zh-CN':
            return f"<h2>eCan.ai {version}</h2><p>暂无更新说明。</p>"
        else:
            return f"<h2>eCan.ai {version}</h2><p>Release notes not available.</p>"


def markdown_to_html(markdown_text: str) -> str:
    """
    Simple Markdown to HTML conversion
    Supports: ### headings, - lists, **bold**
    
    Args:
        markdown_text: Markdown text
    
    Returns:
        HTML text
    """
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


# ---------------------------------------------------------------------------
# Per-user release helpers (mirror of ota/core/appcast.py::_split_user_prefix)
# ---------------------------------------------------------------------------
# These let the generator handle two on-S3 layouts in lockstep with the
# upload script:
#   * `releases/v{version}/...`            → universal builds (legacy)
#   * `releases/{prefix}_v{version}/...`   → user-targeted preview builds
#
# The directory name on S3 is also what we emit verbatim into the
# `<sparkle:version>` attribute, so the client-side splitter in
# ota/core/appcast.py picks the prefix back out without any extra hint.
# ---------------------------------------------------------------------------

# Reserved prefixes that must NEVER be misinterpreted as user prefixes;
# kept in sync with both release.yml and ota/core/appcast.py.
_RESERVED_PREFIXES = frozenset({
    'rc', 'beta', 'alpha', 'dev', 'nightly', 'pre', 'preview', 'snapshot'
})

# A user prefix is `[A-Za-z][A-Za-z0-9]{0,31}` followed by `_v<digits>`.
_PREFIXED_DIR_RE = re.compile(r'^([A-Za-z][A-Za-z0-9]{0,31})_v(\d.*)$')


def _to_release_dir(version: str, user_prefix: str = '') -> str:
    """Convert a (version, user_prefix) pair to its on-S3 directory name.

    Mirrors the logic in upload_to_s3.py::S3Uploader.release_dir so the
    write side and read side never disagree.

    Examples::

        ('1.0.0', '')       -> 'v1.0.0'
        ('1.0.0', 'songc')  -> 'songc_v1.0.0'      # unusual but legal
        ('26.05.04', 'songc')-> 'songc_v26.05.04'
        ('v1.0.0', '')      -> 'v1.0.0'            # already in dir form
        ('songc_v1.0.0', '')-> 'songc_v1.0.0'      # already in dir form
    """
    if not version:
        return version
    user_prefix = (user_prefix or '').strip().lower()
    # If `version` already looks like a directory name, return it verbatim.
    if version.startswith('v') or _PREFIXED_DIR_RE.match(version):
        return version
    if user_prefix:
        return f"{user_prefix}_v{version}"
    return f"v{version}"


def _split_release_dir(dir_name: str) -> Tuple[Optional[str], str]:
    """Split a release directory name into (user_prefix, version_core).

    `version_core` is the bare ``X.Y.Z[...]`` numeric string with the
    leading ``v`` stripped — same shape consumers like the CHANGELOG
    lookup already expect.

    Returns ``(None, dir_name_without_v)`` for universal builds.
    """
    if not dir_name:
        return None, dir_name
    m = _PREFIXED_DIR_RE.match(dir_name)
    if m:
        prefix = m.group(1).lower()
        if prefix in _RESERVED_PREFIXES:
            # A reserved keyword in the prefix slot means the dir was
            # never a user build (e.g. `rc_v1.0.0` is malformed). Treat
            # it as universal so we don't accidentally hide it from the
            # default appcast.
            return None, dir_name.lstrip('v')
        return prefix, m.group(2)
    return None, dir_name[1:] if dir_name.startswith('v') else dir_name


def _normalize_last_modified(value) -> datetime:
    """Normalize an S3 ``LastModified`` value to a tz-aware UTC ``datetime``.

    boto3 returns ``datetime`` for AWS S3, but the COS S3-compatible client
    returns an ISO-8601 *string* (e.g. ``'2026-08-13T19:02:33.000Z'``).
    Downstream code (the chronological sort and the pubDate formatter)
    requires a real datetime, so:

      * strings are parsed via :func:`datetime.fromisoformat` (after
        replacing a trailing ``Z``);
      * naive ``datetime`` objects are tagged as UTC, since the XML
        ``pubDate`` is rendered with a fixed ``+0000`` offset.

    Returns:
        A tz-aware ``datetime`` (always UTC).
    """
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


class AppcastGenerator:
    """
    Generate Appcast XML files from S3 artifacts
    """

    def __init__(
        self,
        environment: str,
        channel: str = None,
        specific_version: str = None,
        user_prefix: str = '',
        app_id: str = 'intl',
    ):
        """
        Initialize the appcast generator

        Args:
            environment: Target environment (dev, test, staging, production, simulation)
            channel: Release channel (overrides environment default)
            specific_version: Specific version to generate appcast for (e.g., '1.0.1')
                            If None, scans all versions on S3
            user_prefix: Optional per-user release prefix (lowercase). When
                provided alongside ``specific_version``, the generator
                resolves the on-S3 directory as ``{prefix}_v{version}``.
                For the auto-scan path it's only used in diagnostic logging
                — the scan picks up every directory layout regardless.
            app_id: App identifier ('cn' | 'intl') for per-app appcast generation.
        """
        self.environment = environment
        self.user_prefix = (user_prefix or '').strip().lower()
        self.app_id = app_id

        # Source app display info + storage backend from apps/{app_id}/config/app_manifest.json
        # via utils.app_config_loader (single source of truth). AppConfigLoader
        # itself never raises — it returns safe defaults — so no try/except
        # is needed here.
        from utils.app_config_loader import AppConfigLoader
        _loader = AppConfigLoader(app_id)
        self.app_name = _loader.app_name
        self.app_short_name = _loader.app_short_name
        self.storage_backend = 'cos' if _loader.cloud_provider == 'tencent' else 's3'

        # app_prefix is the on-disk artifact name (e.g. eCan.cn vs eCan).
        self.app_prefix = self.app_short_name
        # Convert the (specific_version, user_prefix) pair into the
        # verbatim S3 directory name once at construction time so every
        # downstream call site agrees. ``None`` => auto-scan mode.
        self.specific_version = (
            _to_release_dir(specific_version, self.user_prefix)
            if specific_version
            else None
        )
        
        # Load configuration directly from YAML file
        config = self._load_config()

        if self.storage_backend == 'cos':
            try:
                from qcloud_cos import CosConfig, CosS3Client
                from qcloud_cos.cos_exception import CosServiceError
            except ImportError:
                print("[ERROR] --app cn requires cos-python-sdk-v5. Install it with:")
                print("    pip install cos-python-sdk-v5")
                sys.exit(1)
            # The helpers below (_cos_list_objects, _cos_get_object,
            # _cos_put_object) reference CosServiceError by name; keep them
            # qualified so the intl backend never needs to bind them.
            self._CosConfig = CosConfig
            self._CosS3Client = CosS3Client
            self._CosServiceError = CosServiceError

            self.bucket = config['common'].get('cos_bucket', 'ecan-releases-1251680599')
            self.region = config['common'].get('cos_region', 'ap-shanghai')
            env_config = config['environments'].get(environment, {})
            self.prefix = env_config.get('cos_prefix', environment)
            self.channel = channel or env_config.get('channel', 'stable')
            self.base_path = ''

            # Initialize COS client
            secret_id = os.environ.get('ECAN_TENCENT_SECRET_ID', '')
            secret_key = os.environ.get('ECAN_TENCENT_SECRET_KEY', '')
            if not secret_id or not secret_key:
                print("[ERROR] ECAN_TENCENT_SECRET_ID and ECAN_TENCENT_SECRET_KEY must be set for COS backend")
                sys.exit(1)
            cos_region_map = {
                'ap-beijing': 'ap-beijing-1',
                'ap-shanghai': 'ap-shanghai',
                'ap-nanjing': 'ap-nanjing-1',
            }
            cos_region = cos_region_map.get(self.region, self.region)
            cos_config = self._CosConfig(Region=cos_region, SecretId=secret_id, SecretKey=secret_key)
            self.cos = self._CosS3Client(cos_config)
            self.s3 = None
        else:
            # boto3 is only installed in the intl requirements set
            # (build_system/scripts/requirements.txt). CN does not have it.
            # Import here so the CN build — which only installs
            # cos-python-sdk-v5 + pyyaml + packaging — never trips on
            # a missing boto3.
            try:
                import boto3
                from botocore.exceptions import ClientError, NoCredentialsError
            except ImportError:
                print("[ERROR] boto3 is required for S3/intl backend. Install it with:")
                print("    pip install boto3")
                sys.exit(1)

            self.bucket = config['common']['s3_bucket']
            self.region = config['common']['s3_region']

            # Handle S3_BASE_PATH environment variable
            env_base_path = os.environ.get('S3_BASE_PATH', '')
            if env_base_path == 'releases':
                self.base_path = ''
            else:
                self.base_path = env_base_path or config['common'].get('s3_base_path', '')

            env_config = config['environments'].get(environment, {})
            self.prefix = env_config.get('s3_prefix', environment)
            self.channel = channel or env_config.get('channel', 'stable')

            # Initialize S3 client
            try:
                self.s3 = boto3.client('s3', region_name=self.region)
            except NoCredentialsError:
                print("[ERROR] AWS credentials not found")
                sys.exit(1)
            self.cos = None

    def _cos_list_objects(self, prefix: str) -> List[Dict]:
        """List objects in COS bucket with given prefix, returns same shape as S3.list_objects_v2"""
        try:
            response = self.cos.list_objects(
                Bucket=self.bucket,
                Prefix=prefix,
            )
            # COS returns 'Contents' as list directly (not paginated here)
            return response.get('Contents', [])
        except self._CosServiceError:
            return []

    def _cos_get_object(self, key: str) -> Optional[Dict]:
        """Get object metadata + body from COS"""
        try:
            response = self.cos.get_object(Bucket=self.bucket, Key=key)
            return response
        except self._CosServiceError:
            return None

    def _cos_put_object(self, key: str, body: bytes, content_type: str = 'application/octet-stream', extra: Optional[Dict] = None) -> bool:
        """Put object to COS bucket"""
        try:
            kwargs = {'Bucket': self.bucket, 'Key': key, 'Body': body, 'ContentType': content_type}
            if extra:
                kwargs.update(extra)
            self.cos.put_object(**kwargs)
            return True
        except self._CosServiceError:
            return False

    def _load_config(self) -> dict:
        """
        Load OTA configuration from YAML file
        
        Returns:
            Configuration dictionary
        """
        config_file = project_root / 'ota' / 'config' / 'ota_config.yaml'
        
        if not config_file.exists():
            print(f"[ERROR] Configuration file not found: {config_file}")
            sys.exit(1)
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            print(f"[ERROR] Error loading configuration: {e}")
            sys.exit(1)
    
    def parse_version(self, version_str: str) -> Tuple[int, int, int, int]:
        """
        Parse version string to tuple for comparison.

        Accepts every shape we may see on S3:

          * Bare numeric:        ``1.0.0`` (legacy callers)
          * Sparkle-style:       ``v1.0.0``
          * Pre-release/builds:  ``v1.0.0-rc.1``, ``v1.0.0-gui-v2-abc``
          * User-tagged:         ``songc_v26.05.04.09.11`` (prefix stripped first)

        Args:
            version_str: Version string in any of the shapes above.

        Returns:
            Version tuple (major, minor, patch, priority)
            Priority: 1000 = standard, 900 = rc, 800 = beta, 0 = branch builds.
            Used as a tiebreaker for the chronological sort in
            ``generate_appcast``; not the primary sort key any more.
        """
        # Strip the user prefix (if any) and the leading 'v' so the
        # numeric regex below works for both `v1.0.0` and
        # `songc_v26.05.04.09.11`.
        _prefix, core = _split_release_dir(version_str)

        # Extract numeric parts
        match = re.match(r'(\d+)\.(\d+)\.(\d+)', core)
        if not match:
            return (0, 0, 0, 0)

        major, minor, patch = map(int, match.groups())

        # Determine priority based on suffix
        remainder = core[match.end():]
        
        if not remainder or re.match(r'^(\.\d+)+$', remainder):
            # Standard version (e.g., '1.0.0') OR a longer purely-numeric
            # tail used by date-coded user builds (e.g.,
            # '26.05.04.09.11' has remainder '.09.11' after the
            # major.minor.patch match — still a numeric version, not a
            # prerelease tag).
            priority = 1000
        elif remainder.startswith('-rc.'):
            # Release candidate (e.g., '1.0.0-rc.1')
            priority = 900
        elif remainder.startswith('-beta.'):
            # Beta version (e.g., '1.0.0-beta.1')
            priority = 800
        else:
            # Branch builds or other suffixes (e.g., '1.0.0-gui-v2-abc')
            priority = 0
        
        return (major, minor, patch, priority)
    
    def list_versions(self) -> List[str]:
        """
        List release-directory names to include in the appcast.

        Returns the **verbatim** S3 sub-directory names under
        ``releases/`` (e.g. ``v1.0.0``, ``songc_v26.05.04.09.11``) so
        downstream code can:

          * use them as-is when constructing ``releases/{dir}/...`` paths;
          * emit them verbatim into ``<sparkle:version>`` so the client's
            ``ota.core.appcast._split_user_prefix`` can recover the
            user prefix without any extra hint.

        The order is by parsed semver descending — kept as a stable
        starting point. The chronological-by-LastModified sort happens
        once we have ``pkg_info`` for each candidate (see
        ``generate_appcast``); doing it here would require an extra
        round-trip per version and isn't worth the latency.

        - If ``specific_version`` is set, returns only that one.
        - Otherwise, scans S3 and returns every version dir we find.
        """
        if self.specific_version:
            print(f"\n[INFO] Using specific release dir: {self.specific_version}")
            return [self.specific_version]

        print(f"\n[INFO] Scanning S3 for versions in {self.environment}...")

        if self.base_path:
            prefix = f"{self.base_path}/{self.prefix}/releases/"
        else:
            prefix = f"{self.prefix}/releases/"

        try:
            if self.storage_backend == 'cos':
                # COS: list with delimiter, need manual prefix filtering
                response = self.cos.list_objects(
                    Bucket=self.bucket,
                    Prefix=prefix,
                    Delimiter='/'
                )
                versions: List[str] = []
                for common_prefix in response.get('CommonPrefixes', []):
                    version_path = common_prefix['Prefix']
                    release_dir = version_path.rstrip('/').split('/')[-1]
                    if release_dir == 'latest' or release_dir.lower() == 'latest':
                        continue
                    if self.environment != 'simulation' and '-sim' in release_dir:
                        print(f"  [SKIP] Simulation build {release_dir} (not allowed in {self.environment})")
                        continue
                    versions.append(release_dir)
            else:
                response = self.s3.list_objects_v2(
                    Bucket=self.bucket,
                    Prefix=prefix,
                    Delimiter='/'
                )
                versions: List[str] = []
                for common_prefix in response.get('CommonPrefixes', []):
                    version_path = common_prefix['Prefix']
                    release_dir = version_path.rstrip('/').split('/')[-1]
                    if release_dir == 'latest' or release_dir.lower() == 'latest':
                        continue
                    if self.environment != 'simulation' and '-sim' in release_dir:
                        print(f"  [SKIP] Simulation build {release_dir} (not allowed in {self.environment})")
                        continue
                    versions.append(release_dir)

            # Initial sort by parsed semver descending. The final
            # chronological order is applied by `generate_appcast` once
            # LastModified is known per version.
            versions.sort(key=self.parse_version, reverse=True)

            print(f"  Found {len(versions)} versions")
            for v in versions[:5]:  # Show first 5
                print(f"    • {v}")
            if len(versions) > 5:
                print(f"    ... and {len(versions) - 5} more")

            return versions

        except Exception as e:
            print(f"  [ERROR] Failed to list versions: {e}")
            return []
    
    def get_package_info(self, version: str, platform: str, arch: str) -> Optional[Dict]:
        """
        Get package information from S3

        Args:
            version: Verbatim S3 release-directory name as returned by
                ``list_versions`` (e.g. ``v1.0.0`` or
                ``songc_v26.05.04.09.11``). Legacy callers passing a bare
                numeric like ``1.0.0`` are normalized via
                :func:`_to_release_dir` so existing call sites keep
                working without modification.
            platform: Platform (macos/windows/linux)
            arch: Architecture (amd64/aarch64)

        Returns:
            Package info dict or None if not found
        """
        # Normalize legacy bare-numeric inputs (e.g. '1.0.0') back into
        # the verbatim directory form ('v1.0.0'). This is the ONLY place
        # we apply the conversion — everywhere else `version` is already
        # the dir name.
        release_dir = _to_release_dir(version)

        # Build S3 prefix for this version/platform/arch (no 'v' prepending —
        # `release_dir` already carries it for semver and includes the user
        # prefix for tagged builds).
        if self.base_path:
            prefix = f"{self.base_path}/{self.prefix}/releases/{release_dir}/{platform}/{arch}/"
        else:
            prefix = f"{self.prefix}/releases/{release_dir}/{platform}/{arch}/"
        
        try:
            if self.storage_backend == 'cos':
                response = self.cos.list_objects(
                    Bucket=self.bucket,
                    Prefix=prefix
                )
                contents = response.get('Contents', [])
            else:
                response = self.s3.list_objects_v2(
                    Bucket=self.bucket,
                    Prefix=prefix
                )
                contents = response.get('Contents', [])

            for obj in contents:
                key = obj['Key']
                filename = key.split('/')[-1]
                
                # Skip checksum files
                if filename.endswith('.sha256') or filename.endswith('.sig'):
                    continue
                
                # Check if it's an installer
                if platform == 'macos' and filename.endswith('.pkg'):
                    pass
                elif platform == 'windows' and (filename.endswith('.exe') or filename.endswith('.msi')):
                    pass
                elif platform == 'linux' and (filename.endswith('.AppImage') or filename.endswith('.deb')):
                    pass
                else:
                    continue
                
                # Get SHA256 checksum
                sha256 = None
                sha256_key = f"{key}.sha256"
                try:
                    if self.storage_backend == 'cos':
                        sha256_obj = self.cos.get_object(Bucket=self.bucket, Key=sha256_key)
                        if sha256_obj:
                            sha256 = sha256_obj['Body'].read().decode('utf-8').strip()
                    else:
                        sha256_obj = self.s3.get_object(Bucket=self.bucket, Key=sha256_key)
                        sha256 = sha256_obj['Body'].read().decode('utf-8').strip()
                except:
                    pass

                # Get Ed25519 signature
                signature = None
                sig_key = f"{key}.sig"
                try:
                    import base64
                    if self.storage_backend == 'cos':
                        sig_obj = self.cos.get_object(Bucket=self.bucket, Key=sig_key)
                        if sig_obj:
                            sig_data = sig_obj['Body'].read()
                            signature = base64.b64encode(sig_data).decode('utf-8')
                    else:
                        sig_obj = self.s3.get_object(Bucket=self.bucket, Key=sig_key)
                        sig_data = sig_obj['Body'].read()
                        signature = base64.b64encode(sig_data).decode('utf-8')
                except Exception as e:
                    print(f"  [WARNING] Failed to read signature for {key}: {e}")
                    pass

                # Build download URLs
                if self.storage_backend == 'cos':
                    # COS uses S3-compatible API with Tencent Cloud endpoint
                    download_url = f"https://{self.bucket}.cos.{self.region}.myqcloud.com/{key}"
                    accelerated_url = None
                else:
                    # Standard S3 URL (regional endpoint)
                    download_url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"
                    # Accelerated URL (S3 Transfer Acceleration endpoint)
                    accelerated_url = f"https://{self.bucket}.s3-accelerate.amazonaws.com/{key}"
                
                # `version` here is the verbatim release-dir name (e.g.
                # 'v1.0.0' or 'songc_v26.05.04.09.11'). We split it once
                # so downstream callers can pick:
                #   * `version`       → emitted into <sparkle:version>
                #                       (the client splits it back).
                #   * `version_core`  → bare 'X.Y.Z[...]' for CHANGELOG
                #                       lookup and parse_version.
                #   * `user_prefix`   → None for universal builds, used by
                #                       generate_latest_json to skip
                #                       user-tagged versions.
                user_prefix, version_core = _split_release_dir(release_dir)

                # Normalize LastModified to a tz-aware datetime (see
                # `_normalize_last_modified` for the why).
                last_modified = _normalize_last_modified(obj['LastModified'])

                return {
                    'version': release_dir,
                    'version_core': version_core,
                    'user_prefix': user_prefix,
                    'platform': platform,
                    'arch': arch,
                    'filename': filename,
                    's3_key': key,
                    'download_url': download_url,
                    'accelerated_url': accelerated_url,
                    'file_size': obj['Size'],
                    'last_modified': last_modified,
                    'sha256': sha256,
                    'signature': signature
                }
            
            return None
            
        except Exception as e:
            print(f"  [WARN] Failed to get package info for {version}/{platform}/{arch}: {e}")
            return None
    
    def generate_appcast(self, platform: str, arch: str, max_versions: int = 10, language: str = 'en-US') -> Optional[str]:
        """
        Generate appcast XML for platform and architecture (with i18n support)
        
        Args:
            platform: Platform (macos/windows/linux)
            arch: Architecture (amd64/aarch64)
            max_versions: Maximum number of versions to include
            language: Language code (e.g., 'en-US', 'zh-CN')
            
        Returns:
            XML content string or None if failed
        """
        print(f"\n[INFO] Generating appcast for {platform}-{arch}...")
        
        # Get all versions
        versions = self.list_versions()
        
        # Build appcast items
        items = []
        for version in versions[:max_versions]:
            pkg_info = self.get_package_info(version, platform, arch)
            if pkg_info:
                # Filter fake signatures in non-simulation environments
                if pkg_info.get('signature') == 'fake_ed25519_signature_for_simulation':
                    if self.environment != 'simulation':
                        print(f"  [SKIP] {version} (fake signature not allowed in {self.environment} environment)")
                        continue
                    else:
                        print(f"  [OK] Added {version} (⚠️  simulation build with fake signature)")
                else:
                    print(f"  [OK] Added {version}")
                
                items.append(pkg_info)
        
        if not items:
            print(f"  [WARN] No packages found for {platform}-{arch}")
            return None

        # Sort items chronologically (newest first) using S3 LastModified
        # as the primary key, with parsed semver as a deterministic
        # tiebreaker when two builds share a timestamp (rare, but
        # possible after replays). This replaces the old
        # alphanumeric/semver-only ordering — the appcast XML now
        # actually reflects when each artifact was published.
        # See: ota/docs/multi_version_picker.md ("Step 4 — Pipeline").
        items.sort(
            key=lambda p: (p['last_modified'], self.parse_version(p['version'])),
            reverse=True,
        )
        print(
            f"  [INFO] Sorted {len(items)} item(s) chronologically "
            f"(newest: {items[0]['version']} @ {items[0]['last_modified']})"
        )

        # Create XML
        rss = ET.Element('rss', {
            'version': '2.0',
            'xmlns:sparkle': 'http://www.andymatuschak.org/xml-namespaces/sparkle',
            'xmlns:dc': 'http://purl.org/dc/elements/1.1/'
        })
        
        channel = ET.SubElement(rss, 'channel')
        
        # Channel metadata
        ET.SubElement(channel, 'title').text = f"{self.app_name} Updates - {self.environment.title()}"

        if self.base_path:
            appcast_url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{self.base_path}/{self.prefix}/channels/{self.channel}/appcast-{platform}-{arch}.xml"
        else:
            appcast_url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{self.prefix}/channels/{self.channel}/appcast-{platform}-{arch}.xml"
        ET.SubElement(channel, 'link').text = appcast_url

        ET.SubElement(channel, 'description').text = f"Updates for {self.app_name} ({platform} {arch}) - {self.channel} channel"
        ET.SubElement(channel, 'language').text = language
        
        # Add items
        for pkg in items:
            item = ET.SubElement(channel, 'item')
            
            ET.SubElement(item, 'title').text = f"Version {pkg['version']}"
            ET.SubElement(item, 'pubDate').text = pkg['last_modified'].strftime('%a, %d %b %Y %H:%M:%S +0000')
            
            # Description: Read from CHANGELOG.md (with i18n support).
            # Use the bare numeric core (no leading 'v', no user prefix)
            # so the CHANGELOG regex `## [X.Y.Z]` matches user-prefixed
            # builds the same way it matches plain semver builds.
            description = get_release_notes_from_changelog(
                pkg.get('version_core') or pkg['version'],
                language=language,
            )
            
            # Add environment-specific warnings (localized)
            if self.environment == 'development':
                description += "<div style='background-color: #fff3cd; border: 1px solid #ffc107; padding: 10px; margin-top: 10px;'>"
                if language == 'zh-CN':
                    description += "<p><strong>[WARN] 开发版本</strong></p>"
                    description += "<p>这是一个开发版本，仅供测试使用。可能包含错误和未完成的功能。</p>"
                else:
                    description += "<p><strong>[WARN] Development Build</strong></p>"
                    description += "<p>This is a development build for testing purposes only. It may contain bugs and incomplete features.</p>"
                description += "</div>"
            elif self.environment == 'test':
                description += "<div style='background-color: #d1ecf1; border: 1px solid #0c5460; padding: 10px; margin-top: 10px;'>"
                if language == 'zh-CN':
                    description += "<p><strong>[INFO] 测试版本</strong></p>"
                    description += "<p>这是一个测试版本，如遇到问题请及时反馈。</p>"
                else:
                    description += "<p><strong>[INFO] Beta Release</strong></p>"
                    description += "<p>This is a beta release. Please report any issues you encounter.</p>"
                description += "</div>"
            
            ET.SubElement(item, 'description').text = f"<![CDATA[{description}]]>"
            
            # Enclosure (download link)
            enclosure_attrs = {
                'url': pkg['download_url'],
                'length': str(pkg['file_size']),
                'type': 'application/octet-stream',
                'sparkle:version': pkg['version'],
                'sparkle:os': platform,
            }
            
            if arch:
                enclosure_attrs['sparkle:arch'] = arch
            
            # Add accelerated download URL as alternate
            # Client can use this if primary URL fails or is slow
            if pkg.get('accelerated_url'):
                enclosure_attrs['sparkle:alternateUrl'] = pkg['accelerated_url']
            
            # Sparkle 2.x uses edSignature for Ed25519 signatures
            if pkg.get('signature'):
                enclosure_attrs['sparkle:edSignature'] = pkg['signature']
            
            # Legacy support or additional verification
            if pkg['sha256']:
                 # Note: Some older clients might interpret dsaSignature as DSA, but we only use Ed25519 now.
                 # We keep sha256 separate from signature.
                 pass
            
            ET.SubElement(item, 'enclosure', enclosure_attrs)
        
        # Convert to string with pretty formatting
        ET.indent(rss, space='  ')
        xml_str = ET.tostring(rss, encoding='unicode', method='xml')
        
        # Add XML declaration
        xml_str = '<?xml version="1.0" encoding="utf-8"?>\n' + xml_str
        
        return xml_str
    
    def upload_appcast(self, platform: str, arch: str, xml_content: str, language: str = 'en-US') -> bool:
        """
        Upload appcast XML to S3 with smart caching (only upload if changed)
        
        This method implements intelligent caching by comparing the new XML content
        with the existing one on S3. It only uploads if the content has changed,
        reducing unnecessary S3 API calls and uploads.
        
        Args:
            platform: Platform (macos/windows/linux)
            arch: Architecture (amd64/aarch64)
            xml_content: Appcast XML content
            language: Language code (e.g., 'en-US', 'zh-CN')
            
        Returns:
            True if successful
        """
        # Generate filename with language suffix (except for default 'en-US')
        if language == 'en-US':
            filename = f"appcast-{platform}-{arch}.xml"
        else:
            filename = f"appcast-{platform}-{arch}.{language}.xml"
        
        if self.base_path:
            storage_key = f"{self.base_path}/{self.prefix}/channels/{self.channel}/{filename}"
        else:
            storage_key = f"{self.prefix}/channels/{self.channel}/{filename}"

        # Calculate hash of new content
        new_hash = hashlib.sha256(xml_content.encode('utf-8')).hexdigest()

        # Check if existing appcast has the same content
        try:
            if self.storage_backend == 'cos':
                response = self.cos.get_object(Bucket=self.bucket, Key=storage_key)
                if response:
                    existing_content = response['Body'].read().decode('utf-8')
                    existing_hash = hashlib.sha256(existing_content.encode('utf-8')).hexdigest()
                    if new_hash == existing_hash:
                        print(f"  [SKIP] {filename} - No changes detected")
                        return True
                    else:
                        print(f"  [INFO] {filename} - Content changed, uploading...")
            else:
                response = self.s3.get_object(Bucket=self.bucket, Key=storage_key)
                existing_content = response['Body'].read().decode('utf-8')
                existing_hash = hashlib.sha256(existing_content.encode('utf-8')).hexdigest()
                if new_hash == existing_hash:
                    print(f"  [SKIP] {filename} - No changes detected")
                    return True
                else:
                    print(f"  [INFO] {filename} - Content changed, uploading...")
        except Exception as e:
            print(f"  [INFO] {filename} - New file or check failed, uploading... ({e})")

        # Upload to storage
        try:
            if self.storage_backend == 'cos':
                self.cos.put_object(
                    Bucket=self.bucket,
                    Key=storage_key,
                    Body=xml_content.encode('utf-8'),
                    ContentType='application/rss+xml; charset=utf-8',
                )
                url = f"https://{self.bucket}.cos.{self.region}.myqcloud.com/{storage_key}"
            else:
                self.s3.put_object(
                    Bucket=self.bucket,
                    Key=storage_key,
                    Body=xml_content.encode('utf-8'),
                    ContentType='application/rss+xml; charset=utf-8',
                    CacheControl='max-age=300'
                )
                url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{storage_key}"
            print(f"  [OK] Uploaded: {url}")
            return True

        except Exception as e:
            print(f"  [ERROR] Failed to upload appcast: {e}")
            return False
    
    def generate_latest_json(self) -> bool:
        """Generate and upload latest.json with current version info
        
        This method uses incremental update strategy to avoid overwriting
        platform-specific information when builds are done separately.
        """
        print(f"\n[INFO] Generating latest.json...")
        
        versions = self.list_versions()
        if not versions:
            print("  [WARN] No versions found")
            return False

        # `latest.json` is a globally-visible pointer used by anything
        # that doesn't speak Sparkle/appcast (e.g. our public download
        # page). Per ota/docs/multi_version_picker.md it MUST point at
        # a universal build so a user-targeted preview never accidentally
        # becomes the default download for everyone. Filter prefixed
        # builds out of the candidate pool here. The full appcast XML
        # still includes them (clients filter by user_prefix locally).
        universal_versions = [
            v for v in versions if _split_release_dir(v)[0] is None
        ]
        if not universal_versions:
            print(
                "  [WARN] No universal versions found — skipping latest.json "
                "update to avoid pointing it at a user-tagged build."
            )
            return True  # Not a build failure; just nothing to update.

        if len(universal_versions) != len(versions):
            skipped = len(versions) - len(universal_versions)
            print(
                f"  [INFO] Excluded {skipped} user-tagged version(s) from "
                f"latest.json candidate pool (universal-only selection)."
            )

        latest_version = universal_versions[0]
        
        # Determine storage key
        if self.base_path:
            storage_key = f"{self.base_path}/{self.prefix}/latest.json"
        else:
            storage_key = f"{self.prefix}/latest.json"

        # Try to download existing latest.json for incremental update
        existing_data = None
        try:
            if self.storage_backend == 'cos':
                response = self.cos.get_object(Bucket=self.bucket, Key=storage_key)
                if response:
                    existing_data = json.loads(response['Body'].read().decode('utf-8'))
                    print(f"  [INFO] Found existing latest.json, will merge platform data")
            else:
                response = self.s3.get_object(Bucket=self.bucket, Key=storage_key)
                existing_data = json.loads(response['Body'].read().decode('utf-8'))
                print(f"  [INFO] Found existing latest.json, will merge platform data")
        except Exception as e:
            print(f"  [INFO] No existing latest.json found or read failed: {e}")
        
        # Initialize or update latest_data
        if existing_data:
            latest_data = existing_data
            # Update metadata
            latest_data['updated_at'] = datetime.now().isoformat()
            # Preserve existing platforms
            if 'platforms' not in latest_data:
                latest_data['platforms'] = {}
        else:
            # `latest_version` here is the verbatim release-dir name
            # (e.g. 'v1.0.0'). Strip the leading 'v' for the public
            # `version` field to match the legacy on-the-wire shape.
            _bare_version = _split_release_dir(latest_version)[1]
            latest_data = {
                'version': _bare_version,
                'channel': self.channel,
                'environment': self.environment,
                'updated_at': datetime.now().isoformat(),
                'platforms': {}
            }
        
        # Add or update platform-specific info (incremental)
        updated_platforms = []
        for platform in ['macos', 'windows', 'linux']:
            for arch in ['amd64', 'aarch64']:
                pkg_info = self.get_package_info(latest_version, platform, arch)
                if pkg_info:
                    platform_key = f"{platform}-{arch}"
                    # Preserve the legacy bare-numeric shape for the
                    # public `version` field (e.g. '1.0.0') so external
                    # consumers of latest.json don't see a leading 'v'
                    # appear out of nowhere with this rollout.
                    latest_data['platforms'][platform_key] = {
                        'version': pkg_info.get('version_core') or pkg_info['version'],
                        'url': pkg_info['download_url'],
                        'accelerated_url': pkg_info.get('accelerated_url'),
                        'file_size': pkg_info['file_size'],
                        'sha256': pkg_info['sha256'],
                        'signature': pkg_info['signature']
                    }
                    updated_platforms.append(platform_key)
        
        # Global `version` is the highest across all platforms
        # currently in `latest.json`. Sort with our internal
        # `parse_version` (the same rule `list_versions` uses to pick
        # `latest_version` upstream) so the comparison rule is
        # consistent. `packaging.version.parse` mishandles branch-build
        # suffixes such as `0.7.0-v0.9.97d-53bdc77` and can rank a
        # branch build above a numerically larger stable.
        all_platform_versions = [
            info.get('version', '0.0.0')
            for info in latest_data['platforms'].values()
        ]
        if all_platform_versions:
            try:
                latest_data['version'] = max(
                    all_platform_versions,
                    key=lambda v: self.parse_version(v),
                )
            except Exception:
                # Last-resort string compare if parse_version fails.
                latest_data['version'] = max(all_platform_versions)
        else:
            # No platforms present at all - fall back to the release
            # dir we intended to publish (e.g. immediately after the
            # first platform upload, before any sibling platform has
            # landed). This keeps the top-level field non-empty
            # rather than silently dropping it.
            _bare_version = _split_release_dir(latest_version)[1]
            latest_data['version'] = _bare_version
        
        # Upload to storage
        try:
            if self.storage_backend == 'cos':
                self.cos.put_object(
                    Bucket=self.bucket,
                    Key=storage_key,
                    Body=json.dumps(latest_data, indent=2, ensure_ascii=False).encode('utf-8'),
                    ContentType='application/json; charset=utf-8',
                )
                url = f"https://{self.bucket}.cos.{self.region}.myqcloud.com/{storage_key}"
            else:
                self.s3.put_object(
                    Bucket=self.bucket,
                    Key=storage_key,
                    Body=json.dumps(latest_data, indent=2, ensure_ascii=False).encode('utf-8'),
                    ContentType='application/json; charset=utf-8',
                    CacheControl='max-age=300'
                )
                url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{storage_key}"
            print(f"  [OK] Uploaded: {url}")
            if updated_platforms:
                print(f"  [INFO] Updated platforms: {', '.join(updated_platforms)}")
            print(f"  [INFO] Total platforms in latest.json: {len(latest_data['platforms'])}")
            return True

        except Exception as e:
            print(f"  [ERROR] Failed to upload latest.json: {e}")
            return False
    
    def run(self, platform_filter: str = 'all', arch_filter: str = 'all') -> bool:
        """Run the appcast generation process
        
        Args:
            platform_filter: Platform filter ('all', 'macos', 'windows', 'linux')
            arch_filter: Architecture filter ('all', 'amd64', 'aarch64')
        """
        print("=" * 60)
        backend = "COS" if self.storage_backend == 'cos' else "S3"
        print(f"[INFO] Appcast Generator - {backend} ({self.app_id})")
        print("=" * 60)
        print(f"Environment: {self.environment}")
        print(f"Channel:     {self.channel}")
        print(f"App:         {self.app_id} ({self.app_name})")
        print(f"Storage:     {backend} - {self.bucket}")
        print(f"S3 Bucket:   {self.bucket}")
        print(f"S3 Region:   {self.region}")
        print(f"S3 Prefix:   {self.prefix}")
        if platform_filter != 'all' or arch_filter != 'all':
            print(f"Filter:      platform={platform_filter}, arch={arch_filter}")
        print("=" * 60)
        
        success_count = 0
        total_count = 0
        
        # Define platforms to process
        platforms = ['macos', 'windows', 'linux'] if platform_filter == 'all' else [platform_filter]
        architectures = ['amd64', 'aarch64'] if arch_filter == 'all' else [arch_filter]
        
        # Apply filters
        combinations = []
        for platform in platforms:
            for arch in architectures:
                combinations.append((platform, arch))
        
        if not combinations:
            print("[WARN] No platform/arch combinations match the filters")
            return False
        
        # Supported languages
        languages = ['en-US', 'zh-CN']
        
        for platform, arch in combinations:
            for language in languages:
                total_count += 1
                xml_content = self.generate_appcast(platform, arch, language=language)
                
                if xml_content:
                    if self.upload_appcast(platform, arch, xml_content, language=language):
                        success_count += 1
        
        # Note: latest.json generation moved to separate job
        # to avoid race conditions when multiple appcast jobs run in parallel
        # See: generate-latest-json job in release.yml
        
        # Summary
        print("\n" + "=" * 60)
        if success_count == total_count:
            print("[OK] All appcasts generated successfully!")
        else:
            print(f"[WARN] Generated {success_count}/{total_count} appcasts")
        print("=" * 60)
        
        return success_count > 0


def main():
    parser = argparse.ArgumentParser(
        description='Generate Appcast XML files from S3 artifacts',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate appcasts for production
  python3 ota/scripts/generate_appcast.py --env production
  
  # Generate appcasts for test environment with beta channel
  python3 ota/scripts/generate_appcast.py --env test --channel beta
  
  # Generate appcasts for development
  python3 ota/scripts/generate_appcast.py --env dev
        """
    )
    
    parser.add_argument('--env', required=True, choices=['dev', 'development', 'test', 'staging', 'production', 'simulation'],
                       help='Target environment')
    parser.add_argument('--channel', choices=['dev', 'beta', 'stable', 'lts', 'simulation'],
                       help='Release channel (overrides environment default)')
    parser.add_argument('--version', 
                       help='Specific version to generate appcast for (e.g., 1.0.1). If not provided, scans all versions.')
    parser.add_argument('--user-prefix', default='', dest='user_prefix',
                       help=(
                           'Optional per-user release prefix (lowercase). When given '
                           'alongside --version, the on-S3 directory looked up is '
                           '{prefix}_v{version}. The auto-scan path picks up every '
                           'directory layout regardless. See ota/docs/multi_version_picker.md.'
                       ))
    parser.add_argument('--platform', choices=['all', 'macos', 'windows', 'linux'],
                       default='all', help='Target platform (default: all)')
    parser.add_argument('--arch', choices=['all', 'amd64', 'aarch64'],
                       default='all', help='Target architecture (default: all)')
    parser.add_argument('--app', choices=['intl', 'cn'],
                       default='intl', dest='app_id',
                       help='App identifier: intl (eCan) or cn (eCan.cn)')

    args = parser.parse_args()

    # Create generator and run
    generator = AppcastGenerator(
        args.env,
        args.channel,
        specific_version=args.version,
        user_prefix=args.user_prefix,
        app_id=args.app_id,
    )
    success = generator.run(platform_filter=args.platform, arch_filter=args.arch)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
