# %APPDATA%/MyApp/my_skills/
#   abc_skill/
#     requirements.txt        # plugin-only deps (e.g., pandas)
#     abc_skill/              # package folder
#       abc_skill.py          # entry module (run(ctx) + __main__)
# On macOS: ~/Library/Application Support/MyApp/my_skills/…
# On Linux: ~/.local/share/MyApp/my_skills/…

# host_plugins.py
from __future__ import annotations
import os, sys, json, subprocess, textwrap
from pathlib import Path
# venv only needed in development environment, import lazily
# import venv  # Imported when needed in ensure_skill_venv()
from utils.logger_helper import logger_helper as logger

APP_NAME = "eCan.ai"              # change to your real app name
SKILLS_DIRNAME = "my_skills"    # as requested
IS_FROZEN = getattr(sys, 'frozen', False)


# ===============================================================================
def user_skills_root() -> Path:
    """Return the per-user skills root dir.
    
    Uses app_info.appdata_path + SKILLS_DIRNAME:
    - Development environment: <project_root>/my_skills
    - Production environment: <system_appdata>/eCan.ai/my_skills
    """
    try:
        # Import app_info to get the configured appdata path
        from config.app_info import app_info
        
        # Get appdata path from app_info (handles dev/prod automatically)
        appdata_path = Path(app_info.appdata_path)
        # switch debug read prod install appdata path
        # appdata_path = Path(app_info._prod_appdata_path())
        skills_root = appdata_path / SKILLS_DIRNAME
        
        # Log the path based on environment
        env_mode = "DEV MODE" if not IS_FROZEN else "PRODUCTION MODE"
        logger.info(f"[{env_mode}] Using skills directory: {skills_root}")
        
        # Ensure directory exists
        skills_root.mkdir(parents=True, exist_ok=True)
        
        return skills_root
        
    except Exception as e:
        # Fallback: use simple platform-specific path if app_info is not available
        logger.warning(f"Failed to get appdata path from app_info: {e}, using fallback")
        
        if sys.platform == "win32":
            base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
            fallback_path = base / APP_NAME / SKILLS_DIRNAME
        elif sys.platform == "darwin":
            fallback_path = Path.home() / "Library" / "Application Support" / APP_NAME / SKILLS_DIRNAME
        else:
            fallback_path = Path.home() / ".local" / "share" / APP_NAME / SKILLS_DIRNAME
        
        logger.info(f"[FALLBACK] Using fallback skills directory: {fallback_path}")
        fallback_path.mkdir(parents=True, exist_ok=True)
        return fallback_path


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


def _get_skill_python_executable(skill_dir: Path = None) -> str:
    """Get Python interpreter path for skill execution.
    
    In PyInstaller environment:
        - Use sys.executable (the packaged exe) directly
        - Skills share the same packaged environment
    
    In development environment:
        - Try to use skill's local venv if available
        - Fall back to current Python interpreter
    
    Args:
        skill_dir: Path to skill directory (optional, used in dev environment)
    
    Returns:
        Path to Python executable as string
    """
    # In packaged environment, sys.executable is the exe file containing all dependencies
    # Skills should use the same exe to ensure environment consistency
    if IS_FROZEN:
        logger.info(f"[ExternSkills] Running in PyInstaller environment, using current executable: {sys.executable}")
        return sys.executable
    
    # Development environment: try skill's local venv first
    if skill_dir:
        venv_dir = skill_dir / ".venv"
        if venv_dir.exists():
            # Try to find Python in skill's venv
            if sys.platform == "win32":
                venv_python = venv_dir / "Scripts" / "python.exe"
            else:
                venv_python = venv_dir / "bin" / "python"
            
            if venv_python.exists():
                logger.info(f"[ExternSkills] Using skill's venv Python: {venv_python}")
                return str(venv_python)
    
    # Check if currently in virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        logger.info(f"[ExternSkills] Already in virtual environment: {sys.executable}")
        return sys.executable
    
    # Try to find virtual environment in project root directory
    try:
        project_root = Path(__file__).parent.parent.parent.parent
        venv_paths = [
            project_root / "venv" / "bin" / "python",
            project_root / "venv" / "Scripts" / "python.exe",
        ]
        
        for venv_python in venv_paths:
            if venv_python.exists():
                logger.info(f"[ExternSkills] Found project venv Python: {venv_python}")
                return str(venv_python)
    except Exception as e:
        logger.warning(f"[ExternSkills] Error finding project venv: {e}")
    
    # If virtual environment not found, return current interpreter
    logger.info(f"[ExternSkills] Using current Python interpreter: {sys.executable}")
    return sys.executable


def _venv_paths(venv_dir: Path):
    """Get venv Python and pip paths (for development environment only).
    
    Note: This function should only be called in development environment.
    In PyInstaller environment, use _get_skill_python_executable() instead.
    """
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe", venv_dir / "Scripts" / "pip.exe"
    return venv_dir / "bin" / "python", venv_dir / "bin" / "pip"

def ensure_skill_venv(skill_dir: Path, *, reuse_host_libs: bool = True):
    """Ensure skill's virtual environment and dependencies are ready.
    
    In PyInstaller environment:
        - Skip venv creation (use packaged environment)
        - Log warning if requirements.txt exists (dependencies should be pre-packaged)
    
    In development environment:
        - Create local venv if not exists
        - Install dependencies from requirements.txt
    Args:
        skill_dir: Path to skill directory
        reuse_host_libs: Whether to use system site packages (dev environment only)
    """
    # Determine requirements file path once to avoid UnboundLocalError in different branches
    # Support both legacy and new layouts
    req_candidates = [
        skill_dir / "requirements.txt",
        skill_dir / "code_dir" / "requirements.txt",
        skill_dir / "code_skill" / "requirements.txt",
    ]
    req = next((p for p in req_candidates if p.exists()), None)
    # In PyInstaller environment, skip venv creation
    if IS_FROZEN:
        logger.info(f"[ExternSkills] Running in PyInstaller environment, skipping venv creation for {skill_dir.name}")
        if req and req.exists():
            logger.warning(f"[ExternSkills] Skill {skill_dir.name} has requirements.txt but running in packaged environment")
            logger.warning(f"[ExternSkills] Dependencies should be pre-packaged. File: {req}")
            
            # Read and log requirements for debugging
            try:
                with open(req, 'r', encoding='utf-8') as f:
                    requirements = f.read().strip()
                    if requirements:
                        logger.info(f"[ExternSkills] Required packages: {requirements}")
            except Exception as e:
                logger.error(f"[ExternSkills] Error reading requirements.txt: {e}")
        return  # Skip venv creation in packaged environment

    # Development environment: create venv and install dependencies
    logger.info(f"[ExternSkills] Setting up development venv for skill: {skill_dir.name}")
    
    venv_dir = skill_dir / ".venv"
    if not venv_dir.exists():
        logger.info(f"[ExternSkills] Creating venv at: {venv_dir}")
        try:
            # Use unified VenvHelper to create virtual environment
            # This uses subprocess method which works in all environments
            from utils.venv_helper import VenvHelper
            
            success, error = VenvHelper.create_venv(
                venv_path=venv_dir,
                system_site_packages=reuse_host_libs,
                with_pip=True
            )
            
            if not success:
                logger.error(f"[ExternSkills] Failed to create venv: {error}")
                raise RuntimeError(f"Failed to create virtual environment: {error}")
            
            logger.info(f"[ExternSkills] Venv created successfully")
        except Exception as e:
            logger.error(f"[ExternSkills] Failed to create venv: {e}")
            raise
    else:
        logger.info(f"[ExternSkills] Venv already exists at: {venv_dir}")
    
    # Install dependencies from requirements.txt
    if req and req.exists():
        logger.info(f"[ExternSkills] Installing dependencies from: {req}")
        try:
            py, pip = _venv_paths(venv_dir)
            
            # Build pip install command with cross-platform support
            pip_cmd = [str(pip), "install", "-r", str(req)]
            
            # Log command for debugging
            logger.debug(f"[ExternSkills] Running: {' '.join(pip_cmd)}")
            
            # Prepare subprocess parameters with console hiding for frozen environment
            base_kwargs = {
                'timeout': 300,  # 5 minutes timeout
                'capture_output': True,
                'text': True,
                'encoding': 'utf-8',
                'errors': 'replace',  # Handle encoding issues on Windows
            }
            
            # Use unified subprocess helper to prevent console window popup
            from utils.subprocess_helper import get_subprocess_kwargs
            subprocess_kwargs = get_subprocess_kwargs(base_kwargs)
            
            # Execute with timeout to prevent hanging
            result = subprocess.run(pip_cmd, **subprocess_kwargs)
            
            if result.returncode == 0:
                logger.info(f"[ExternSkills] ✅ Dependencies installed successfully")
                if result.stdout:
                    logger.debug(f"[ExternSkills] pip output: {result.stdout.strip()}")
            else:
                logger.error(f"[ExternSkills] ❌ pip install failed with return code {result.returncode}")
                if result.stderr:
                    logger.error(f"[ExternSkills] pip stderr: {result.stderr.strip()}")
                raise subprocess.CalledProcessError(result.returncode, pip_cmd, result.stdout, result.stderr)
                
        except subprocess.TimeoutExpired as e:
            logger.error(f"[ExternSkills] ❌ Dependency installation timed out after 5 minutes")
            raise
        except subprocess.CalledProcessError as e:
            logger.error(f"[ExternSkills] ❌ Failed to install dependencies: {e}")
            raise
        except Exception as e:
            logger.error(f"[ExternSkills] ❌ Unexpected error during dependency installation: {e}")
            raise
    else:
        logger.info(f"[ExternSkills] No requirements.txt found, skipping dependency installation")


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