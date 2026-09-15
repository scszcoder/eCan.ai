from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from build_system.linux_builder import LinuxBuilder


def test_lightrag_submodules_are_enumerated_without_importing_children(tmp_path: Path) -> None:
    package_dir = tmp_path / "lightrag"
    (package_dir / "api").mkdir(parents=True)
    (package_dir / "__init__.py").write_text("")
    (package_dir / "api" / "__init__.py").write_text("raise SystemExit(2)")
    (package_dir / "api" / "server.py").write_text("")

    spec = type("Spec", (), {"submodule_search_locations": [str(package_dir)]})()
    with patch("build_system.linux_builder.importlib.util.find_spec", return_value=spec):
        modules = LinuxBuilder._find_submodules_without_importing("lightrag")

    assert modules == ["lightrag", "lightrag.api", "lightrag.api.server"]


def test_pyinstaller_avoids_collect_all_for_lightrag(tmp_path: Path) -> None:
    builder = LinuxBuilder(
        tmp_path,
        {"build": {"pyinstaller": {"collect_all": ["lightrag", "neo4j"]}}},
    )

    with (
        patch.object(
            builder,
            "_find_submodules_without_importing",
            return_value=["lightrag", "lightrag.api.config"],
        ),
        patch(
            "build_system.linux_builder.subprocess.run",
            return_value=CompletedProcess([], 0, stdout="", stderr=""),
        ) as run,
    ):
        assert builder.build_pyinstaller() is True

    command = run.call_args.args[0]
    pairs = list(zip(command, command[1:]))
    assert ("--collect-all", "lightrag") not in pairs
    assert ("--collect-data", "lightrag") in pairs
    assert ("--hidden-import", "lightrag.api.config") in pairs
    assert ("--collect-all", "neo4j") in pairs


def test_pyinstaller_failure_keeps_start_of_traceback(tmp_path: Path, capsys) -> None:
    builder = LinuxBuilder(tmp_path, {"app": {"name": "eCan"}})
    stderr = "ROOT CAUSE: bad command-line import\n" + ("detail\n" * 100) + "SystemExit: 2\n"

    with patch(
        "build_system.linux_builder.subprocess.run",
        return_value=CompletedProcess([], 1, stdout="analysis output\n", stderr=stderr),
    ):
        assert builder.build_pyinstaller() is False

    output = capsys.readouterr().out
    assert "analysis output" in output
    assert "ROOT CAUSE: bad command-line import" in output
    assert "SystemExit: 2" in output


def test_sanitize_deb_version_replaces_underscores() -> None:
    """Underscores must be replaced because dpkg-deb rejects them in Version field.

    Note: We only sanitize the value written to DEBIAN/control's Version
    field, NOT the .deb filename. The filename keeps the raw version
    (with underscores) so it matches the workflow contract:
        dist/$DIST_APP-$VERSION-linux-amd64.deb
    dpkg-deb permits the filename to differ from control's Version field.
    """
    assert LinuxBuilder._sanitize_deb_version("0.7.0-lq_dev_multi-final-32a8223") == "0.7.0-lq-dev-multi-final-32a8223"
    assert LinuxBuilder._sanitize_deb_version("1.0.0") == "1.0.0"  # no change
    assert LinuxBuilder._sanitize_deb_version("v1.2.3-beta_test-1") == "v1.2.3-beta-test-1"


def test_flatpak_manifest_paths_match_pyinstaller_layout(tmp_path: Path) -> None:
    """Contract test: Flatpak manifest's install commands must reference
    paths that exist in the PyInstaller output.

    PyInstaller places all data files under ``dist/{app_name}/_internal/``,
    while the executable lives directly at ``dist/{app_name}/{app_name}``.
    If the manifest drifts (e.g. drops the ``_internal/`` prefix), the
    Flatpak build will silently fail to find icons or icons and produce
    a bundle that doesn't show up in the desktop menu.

    Without this test, the regression only surfaces on a CI build, and
    Flatpak builds are too slow (60+ min for first SDK download) to
    iterate quickly. Catch the bug at unit-test speed.
    """
    config = {
        "app": {"name": "eCan.cn", "version": "1.0.0"},
        "platforms": {
            "linux": {
                "flatpak": {
                    "runtime": "org.freedesktop.Platform",
                    "runtime_version": "23.08",
                    "sdk": "org.freedesktop.Sdk",
                }
            }
        },
    }
    builder = LinuxBuilder(tmp_path, config)

    # Set up a fake PyInstaller output matching the real layout:
    #   dist/{app_name}/{app_name}             ← executable
    #   dist/{app_name}/_internal/resource/images/logos/desktop_*.png
    dist = tmp_path / "dist"
    app_dir = dist / "eCan.cn"
    app_dir.mkdir(parents=True)
    (app_dir / "eCan.cn").write_text("fake-binary")  # executable
    internal = app_dir / "_internal"
    logos = internal / "resource" / "images" / "logos"
    logos.mkdir(parents=True)
    (logos / "desktop_256x256.png").write_bytes(b"png-256")
    (logos / "desktop_64x64.png").write_bytes(b"png-64")

    manifest_path = tmp_path / "manifest.yml"
    assert builder._write_flatpak_manifest(manifest_path) is True

    text = manifest_path.read_text()

    # 1. Executable install command must use the bundle's top-level executable,
    #    not a path under _internal/.
    assert "install -Dm755 eCan.cn/eCan.cn /app/bin/eCan.cn" in text, (
        "Executable install command must reference PyInstaller's bundle root, "
        "not the _internal/ subdirectory. Got:\n" + text
    )

    # 2. Icon install commands must reference the _internal/ prefix — this is
    #    where PyInstaller puts resources after data_files collection.
    assert (
        "_internal/resource/images/logos/desktop_256x256.png" in text
    ), "256x256 icon install command missing _internal/ prefix"
    assert (
        "_internal/resource/images/logos/desktop_64x64.png" in text
    ), "64x64 icon install command missing _internal/ prefix"

    # 3. The bare "resource/images/logos/..." (without _internal/) must NOT
    #    appear as an install source. Note: _internal/-prefixed paths contain
    #    "resource/images/logos/" as a substring — check for the prefix.
    bare_resource_ref = sum(
        1 for line in text.splitlines()
        if "resource/images/logos/" in line
        and "_internal/resource/images/logos/" not in line
    )
    assert bare_resource_ref == 0, (
        f"Found {bare_resource_ref} install commands referencing "
        "resource/images/logos/ without _internal/ prefix; "
        "these would fail at install time"
    )

    # 4. Source dir path must be relative to the manifest location. Manifest
    #    is at dist/flatpak_build/manifest/*.yml, source is at dist/{app_name}/,
    #    so the relative path is ../../{app_name}.
    assert "path: ../../eCan.cn" in text, (
        "Source dir path must be relative to the manifest file location "
        "(../../eCan.cn from dist/flatpak_build/manifest/). Got:\n" + text
    )

    # 5. desktop.desktop must be a separate file source, not embedded in the
    #    dir source (PyInstaller doesn't generate one).
    assert "type: file" in text
    assert "path: desktop.desktop" in text


def test_flatpak_id_derives_cn_variant(tmp_path: Path) -> None:
    """CN variant must produce a different Flatpak app-id than INTL.

    Flathub and Flatpak's AppStream metadata both require distinct app-ids
    for distinct distributions of the same upstream project. eCan.ai ships
    CN (built from apps/cn/build_config_cn.json) and INTL separately;
    their bundles must not collide on Flathub.
    """
    intl_builder = LinuxBuilder(tmp_path, {"app": {"name": "eCan"}})
    cn_builder = LinuxBuilder(tmp_path, {"app": {"name": "eCan.cn"}})

    assert intl_builder._get_flatpak_id() == "ai.ecan.Ecan"
    assert cn_builder._get_flatpak_id() == "ai.ecan.EcanCN"
    assert intl_builder._get_flatpak_id() != cn_builder._get_flatpak_id()
