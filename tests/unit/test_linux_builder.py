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
    """Underscores must be replaced because dpkg-deb rejects them in Version field."""
    assert LinuxBuilder._sanitize_deb_version("0.7.0-lq_dev_multi-final-32a8223") == "0.7.0-lq-dev-multi-final-32a8223"
    assert LinuxBuilder._sanitize_deb_version("1.0.0") == "1.0.0"  # no change
    assert LinuxBuilder._sanitize_deb_version("v1.2.3-beta_test-1") == "v1.2.3-beta-test-1"
