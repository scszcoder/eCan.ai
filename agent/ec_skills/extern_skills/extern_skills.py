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
import os, sys, json, subprocess, textwrap, uuid
from pathlib import Path
import venv
from typing import Any, Callable

APP_NAME = "eCan.ai"              # change to your real app name
SKILLS_DIRNAME = "my_skills"    # as requested



# ===============================================================================
def user_plugins_root() -> Path:
    """Return the per-user skills root dir."""
    if sys.platform == "win32":
        base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / APP_NAME / SKILLS_DIRNAME
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / SKILLS_DIRNAME
    else:
        return Path.home() / ".local" / "share" / APP_NAME / SKILLS_DIRNAME


def scaffold_skill(skill_name: str = "abc_skill", description: str = "This skill ....") -> Path:
    root = user_plugins_root()
    skill_dir = root / skill_name
    pkg = skill_dir / skill_name
    pkg.mkdir(parents=True, exist_ok=True)

    # plugin-only deps (host already provides langchain)
    (skill_dir / "requirements.txt").write_text("pandas>=2.2\n", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    # Entry module returns (SkillDTO, StateGraph)
    (pkg / "abc_skill.py").write_text(textwrap.dedent(f"""\
        from typing import Dict, Any
        from models import SkillDTO
        from langgraph.graph import StateGraph

        # plugin can use host-provided libs and its own extras:
        import langchain             # from host environment
        import pandas as pd          # from this plugin's .venv

        Description:
            {description}
            
        def build_stategraph() -> Any:
            # Minimal StateGraph example; adjust to your real state type
            # For demo we assume dict-state
            g = StateGraph(dict)

            # Example nodes
            def start(state: dict):
                state["msg"] = state.get("msg", "hi")
                return state

            def done(state: dict):
                state["done"] = True
                return state

            g.add_node("start", start)
            g.add_node("done", done)
            g.add_edge("start", "done")
            g.set_entry_point("start")
            g.set_finish_point("done")
            return g

        def build_skill():
            dto = SkillDTO(
                name="{skill_name}",
                description="{description}",
                config={{"uses": ["pandas", "langgraph"], "langgraph_version": getattr(langgraph, "__version__", "unknown")}}
            )
            sg = build_stategraph()
            return dto, sg
        """), encoding="utf-8")

    return skill_dir



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