# -*- coding: utf-8 -*-
"""Regression: importing a cli submodule must not flip the process into web mode.

The desktop GUI imports cli submodules for helpers (e.g. fast_deploy_handler does
`from cli.deploy.commands import cs_pools`). That import pulls in the `cli` package
via cli/__init__.py -> `from .main import cli`. cli/main.py used to run
`os.environ.setdefault('ECAN_MODE', 'web')` at import time, which — because
ECAN_MODE is unset in the desktop process — silently set it to 'web'. Every
handler that resolves context by deployment mode then failed with
"No session_id available. In web mode, ...". See the 2026-10-15 customer report.

ECAN_MODE is now set only when the CLI actually executes (the cli() group
callback and main()), never as an import side effect.
"""
import os
import subprocess
import sys


def _run(code: str) -> str:
    """Run `code` in a child process with ECAN_MODE unset; return the marker line.

    Inherits the full environment (so the app imports cleanly) but drops
    ECAN_MODE to emulate the desktop process, where it is unset.
    """
    env = dict(os.environ)
    env.pop("ECAN_MODE", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", code],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, f"child failed: {proc.returncode}\n{proc.stderr}"
    # The last non-empty stdout line is our marker (eCan prints banners on import).
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT=")]
    assert lines, f"no RESULT marker in output:\n{proc.stdout}\n{proc.stderr}"
    return lines[-1]


def test_importing_cli_deploy_commands_does_not_set_web_mode():
    """The exact import fast_deploy_handler performs must leave mode = desktop."""
    out = _run(
        "import os\n"
        "os.environ.pop('ECAN_MODE', None)\n"
        "import cli.deploy.commands\n"
        "from gui.ipc.context_bridge import get_deployment_mode\n"
        "print('RESULT=' + repr(os.environ.get('ECAN_MODE')) + '|' + get_deployment_mode())\n"
    )
    assert out == "RESULT=None|desktop", out


def test_importing_cli_main_does_not_set_web_mode():
    out = _run(
        "import os\n"
        "os.environ.pop('ECAN_MODE', None)\n"
        "import cli.main  # noqa: F401\n"
        "print('RESULT=' + repr(os.environ.get('ECAN_MODE')))\n"
    )
    assert out == "RESULT=None", out


def test_cli_invocation_still_defaults_to_web():
    """Running the CLI (group callback) must still default ECAN_MODE to web."""
    out = _run(
        "import os\n"
        "os.environ.pop('ECAN_MODE', None)\n"
        "from cli.main import cli\n"
        "from click.testing import CliRunner\n"
        "r = CliRunner().invoke(cli, ['version'])\n"
        "print('RESULT=' + repr(os.environ.get('ECAN_MODE')) + '|exit=' + str(r.exit_code))\n"
    )
    assert out == "RESULT='web'|exit=0", out
