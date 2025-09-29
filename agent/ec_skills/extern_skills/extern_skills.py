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
import os, sys, json, subprocess, textwrap
from pathlib import Path
import venv

APP_NAME = "MyApp"              # change to your real app name
SKILLS_DIRNAME = "my_skills"    # as requested

def user_plugins_root() -> Path:
    """Return the per-user skills root dir."""
    if sys.platform == "win32":
        base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / APP_NAME / SKILLS_DIRNAME
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / SKILLS_DIRNAME
    else:
        return Path.home() / ".local" / "share" / APP_NAME / SKILLS_DIRNAME


def scaffold_skill(skill_name: str) -> Path:
    """
    Create a new multi-file skill scaffold:
      <root>/my_skills/<skill_name>/{requirements.txt, <skill_name>/__init__.py, <skill_name>/abc_skill.py}
    Put 'pandas' in requirements.txt as an example.
    """
    root = user_plugins_root()
    pkg_root = root / skill_name
    mod_pkg = pkg_root / skill_name   # package folder with same name
    mod_pkg.mkdir(parents=True, exist_ok=True)

    # 1) requirements.txt — plugin-only deps (host already has langchain)
    (pkg_root / "requirements.txt").write_text("pandas>=2.2\n", encoding="utf-8")

    # 2) __init__.py (empty)
    (mod_pkg / "__init__.py").write_text("", encoding="utf-8")

    # 3) abc_skill.py — entry module
    (mod_pkg / "abc_skill.py").write_text(textwrap.dedent(f"""\
        \"\"\"Example skill entry module.

        Requirements:
          - Reuses host's langchain (provided by host runtime)
          - Installs pandas (declared in requirements.txt)
        \"\"\"
        import json, sys

        # Reuse host-provided library (host must have it installed)
        import langchain    # comes from host environment via --system-site-packages

        # Plugin-specific dependency (installed into this skill's venv)
        try:
            import pandas as pd
        except Exception as e:
            raise RuntimeError("pandas is not installed in this skill venv") from e

        def run(ctx: dict) -> dict:
            \"\"\"Skill entrypoint called by the host. Returns JSON-serializable data.\"\"\"
            message = ctx.get("message", "hello from abc_skill")
            df = pd.DataFrame({{"message": [message], "lc_version": [getattr(langchain, "__version__", "unknown")]}})
            return {{"ok": True, "rows": int(len(df)), "langchain_version": getattr(langchain, "__version__", "unknown")}}

        if __name__ == "__main__":
            # Support: python -m {skill_name}.abc_skill (stdin JSON -> stdout JSON)
            payload = json.loads(sys.stdin.read() or "{{}}")
            out = run(payload)
            sys.stdout.write(json.dumps(out))
        """), encoding="utf-8")

    return pkg_root


def _skill_paths(skill_dir: Path) -> tuple[Path, Path, Path]:
    """Return (venv_dir, python_exe, pip_exe) for a skill."""
    venv_dir = skill_dir / ".venv"
    if sys.platform == "win32":
        py = venv_dir / "Scripts" / "python.exe"
        pip = venv_dir / "Scripts" / "pip.exe"
    else:
        py = venv_dir / "bin" / "python"
        pip = venv_dir / "bin" / "pip"
    return venv_dir, py, pip


def ensure_skill_env(skill_dir: Path, allow_reuse_host_libs: bool = True) -> None:
    """
    Create/prepare per-skill venv.
    If allow_reuse_host_libs=True we pass --system-site-packages so the skill can
    reuse host-installed libs (e.g., langchain) without reinstalling them.
    Then we install the skill's requirements.txt (e.g., pandas).
    """
    venv_dir, py, pip = _skill_paths(skill_dir)
    if not venv_dir.exists():
        # Create venv with or without access to host site-packages
        builder = venv.EnvBuilder(with_pip=True, system_site_packages=allow_reuse_host_libs, clear=False, upgrade=False)
        builder.create(str(venv_dir))

    req = skill_dir / "requirements.txt"
    if req.exists():
        subprocess.check_call([str(pip), "install", "-r", str(req)])
    # else: no plugin-only deps to install


def run_skill_subprocess(skill_name: str, ctx: dict, timeout: int = 20) -> dict:
    """
    Run <skill_name>/abc_skill.py by invoking module '{skill_name}.abc_skill'
    inside the skill's venv as a subprocess, piping ctx JSON over stdin.
    """
    skills_root = user_plugins_root()
    skill_dir = skills_root / skill_name
    if not skill_dir.exists():
        raise FileNotFoundError(f"Skill '{skill_name}' not found at {skill_dir}")

    ensure_skill_env(skill_dir, allow_reuse_host_libs=True)

    venv_dir, py, _ = _skill_paths(skill_dir)

    # Make the package importable: add the skill directory (which contains the package folder)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(skill_dir), env.get("PYTHONPATH", "")])

    module_path = f"{skill_name}.abc_skill"
    proc = subprocess.Popen(
        [str(py), "-m", module_path],
        cwd=str(skill_dir),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    out, err = proc.communicate(json.dumps(ctx), timeout=timeout)
    if err:
        # Surface plugin logs
        print(f"[{skill_name} stderr]\n{err}", file=sys.stderr)

    if proc.returncode != 0:
        raise RuntimeError(f"Skill '{skill_name}' exited with code {proc.returncode}")

    return json.loads(out or "{{}}")


# # somewhere in your app at startup (first-run experience)
# from host_plugins import scaffold_skill, user_plugins_root
#
# root = user_plugins_root()
# root.mkdir(parents=True, exist_ok=True)
# skill_path = scaffold_skill("abc_skill")   # creates the template once
# print("Skill scaffold at:", skill_path)
#
# # later, when you want to run it
# from host_plugins import run_skill_subprocess
# result = run_skill_subprocess("abc_skill", {"message": "Hi from host!"})
# print("Skill result:", result)