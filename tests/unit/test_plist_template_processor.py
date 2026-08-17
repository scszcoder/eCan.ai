"""
Unit tests for build_system/plist_template_processor.py.

Focuses on the pure-function ``_apply_dynamic_config`` (template + config
-> rendered plist dict) and the surrounding ``process_template`` IO
shell. macOS package identity lives or dies on these values — a typo
in CFBundleIdentifier breaks code signing, a wrong LSMinimumSystemVersion
breaks install on older macOS, and a missing NSMicrophoneUsageDescription
triggers App Store rejection (or worse, runtime crash on first mic
access).

The template rendering is hand-rolled rather than via Jinja/etc., so a
regression in the dict-update order silently drops a key. Pin the
contract.
"""
from __future__ import annotations

import plistlib
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from build_system import plist_template_processor as pp  # noqa: E402


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def empty_template():
    """A minimal plist-shaped dict that mimics what plistlib.load would
    return from a real Info.plist template."""
    return {
        "CFBundleName": "PLACEHOLDER",
        "CFBundleIdentifier": "PLACEHOLDER",
        # macOS also requires this on modern SDKs even if empty.
        "LSMinimumSystemVersion": "",
        "NSMicrophoneUsageDescription": "old",
    }


@pytest.fixture
def default_config():
    return {
        "app": {"author": "eCan.AI Team"},
        "installer": {
            "macos": {
                "bundle_identifier": "com.ecan.app",
                "copyright": "Copyright © 2025 eCan.AI Team",
                "min_os_version": "11.0",
            }
        },
    }


@pytest.fixture
def processor(tmp_path):
    """Processor pointed at a tmp project root. No template is created,
    so ``process_template`` will fall back to the fallback plist path.
    The unit tests use ``_apply_dynamic_config`` directly."""
    return pp.InfoPlistTemplateProcessor(
        project_root=tmp_path,
        config={},
    )


# ============================================================================
# _apply_dynamic_config
# ============================================================================


class TestApplyDynamicConfig:
    def test_basic_app_fields_are_set(self, empty_template, default_config):
        p = pp.InfoPlistTemplateProcessor(project_root=Path("/tmp"), config=default_config)
        out = p._apply_dynamic_config(
            template_data=dict(empty_template),
            app_name="eCan",
            app_version="1.0.0",
            mode="prod",
        )
        assert out["CFBundleName"] == "eCan"
        assert out["CFBundleDisplayName"] == "eCan"
        assert out["CFBundleVersion"] == "1.0.0"
        assert out["CFBundleShortVersionString"] == "1.0.0"
        assert out["CFBundleExecutable"] == "eCan"

    def test_bundle_identifier_is_taken_from_config(self, empty_template):
        cfg = {"installer": {"macos": {"bundle_identifier": "com.custom.id"}}}
        p = pp.InfoPlistTemplateProcessor(project_root=Path("/tmp"), config=cfg)
        out = p._apply_dynamic_config(
            template_data=dict(empty_template),
            app_name="x", app_version="1", mode="prod",
        )
        assert out["CFBundleIdentifier"] == "com.custom.id"

    def test_default_bundle_identifier_falls_back(self, empty_template):
        # No installer config -> fallback default.
        p = pp.InfoPlistTemplateProcessor(project_root=Path("/tmp"), config={})
        out = p._apply_dynamic_config(
            template_data=dict(empty_template),
            app_name="x", app_version="1", mode="prod",
        )
        assert out["CFBundleIdentifier"] == "com.ecan.app"

    def test_min_os_version_is_overridden(self, empty_template):
        cfg = {"installer": {"macos": {"min_os_version": "13.0"}}}
        p = pp.InfoPlistTemplateProcessor(project_root=Path("/tmp"), config=cfg)
        out = p._apply_dynamic_config(
            template_data=dict(empty_template),
            app_name="x", app_version="1", mode="prod",
        )
        assert out["LSMinimumSystemVersion"] == "13.0"

    def test_copyright_uses_config_value(self, empty_template):
        cfg = {"installer": {"macos": {"copyright": "© 2026 Acme"}}}
        p = pp.InfoPlistTemplateProcessor(project_root=Path("/tmp"), config=cfg)
        out = p._apply_dynamic_config(
            template_data=dict(empty_template),
            app_name="x", app_version="1", mode="prod",
        )
        assert out["NSHumanReadableCopyright"] == "© 2026 Acme"

    def test_microphone_description_is_set(self, empty_template):
        # macOS Big Sur+ REJECTS apps without this if mic access is
        # requested. The original `old` placeholder must be replaced.
        p = pp.InfoPlistTemplateProcessor(project_root=Path("/tmp"), config={})
        out = p._apply_dynamic_config(
            template_data=dict(empty_template),
            app_name="eCan", app_version="1", mode="prod",
        )
        assert "eCan" in out["NSMicrophoneUsageDescription"]
        assert "microphone" in out["NSMicrophoneUsageDescription"].lower()
        assert out["NSMicrophoneUsageDescription"] != "old"

    @pytest.mark.parametrize(
        "key",
        [
            "NSMicrophoneUsageDescription",
            "NSCameraUsageDescription",
            "NSNetworkVolumesUsageDescription",
            "NSAppleEventsUsageDescription",
            "NSSystemAdministrationUsageDescription",
            "NSApplicationSupportDirectoryUsageDescription",
            "NSDocumentsFolderUsageDescription",
            "NSDesktopFolderUsageDescription",
            "NSDownloadsFolderUsageDescription",
            "NSScreenCaptureUsageDescription",
            "NSAccessibilityUsageDescription",
        ],
    )
    def test_required_macos_usage_descriptions_are_set(
        self, empty_template, key
    ):
        p = pp.InfoPlistTemplateProcessor(project_root=Path("/tmp"), config={})
        out = p._apply_dynamic_config(
            template_data=dict(empty_template),
            app_name="eCan", app_version="1", mode="prod",
        )
        assert key in out, f"{key} missing from rendered plist"
        assert "eCan" in out[key], f"{key} does not mention app name"

    def test_dev_mode_appends_dev_suffix_to_display_name(self, empty_template):
        p = pp.InfoPlistTemplateProcessor(project_root=Path("/tmp"), config={})
        out = p._apply_dynamic_config(
            template_data=dict(empty_template),
            app_name="eCan", app_version="1", mode="dev",
        )
        assert out["CFBundleDisplayName"] == "eCan (Dev)"
        # CFBundleName stays the same — only the user-facing display
        # name changes.
        assert out["CFBundleName"] == "eCan"

    def test_url_schemes_from_config_replace_defaults(self, empty_template):
        cfg = {
            "installer": {
                "macos": {
                    "url_schemes": [
                        {
                            "name": "Custom URL",
                            "scheme": "myapp",
                            "role": "Editor",
                            "icon": "myapp.icns",
                        }
                    ]
                }
            }
        }
        p = pp.InfoPlistTemplateProcessor(project_root=Path("/tmp"), config=cfg)
        out = p._apply_dynamic_config(
            template_data=dict(empty_template),
            app_name="x", app_version="1", mode="prod",
        )
        url_types = out["CFBundleURLTypes"]
        assert len(url_types) == 1
        assert url_types[0]["CFBundleURLSchemes"] == ["myapp"]
        assert url_types[0]["CFBundleURLName"] == "Custom URL"
        assert url_types[0]["CFBundleTypeRole"] == "Editor"
        assert url_types[0]["CFBundleURLIconFile"] == "myapp.icns"

    def test_url_schemes_default_added_when_template_and_config_lack_them(
        self, empty_template
    ):
        p = pp.InfoPlistTemplateProcessor(project_root=Path("/tmp"), config={})
        out = p._apply_dynamic_config(
            template_data=dict(empty_template),
            app_name="x", app_version="1", mode="prod",
        )
        url_types = out["CFBundleURLTypes"]
        # Falls back to the ecan:// scheme so the app can still receive
        # deep links out of the box.
        assert url_types[0]["CFBundleURLSchemes"] == ["ecan"]

    def test_existing_url_schemes_in_template_are_preserved(self, empty_template):
        empty_template["CFBundleURLTypes"] = [
            {"CFBundleURLSchemes": ["pre-existing"]}
        ]
        # Empty config: must NOT clobber the template's existing entry.
        p = pp.InfoPlistTemplateProcessor(project_root=Path("/tmp"), config={})
        out = p._apply_dynamic_config(
            template_data=dict(empty_template),
            app_name="x", app_version="1", mode="prod",
        )
        assert out["CFBundleURLTypes"] == [
            {"CFBundleURLSchemes": ["pre-existing"]}
        ]


# ============================================================================
# process_template: IO shell
# ============================================================================


class TestProcessTemplate:
    def test_missing_template_uses_fallback(self, tmp_path):
        # No resource/Info.plist exists. Must fall back to the
        # internally-generated plist (so the macOS package still
        # builds without crashing).
        p = pp.InfoPlistTemplateProcessor(project_root=tmp_path, config={})
        out_path = p.process_template("eCan", "1.0.0", mode="prod")
        assert Path(out_path).exists()
        # Round-trip the plist to make sure it's well-formed XML.
        with open(out_path, "rb") as f:
            data = plistlib.load(f)
        assert data["CFBundleName"] == "eCan"
        assert data["CFBundleVersion"] == "1.0.0"

    def test_renders_valid_plist_xml(self, tmp_path):
        # Drop a minimal valid template into resource/Info.plist and
        # assert process_template produces plistlib-loadable output.
        resource = tmp_path / "resource"
        resource.mkdir()
        template = {
            "CFBundleName": "TEMPLATE",
            "CFBundleIdentifier": "com.example",
            "CFBundleVersion": "0.0.0",
        }
        with open(resource / "Info.plist", "wb") as f:
            plistlib.dump(template, f)

        p = pp.InfoPlistTemplateProcessor(project_root=tmp_path, config={})
        out_path = p.process_template("eCan", "1.0.0", mode="prod")

        with open(out_path, "rb") as f:
            data = plistlib.load(f)
        # Template values were overridden by dynamic config.
        assert data["CFBundleName"] == "eCan"
        assert data["CFBundleVersion"] == "1.0.0"

    def test_fallback_writes_to_build_temp(self, tmp_path):
        # No resource/Info.plist -> falls back to Info_fallback.plist
        # under <project>/build/temp/.
        p = pp.InfoPlistTemplateProcessor(project_root=tmp_path, config={})
        out_path = p.process_template("eCan", "1.0.0", mode="dev")
        assert Path(out_path).exists()
        assert Path(out_path).name == "Info_fallback.plist"
        assert Path(out_path).parent == tmp_path / "build" / "temp"

    def test_real_template_writes_to_build_temp_with_mode_suffix(self, tmp_path):
        # With a real template in place, the output file is named
        # Info_<mode>.plist.
        resource = tmp_path / "resource"
        resource.mkdir()
        with open(resource / "Info.plist", "wb") as f:
            plistlib.dump({"CFBundleName": "TEMPLATE"}, f)

        p = pp.InfoPlistTemplateProcessor(project_root=tmp_path, config={})
        out_path = p.process_template("eCan", "1.0.0", mode="dev")
        assert Path(out_path).name == "Info_dev.plist"