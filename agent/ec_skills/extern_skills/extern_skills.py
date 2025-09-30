# %APPDATA%/MyApp/my_skills/
#   abc_skill/
#     requirements.txt        # plugin-only deps (e.g., pandas)
#     abc_skill/              # package folder
#       __init__.py
#       abc_skill.py          # entry module (run(ctx) + __main__)
# On macOS: ~/Library/Application Support/MyApp/my_skills/…
# On Linux: ~/.local/share/MyApp/my_skills/…

# host_plugins.py
from __future__ import annotations
import os, sys, json, subprocess, textwrap, uuid, shutil
from pathlib import Path
import venv
from typing import Any, Callable

APP_NAME = "eCan.ai"              # change to your real app name
SKILLS_DIRNAME = "my_skills"    # as requested


# ===============================================================================
def user_skills_root() -> Path:
    """Return the per-user skills root dir."""
    if sys.platform == "win32":
        base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / APP_NAME / SKILLS_DIRNAME
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / SKILLS_DIRNAME
    else:
        return Path.home() / ".local" / "share" / APP_NAME / SKILLS_DIRNAME


def scaffold_skill(skill_name: str = "abc", description: str = "This skill ....", kind: str = "code") -> Path:
    """Create `<root>/<name>_skill/` with either `code_skill/` or `diagram_dir/`.

    kind:
      - "code": create code_skill/<name>/abc_skill.py (+requirements.txt)
      - "diagram": create diagram_dir/<name>_skill.json (+ optional bundle placeholder)
    """
    root = user_skills_root()
    root.mkdir(parents=True, exist_ok=True)
    skill_root = root / f"{skill_name}_skill"
    skill_root.mkdir(parents=True, exist_ok=True)

    if kind == "code":
        code_dir = skill_root / "code_skill"
        pkg = code_dir / skill_name
        pkg.mkdir(parents=True, exist_ok=True)
        (skill_root / "requirements.txt").write_text("pandas>=2.2\n", encoding="utf-8")
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "abc_skill.py").write_text(textwrap.dedent(f"""\
            # {skill_name} code skill scaffold
            from langgraph.graph import StateGraph

            def build_stategraph():
                g = StateGraph(dict)
                def start(state: dict):
                    state['hello'] = 'world'
                    return state
                g.add_node('start', start)
                g.set_entry_point('start')
                return g

            def build_skill():
                # return (dto, stategraph) tuple or EC_Skill; loader supports both
                class DTO:
                    def __init__(self):
                        self.name = '{skill_name}'
                        self.description = '{description}'
                        self.config = {{}}
                return DTO(), build_stategraph()
        """), encoding="utf-8")
    elif kind == "diagram":
        diagram_dir = skill_root / "diagram_dir"
        diagram_dir.mkdir(parents=True, exist_ok=True)
        core = {
            "skillName": skill_name,
            "description": description,
            "owner": "",
            "workFlow": {"nodes": [], "edges": []}
        }
        (diagram_dir / f"{skill_name}_skill.json").write_text(json.dumps(core, indent=2, ensure_ascii=False), encoding="utf-8")
        (diagram_dir / f"{skill_name}_skill_bundle.json").write_text(json.dumps({"resources": []}, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        raise ValueError("kind must be 'code' or 'diagram'")

    return skill_root


def rename_skill(old_name: str, new_name: str) -> Path:
    """Rename `<root>/<old>_skill` -> `<root>/<new>_skill`. Returns new path."""
    root = user_skills_root()
    old_dir = root / f"{old_name}_skill"
    new_dir = root / f"{new_name}_skill"
    if not old_dir.exists():
        raise FileNotFoundError(f"Skill root not found: {old_dir}")
    if new_dir.exists():
        raise FileExistsError(f"Target already exists: {new_dir}")
    old_dir.rename(new_dir)
    return new_dir


def _venv_paths(venv_dir: Path):
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe", venv_dir / "Scripts" / "pip.exe"
    return venv_dir / "bin" / "python", venv_dir / "bin" / "pip"

def ensure_skill_venv(skill_dir: Path, *, reuse_host_libs: bool = True):
    venv_dir = skill_dir / ".venv"
    if not venv_dir.exists():
        venv.EnvBuilder(with_pip=True, system_site_packages=reuse_host_libs).create(str(venv_dir))
    py, pip = _venv_paths(venv_dir)
    req = skill_dir / "requirements.txt"
    if req.exists():
        subprocess.check_call([str(pip), "install", "-r", str(req)])


# usage sample:
# Prepare user skills dir + scaffold example skill
# root = user_plugins_root()
# root.mkdir(parents=True, exist_ok=True)
# skill_dir = scaffold_skill("abc_skill")      # idempotent
# ensure_skill_venv(skill_dir, reuse_host_libs=True)  # installs pandas into plugin venv
#
# # Load StateGraph in-process
# loaded = load_skill_stategraph_inproc(skill_dir, package_name="abc_skill")
# print("Loaded skill:", loaded.dto)