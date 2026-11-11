"""The stealth script must parse once a fingerprint is filled in: a syntax error
means the browser drops the whole script and no fingerprint is applied."""
import shutil
import subprocess
from pathlib import Path

import pytest

from agent.ec_skills.browser_use_extension.fingerprint.fingerprint_service import (
    load_profile,
    prepare_stealth_js,
)

PRESETS = sorted(p.stem for p in (Path(__file__).resolve().parents[2] / "agent" / "ec_skills" / "browser_use_extension"
                                  / "fingerprint" / "profiles").glob("*.json"))


@pytest.mark.parametrize("preset", PRESETS)
def test_list_values_are_never_pasted_inside_a_js_string(preset):
    js = prepare_stealth_js(load_profile(preset))
    assert "__" + "LANGUAGES__" not in js
    assert 'JSON.parse("[' not in js


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
@pytest.mark.parametrize("preset", PRESETS)
def test_filled_in_script_parses(preset, tmp_path):
    script = tmp_path / f"{preset}.js"
    script.write_text(prepare_stealth_js(load_profile(preset)), encoding="utf-8")
    result = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
