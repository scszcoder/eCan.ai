# inproc_loader.py
import sys, importlib
from contextlib import contextmanager, ExitStack
from pathlib import Path
from typing import List
from agent.ec_skill import EC_Skill

def _site_packages(venv_dir: Path) -> List[Path]:
    if sys.platform == "win32":
        return [venv_dir / "Lib" / "site-packages"]
    pyver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return [venv_dir / "lib" / pyver / "site-packages"]

@contextmanager
def temp_sys_path(paths: List[Path]):
    added = [str(p) for p in paths if p.exists()]
    for p in added: sys.path.insert(0, p)
    try: yield
    finally:
        for p in added:
            try: sys.path.remove(p)
            except ValueError: pass

def load_skill_stategraph_inproc(skill_dir: Path, skill_name="abc") -> EC_Skill:
    venv_dir = skill_dir / ".venv"
    skill_full_dir  = skill_dir / f"{skill_name}_skill"
    if not skill_full_dir.exists():
        raise FileNotFoundError(f"Missing skill folder: {skill_full_dir}")

    with ExitStack() as stack:
        # Make plugin package & its venv deps importable
        stack.enter_context(temp_sys_path([skill_full_dir]))
        stack.enter_context(temp_sys_path(_site_packages(venv_dir)))

        mod = importlib.import_module(f"{skill_name}.abc_skill")
        if not hasattr(mod, "build_skill"):
            raise RuntimeError("Plugin must export build_skill() returning (SkillDTO, StateGraph)")
        custom_skill = mod.build_skill()
        if not isinstance(custom_skill, EC_Skill):
            raise TypeError("build_skill() must return EC_Skill")
        return custom_skill
