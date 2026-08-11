import traceback
import asyncio
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Any
import inspect
import json
from agent.cloud_api.constants import SkillSource
from agent.ec_agents.agent_utils import load_agent_skills_from_cloud
# from agent.ec_skills.ecbot_rpa.ecbot_rpa_chatter_skill import create_rpa_helper_chatter_skill
# from agent.ec_skills.ecbot_rpa.ecbot_rpa_skill import create_rpa_helper_skill
# from agent.ec_skills.search_1688.search_1688_skill import create_search_1688_skill
# from agent.ec_skills.search_digi_key.search_digi_key_skill import create_search_digi_key_skill
# from agent.ec_skills.search_parts.search_parts_chatter_skill import create_search_parts_chatter_skill
# from agent.ec_skills.search_parts.search_parts_skill import create_search_parts_skill
# from agent.ec_skills.self_test.self_test_skill import create_self_test_skill
# from agent.ec_skills.self_test.self_test_chatter_skill import create_self_test_chatter_skill
# from agent.ec_skills.dev_utils.skill_dev_utils import create_test_dev_skill

from agent.mcp.server.tool_schemas import tool_schemas
from utils.logger_helper import logger_helper as logger
import re as _re
from agent.ec_skills.extern_skills.extern_skills import ensure_skill_venv
from agent.ec_skills.extern_skills.inproc_loader import temp_sys_path, _site_packages
from agent.ec_skill import EC_Skill
# from agent.ec_skills.flowgram2langgraph import flowgram2langgraph
from langgraph.graph import StateGraph
from app_context import AppContext
from config.app_info import app_info
from agent.ec_skills.dev_defs import BreakpointManager
from agent.ec_skills.flowgram2langgraph_v2 import flowgram2langgraph_v2
from agent.db.models.skill_model import DBAgentSkill


# --- Skill-build executor & status reporting --------------------------------
# Phase B: skill construction (LangGraph compile + Pydantic + prompt-template
# loading) is CPU-bound under the GIL but the qasync loop IS the Qt UI thread.
# Running these on the loop directly blocks paints and click handling → Windows
# escalates to "Not Responding" → AppHangB1 (see memory project-startup-apphang).
# A shared ThreadPoolExecutor lets the loop keep ticking even though the pool
# workers serialize on the GIL — the gain is responsiveness, not throughput.
#
# NOTE: prior attempts that made things worse and must NOT be repeated:
#   - per-creator new_event_loop() in a fresh executor (startup → 3+ min)
#   - per-skill `await asyncio.sleep(0)` (Batch 3 → 164 s)
# Keep a SINGLE module-level pool; do not construct per-batch.
_SKILL_POOL: Optional[ThreadPoolExecutor] = None


def _get_skill_pool() -> ThreadPoolExecutor:
    global _SKILL_POOL
    if _SKILL_POOL is None:
        workers = min(4, (os.cpu_count() or 2))
        _SKILL_POOL = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="skill-build"
        )
    return _SKILL_POOL


# Phase E: optional status callback invoked after each skill finishes building.
# MainGUI registers a callable that forwards to StartupBusyOverlay.set_status.
# The callback must be safe to invoke from any thread (the executor workers
# call it); typical implementation uses QMetaObject.invokeMethod with a
# QueuedConnection to marshal back to the GUI thread. Kept opt-in so cloud
# workers (no Qt) don't need any of this.
_status_callback: Optional[Callable[[str], None]] = None


def set_status_callback(cb: Optional[Callable[[str], None]]) -> None:
    """Register (or clear) the build-progress callback. None disables reporting."""
    global _status_callback
    _status_callback = cb


def _report_status(text: str) -> None:
    cb = _status_callback
    if cb is None:
        return
    try:
        cb(text)
    except Exception:
        # Status reporting must never break skill build.
        pass


def _log_duplicate_names(all_skills: list) -> None:
    """Log skills sharing the same name with different IDs.

    Same name + different IDs is legitimate (e.g. a built-in example and a user skill
    can share a name). Only warns about the same ID appearing twice (merge bug).
    """
    id_count: dict = {}
    for sk in all_skills:
        if not hasattr(sk, 'name'):
            continue
        sk_id = getattr(sk, 'id', None)
        id_count[sk_id] = id_count.get(sk_id, 0) + 1

    name_count: dict = {}
    for sk in all_skills:
        if not hasattr(sk, 'name'):
            continue
        name_count[sk.name] = name_count.get(sk.name, 0) + 1

    dup_ids = {i: c for i, c in id_count.items() if c > 1}
    dup_names = {n: c for n, c in name_count.items() if c > 1}

    if dup_ids:
        # Same ID appearing multiple times — this IS a bug
        logger.warning(f"[build_agent_skills] ⚠️ Duplicate skill IDs detected: {dup_ids}")
        for sk in all_skills:
            if getattr(sk, 'id', None) in dup_ids:
                logger.warning(
                    f"[build_agent_skills]   -> id={sk.id!r}  name={sk.name!r}  "
                    f"askid={getattr(sk, 'askid', '')!r}  path={getattr(sk, 'path', '')!r}"
                )
    elif dup_names:
        # Same name with different IDs — legitimate, just informational
        logger.info(f"[build_agent_skills] ℹ️ Skills sharing a name (different IDs — normal): {dup_names}")
    else:
        logger.info(f"[build_agent_skills] ✅ No duplicate IDs or names in final list")



def _get_resource_skills_root() -> Path:
    """Get the root path for resource/my_skills directory.
    
    Centralized path management for example skills.
    Now uses unified resolution from extern_skills.
    """
    from agent.ec_skills.extern_skills.extern_skills import resource_skills_root
    return resource_skills_root()


async def build_agent_skills_parallel(mainwin, db_skill_names: set = None):
    """Optimized batch parallel skill creation"""
    logger.info("[build_agent_skills] Building skills with optimized batching...")

    # Group skills by priority and dependencies
    # Batch 1: Core skills (fast creation)
    core_skills = [
        # ("self_test", create_self_test_skill),
        # ("self_test_chatter", create_self_test_chatter_skill),
        # ("test_dev", create_test_dev_skill)
    ]

    # Batch 2: RPA skills (medium complexity)
    # rpa_skills = [
    #     ("rpa_helper", create_rpa_helper_skill),
    #     ("rpa_helper_chatter", create_rpa_helper_chatter_skill),
    # ]
    rpa_skills = []

    # Batch 3: Advanced skills - auto-scan resource/my_skills and appdata/my_skills
    # Passes db_skill_names so appdata scan skips skills already loaded from DB
    resource_skill_names = scan_resource_skills(exclude_names=db_skill_names)

    # Sync creator. _create_skills_batch dispatches into the shared ThreadPool;
    # the old async-wrapper-that-just-calls-sync pattern was misleading — it
    # never actually yielded to the qasync loop. Keep these plain sync funcs so
    # the executor offload is unambiguous.
    def _make_resource_creator(skill_name: str):
        def _creator(mw):
            return create_skill_from_resource(skill_name, mainwin=mw)
        return _creator

    advanced_skills = [
        (name, _make_resource_creator(name))
        for name in resource_skill_names
    ]
    logger.info(f"[build_agent_skills] Auto-discovered {len(advanced_skills)} skills from resource/my_skills: {resource_skill_names}")

    start_time = time.time()
    total_skills = len(core_skills) + len(rpa_skills) + len(advanced_skills)
    logger.info(f"[build_agent_skills] Starting optimized creation of {total_skills} skills in 3 batches...")

    all_skills = []

    # Batch 1: Core skills (concurrency=4)
    logger.info(f"[build_agent_skills] Batch 1: Creating {len(core_skills)} core skills...")
    batch1_start = time.time()
    batch1_results = await _create_skills_batch(mainwin, core_skills, max_concurrent=4)
    all_skills.extend(batch1_results)
    batch1_time = time.time() - batch1_start
    logger.info(f"[build_agent_skills] Batch 1 completed in {batch1_time:.3f}s")

    # Batch 2: RPA skills (concurrency=3, avoid resource contention)
    logger.info(f"[build_agent_skills] Batch 2: Creating {len(rpa_skills)} RPA skills...")
    batch2_start = time.time()
    batch2_results = await _create_skills_batch(mainwin, rpa_skills, max_concurrent=3)
    all_skills.extend(batch2_results)
    batch2_time = time.time() - batch2_start
    logger.info(f"[build_agent_skills] Batch 2 completed in {batch2_time:.3f}s")

    # Batch 3: Advanced skills (concurrency=2, avoid overload)
    logger.info(f"[build_agent_skills] Batch 3: Creating {len(advanced_skills)} advanced skills...")
    batch3_start = time.time()
    batch3_results = await _create_skills_batch(mainwin, advanced_skills, max_concurrent=2)
    all_skills.extend(batch3_results)
    batch3_time = time.time() - batch3_start
    logger.info(f"[build_agent_skills] Batch 3 completed in {batch3_time:.3f}s")

    total_time = time.time() - start_time
    logger.info(f"[build_agent_skills] Optimized parallel creation completed in {total_time:.3f}s")
    logger.info(f"[build_agent_skills] Successfully created {len(all_skills)}/{total_skills} skills")

    return all_skills


def _create_skill_from_workflow(
    core_dict: dict, 
    workflow: StateGraph, 
    skill_name: str, 
    json_path: Path, 
    source: str = "ui") -> Optional[EC_Skill]:
    """Create EC_Skill and populate fields from diagram dict + an already built workflow.

    - For `source="ui"`, keep the historical behavior and do NOT overwrite `id`.
    - For `source="code"`, ensure deterministic stable id generation.
    """
    try:
        if not workflow:
            logger.warning(f"[_create_skill_from_workflow] Empty workflow for {skill_name}")
            return None
        sk = EC_Skill()
        sk.name = core_dict.get("skillName") or core_dict.get("name") or skill_name
        sk.version = str(core_dict.get("version", "1.0.0"))
        sk.description = core_dict.get("description", "")
        sk.diagram = core_dict

        if isinstance(core_dict.get("config"), dict):
            sk.config = core_dict["config"]

        run_mode = core_dict.get("run_mode")
        if run_mode in ("developing", "released"):
            sk.run_mode = run_mode

        # Cloud execution settings - check both top-level (from file) and config dict (from DB)
        config = sk.config or {}
        sk.run_in_cloud = bool(core_dict.get("run_in_cloud", config.get("run_in_cloud", False)))
        sk.hybrid_cloud_mode = bool(core_dict.get("hybrid_cloud_mode", config.get("hybrid_cloud_mode", False)))
        sk.local_helper_skill_id = core_dict.get("local_helper_skill_id", config.get("local_helper_skill_id", None))
        sk.local_helper_machine = core_dict.get("local_helper_machine", config.get("local_helper_machine", None))

        sk.set_work_flow(workflow)
        sk.source = source
        sk.path = str(json_path)

        # Ensure stable ID behavior.
        if source == "code":
            from agent.ec_skill import _generate_stable_id
            sk.id = _generate_stable_id(sk.name, sk.source)

        return sk
    except Exception as e:
        logger.warning(f"[_create_skill_from_workflow] Failed to create skill {skill_name}: {e}")
        logger.debug(f"[_create_skill_from_workflow] Traceback: {traceback.format_exc()}")
        return None


def _get_appdata_skills_root() -> Path:
    """Get the root path for appdata/my_skills directory (user-created skills).
    
    In dev mode this is <project_root>/my_skills.
    In prod mode this is <appdata>/my_skills.
    Now uses unified resolution from extern_skills.
    """
    from agent.ec_skills.extern_skills.extern_skills import user_skills_root
    return user_skills_root()


def _scan_skills_in_dir(skills_root: Path, label: str) -> List[str]:
    """Scan a directory for skill folders matching *_skill/ with diagram_dir/ or code_dir/.

    NOTE (merge fix 2026-05-12): dev's version delegated to
    ``extern_skills.scan_skills_in_dir`` — but that function does not exist in
    ``extern_skills.py`` (it ships ``scan_all_skills`` with a different
    signature), so the delegation broke resource-skill scanning entirely
    (``cannot import name 'scan_skills_in_dir'`` → no resource skills compiled →
    "nothing works").  Restored the original inline implementation.

    Returns:
        List of skill names (without _skill suffix)
    """
    if not skills_root.exists():
        logger.debug(f"[scan_resource_skills] {label} not found: {skills_root}")
        return []

    skill_names = []
    for item in skills_root.iterdir():
        if item.is_dir() and item.name.endswith('_skill'):
            has_diagram = (item / 'diagram_dir').exists()
            has_code = (item / 'code_dir').exists() or (item / 'code_skill').exists()

            if has_diagram or has_code:
                skill_name = item.name[:-6]  # Remove '_skill' suffix
                skill_names.append(skill_name)
                logger.debug(f"[scan_resource_skills] Found skill in {label}: {skill_name}")

    return skill_names


def scan_resource_skills(exclude_names: set = None) -> List[str]:
    """Scan resource/my_skills and appdata/my_skills directories for skill names.
    
    Looks for directories matching pattern *_skill/ that contain diagram_dir/.
    Scans both resource/my_skills (built-in examples) and appdata/my_skills
    (user-created skills that may not be in DB yet, e.g. basic_chatter).
    
    Args:
        exclude_names: Optional set of skill names to exclude (e.g. DB skill names
                       already loaded). Only applied to appdata scan to avoid
                       redundant compilation.
    
    Returns:
        List of unique skill names (without _skill suffix)
    """
    try:
        # Scan resource/my_skills (built-in examples — always included)
        resource_names = _scan_skills_in_dir(_get_resource_skills_root(), "resource/my_skills")
        
        # Also scan appdata/my_skills (user-created skills on disk)
        appdata_root = _get_appdata_skills_root()
        appdata_names = _scan_skills_in_dir(appdata_root, "appdata/my_skills")
        
        # Merge, deduplicate; exclude DB skills from appdata to avoid redundant compilation
        seen = set()
        _excl = exclude_names or set()
        skill_names = []
        for name in resource_names:
            if name not in seen:
                seen.add(name)
                skill_names.append(name)
        for name in appdata_names:
            if name not in seen and name not in _excl:
                seen.add(name)
                skill_names.append(name)
        
        skipped = len(appdata_names) - len([n for n in appdata_names if n not in _excl and n not in set(resource_names)])
        logger.info(f"[scan_resource_skills] Found {len(skill_names)} skills to compile "
                     f"(resource={len(resource_names)}, appdata_new={len(skill_names) - len(resource_names)}, "
                     f"appdata_skipped_db={skipped}): {skill_names}")
        return skill_names
        
    except Exception as e:
        logger.error(f"[scan_resource_skills] Error scanning: {e}")
        return []


def create_skill_from_resource(
    skill_name: str,
    json_filename: Optional[str] = None,
    bundle_filename: Optional[str] = None,
    mainwin=None,
) -> Optional[EC_Skill]:
    """
    Create a skill from resource/my_skills directory.
    
    Uses load_skill_from_folder to handle both diagram_dir and code_dir skills.
    
    Args:
        skill_name: Name of the skill (e.g., "web_rag_assistant", "demo0")
        json_filename: Optional custom JSON filename (legacy, ignored)
        bundle_filename: Optional custom bundle filename (legacy, ignored)
    
    Returns:
        EC_Skill object or None if creation fails
    
    Example:
        create_skill_from_resource("passive0")  # Loads from resource/my_skills/passive0_skill/
    """
    try:
        # Get root directory — check resource/my_skills first, then appdata/my_skills
        skill_folder = _get_resource_skills_root() / f"{skill_name}_skill"
        if not skill_folder.exists():
            skill_folder = _get_appdata_skills_root() / f"{skill_name}_skill"
        if not skill_folder.exists():
            logger.error(f"[create_skill_from_resource] Skill folder not found in resource or appdata: {skill_name}_skill")
            return None
        
        resource_root = _get_resource_skills_root().resolve()
        skill_folder_resolved = skill_folder.resolve()
        is_resource_example = skill_folder_resolved.is_relative_to(resource_root)

        # Use load_skill_from_folder which handles both diagram_dir and code_dir
        sk = load_skill_from_folder(skill_folder, mainwin=mainwin)
        if not sk:
            logger.warning(f"[create_skill_from_resource] Failed to load skill from {skill_folder}")
            return None

        # Only bundled resource examples are read-only code skills.
        # User-created appdata/my_skills entries should remain editable.
        if is_resource_example:
            sk.source = SkillSource.CODE.value
            try:
                from agent.ec_skill import _generate_stable_id
                sk.id = _generate_stable_id(sk.name, sk.source)
            except Exception:
                pass
        else:
            # For UI skills loaded from appdata, preserve the DB id so that
            # agent_task_skill_rels (and other FK references) survive restarts.
            try:
                _mw = mainwin
                if _mw is None:
                    from utils.path_manager import PathManager as _PM
                    _mw = _PM.get_main_window()
                _db_mgr = getattr(_mw, 'ec_db_mgr', None) if _mw else None
                _sk_svc = getattr(_db_mgr, 'skill_service', None) if _db_mgr else None
                if _sk_svc:
                    _hits = _sk_svc.search_skills(name=sk.name)
                    _exact = [h for h in (_hits or []) if h.get('name') == sk.name]
                    _match = _exact[0] if _exact else (_hits[0] if _hits else None)
                    if _match:
                        _db_id = _match.get('id', '')
                        if _db_id:
                            sk.id = _db_id
            except Exception:
                pass

        logger.info(f"[create_skill_from_resource] ✅ Created skill '{sk.name}' from {skill_folder.name}")
        return sk
        
    except Exception as e:
        logger.error(f"[create_skill_from_resource] Failed to create {skill_name}: {e}")
        logger.debug(f"[create_skill_from_resource] Traceback: {traceback.format_exc()}")
        return None


async def create_demo0_skill(mainwin) -> Optional[EC_Skill]:
    """Create demo0 skill from resource/my_skills example"""
    return create_skill_from_resource("demo0")


async def create_ebay_fullfill_messages_skill(mainwin) -> Optional[EC_Skill]:
    """Create ebay_fullfill_messages skill from resource/my_skills example"""
    return create_skill_from_resource("ebay_fullfill_messages")


async def create_search_digikey_chatter_skill(mainwin) -> Optional[EC_Skill]:
    """Create search_digikey_chatter skill from resource/my_skills example (code_dir only)."""
    try:
        skills_root = _get_resource_skills_root()
        skill_folder = skills_root.joinpath("search_digikey_chatter_skill")

        sk = load_skill_from_folder(skill_folder, mainwin)
        if not sk:
            return None

        # Treat resource examples as code-based skills (read-only + deterministic id)
        sk.source = SkillSource.CODE.value
        try:
            from agent.ec_skill import _generate_stable_id
            sk.id = _generate_stable_id(sk.name, sk.source)
        except Exception:
            pass

        return sk
    except Exception as e:
        logger.error(f"[create_search_digikey_chatter_skill] Failed: {e}")
        logger.debug(f"[create_search_digikey_chatter_skill] Traceback: {traceback.format_exc()}")
        return None


async def _create_skills_batch(mainwin, skill_creators, max_concurrent=4):
    """Create a batch of skills, dispatching the CPU-bound work to a thread pool.

    Phase B (2026-05-17): switched from "fake-async on the qasync loop" to a
    shared ThreadPoolExecutor (`_get_skill_pool`). The pool size IS the
    concurrency limit; ``max_concurrent`` is kept in the signature for caller
    compatibility but ignored. The qasync loop now stays responsive while
    LangGraph compile / Pydantic / prompt-template work runs off-thread,
    preventing the Windows AppHangB1 escalations recorded on 2026-05-16.

    Thread-safety guard rails (do NOT loosen without checking):
      - ``temp_sys_path`` (inproc_loader.py) holds an RLock for the duration
        of code-skill imports, so sys.path mutation is safe.
      - Diagram skills (the vast majority) touch no shared mutable state.
      - Qt widgets must NOT be touched from creator funcs; mainwin access is
        read-only for context lookup.

    Prior failures retained as warnings:
      - Per-creator ``new_event_loop()`` in a fresh executor — startup 3+ min.
      - ``await asyncio.sleep(0)`` per skill — Batch 3 from 15s to 164s.
    """
    del max_concurrent  # pool size governs concurrency now
    if not skill_creators:
        return []

    loop = asyncio.get_event_loop()
    pool = _get_skill_pool()
    total = len(skill_creators)
    done_counter = {"n": 0}

    def _sync_build(skill_name: str, creator_func) -> Optional[Any]:
        try:
            return creator_func(mainwin)
        except Exception as e:
            logger.error(f"[build_agent_skills] ❌ Failed to create {skill_name}: {e}")
            logger.debug(f"[build_agent_skills] Traceback: {traceback.format_exc()}")
            return None

    async def _run_one(skill_name: str, creator_func) -> Optional[Any]:
        result = await loop.run_in_executor(pool, _sync_build, skill_name, creator_func)
        # Update progress AFTER the executor returns so the counter reflects
        # actually-finished work. Counter mutation runs back on the loop
        # thread so no lock needed.
        done_counter["n"] += 1
        if result is not None:
            logger.debug(f"[build_agent_skills] ✅ Created {skill_name}")
        else:
            logger.warning(f"[build_agent_skills] ⚠️ {skill_name} returned None")
        _report_status(f"Loaded {done_counter['n']}/{total}: {skill_name}")
        return result

    tasks = [_run_one(name, fn) for name, fn in skill_creators]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if r is not None and not isinstance(r, Exception)]

async def build_agent_skills(mainwin, skill_path=""):
    """Build Agent Skills - supports local database + cloud data + local code triple data sources

    Data flow:
    1. Parallel loading: local database + cloud data
    2. Wait for both to complete, cloud data takes priority and overwrites local database
    3. Add locally built skills from code
    4. Merge all data and update mainwindow.agent_skills memory
    """
    try:
        logger.info("[build_agent_skills] Starting skill building with DB+Cloud+Local integration...")
        start_time = time.time()

        # Step 1: Start parallel loading from local database and cloud
        logger.info("[build_agent_skills] Step 1: Parallel loading DB and Cloud...")
        db_task = asyncio.create_task(_load_skills_from_database_async(mainwin))
        cloud_task = asyncio.create_task(_load_skills_from_cloud_async(mainwin))

        # Step 2: Wait for both database and cloud to complete (with timeout)
        logger.info("[build_agent_skills] Step 2: Waiting for DB and Cloud...")
        db_skills = []
        cloud_skills = []

        try:
            # Wait for database task
            db_skills = await asyncio.wait_for(db_task, timeout=3.0)
            logger.info(f"[build_agent_skills] ✅ Loaded {len(db_skills)} skills from database")
        except asyncio.TimeoutError:
            logger.warning("[build_agent_skills] ⏰ Database timeout")
        except Exception as e:
            logger.error(f"[build_agent_skills] ❌ Database failed: {e}")

        try:
            # Wait for cloud task
            cloud_skills = await asyncio.wait_for(cloud_task, timeout=5.0)
            logger.info(f"[build_agent_skills] ✅ Loaded {len(cloud_skills or [])} skills from cloud")
        except asyncio.TimeoutError:
            logger.warning("[build_agent_skills] ⏰ Cloud timeout")
        except Exception as e:
            logger.error(f"[build_agent_skills] ❌ Cloud failed: {e}")

        # Step 3: Merge DB + cloud skill rows, never let cloud wholesale replace local DB rows.
        # Cloud is useful for backfilling/updating records, but local DB may contain user-created
        # skills that haven't synced cleanly yet and must still remain editable/visible.
        final_db_skills = []
        if cloud_skills and len(cloud_skills) > 0:
            logger.info(f"[build_agent_skills] Step 3: Cloud data available, merging with database skills...")

            # Cloud data updates local database asynchronously (non-blocking), but in-memory build
            # must preserve existing local DB-only skills for this session.
            asyncio.create_task(_update_database_with_cloud_skills(cloud_skills, mainwin))
            logger.info(f"[build_agent_skills] 🔄 Database update started in background (non-blocking)")

            merged_rows = []
            seen_ids = set()
            seen_askids = set()
            seen_names = set()

            def _add_row(row):
                if not isinstance(row, dict):
                    return False
                row_id = str(row.get('id') or '').strip()
                row_askid = str(row.get('askid') or '').strip()
                row_name = str(row.get('name') or '').strip().lower()
                if (row_id and row_id in seen_ids) or (row_askid and row_askid in seen_askids) or (row_name and row_name in seen_names):
                    return False
                merged_rows.append(row)
                if row_id:
                    seen_ids.add(row_id)
                if row_askid:
                    seen_askids.add(row_askid)
                if row_name:
                    seen_names.add(row_name)
                return True

            # Prefer local DB rows first to preserve local metadata/source/editability.
            for row in db_skills or []:
                _add_row(row)
            for row in cloud_skills or []:
                _add_row(row)

            final_db_skills = merged_rows
            logger.info(f"[build_agent_skills] ✅ Merged DB+cloud skills: db={len(db_skills)}, cloud={len(cloud_skills)}, final={len(final_db_skills)}")
        else:
            logger.info(f"[build_agent_skills] Step 3: No cloud data, using database skills...")
            final_db_skills = db_skills

        # Step 4: Convert database skills to skill objects
        logger.info("[build_agent_skills] Step 4: Converting DB skills to objects...")
        logger.info(f"[build_agent_skills] DB skills to convert: {len(final_db_skills)}")

        # Pre-scan local skills to detect name conflicts with code skills
        # Code skills in resource/my_skills should take precedence over DB entries
        local_code_skill_names = set()
        try:
            local_code_skill_names = set(scan_resource_skills() or [])
            logger.info(f"[build_agent_skills] Local code skill names found: {local_code_skill_names}")
        except Exception:
            logger.debug("[build_agent_skills] Could not scan local code skills")

        memory_skills = []
        skipped_code_skill_conflicts = 0
        for i, db_skill in enumerate(final_db_skills):
            try:
                db_skill_name = db_skill.get('name', 'unknown')
                db_skill_source = db_skill.get('source', 'ui')

                # Validate: code skills should not be in database
                if db_skill_source == 'code':
                    logger.error(f"[build_agent_skills] ❌ Invalid: code skill '{db_skill_name}' found in database")
                    continue

                # Skip DB entries that have the same name as a local code skill.
                # Code skills are loaded from disk and are more authoritative.
                if db_skill_name in local_code_skill_names:
                    logger.info(f"[build_agent_skills] ⏭️ Skipping DB skill '{db_skill_name}' - same name exists in local code skills")
                    skipped_code_skill_conflicts += 1
                    continue

                logger.debug(f"[build_agent_skills] Converting DB skill {i+1}/{len(final_db_skills)}: {db_skill_name}")
                skill_obj = _convert_db_skill_to_object(db_skill)
                if skill_obj:
                    memory_skills.append(skill_obj)
                    logger.debug(f"[build_agent_skills] ✅ Successfully converted: {skill_obj.name}")
                else:
                    logger.warning(f"[build_agent_skills] ⚠️ Conversion returned None for: {db_skill_name}")
            except Exception as e:
                logger.error(f"[build_agent_skills] ❌ Failed to convert skill {db_skill.get('name', 'unknown')}: {e}")
                logger.error(f"[build_agent_skills] Traceback: {traceback.format_exc()}")

        logger.info(f"[build_agent_skills] ✅ Converted {len(memory_skills)} DB skills to objects (skipped {skipped_code_skill_conflicts} due to local code skill conflicts)")

        # Step 5: Build local code-based skills (built-in + resource/my_skills examples)
        # Pass DB skill names so appdata scan skips skills already loaded from DB
        db_skill_names = {getattr(sk, 'name', '') for sk in memory_skills if sk}
        logger.info("[build_agent_skills] Step 5: Building local code skills...")
        try:
            code_skills = await _build_local_skills_async(mainwin, skill_path, db_skill_names=db_skill_names)
            logger.info(f"[build_agent_skills] ✅ Built {len(code_skills or [])} code skills")
        except Exception as e:
            logger.error(f"[build_agent_skills] ❌ Local build failed: {e}")
            code_skills = []

        # Step 6: Merge all skill data (simplified)
        logger.info("[build_agent_skills] Step 6: Merging all skills...")
        
        # Design: Only 2 types of skills
        # 1. Database skills (UI-created): saved in DB, use DB ID
        # 2. Code skills: Built-in + resource/my_skills examples, use stable ID, source="code"
        
        # Merge DB skills and code skills by ID.
        # ID is globally unique — two skills with the same ID are the same skill.
        # - DB (memory_skills) is authoritative: loaded first, always kept.
        # - Disk (code_skills) supplements only: added only if their ID is not already present,
        #   so they never overwrite authoritative DB entries.
        # Same name with different IDs is legitimate and both entries are kept.
        skills_dict = {}

        for skill in memory_skills:
            if skill is not None and hasattr(skill, 'name'):
                skills_dict[skill.id] = skill

        for skill in code_skills:
            if skill is not None and hasattr(skill, 'name'):
                if skill.id in skills_dict:
                    # Same ID already in DB — DB is authoritative, skip disk duplicate
                    logger.debug(
                        f"[build_agent_skills] Skipping disk duplicate of id={skill.id} "
                        f"(DB entry already present)"
                    )
                    continue
                if not getattr(skill, 'source', None):
                    skill.source = SkillSource.CODE.value
                skills_dict[skill.id] = skill

        # Convert back to list
        all_skills = list(skills_dict.values())

        # Step 7: Update mainwindow.agent_skills memory
        logger.info("[build_agent_skills] Step 7: Updating mainwindow.agent_skills...")
        mainwin.agent_skills = all_skills

        # Log final results
        total_time = time.time() - start_time
        skill_names = [s.name for s in all_skills] if all_skills else []
        logger.info(f"[build_agent_skills] 🎉 Complete! Total: {len(all_skills)} skills in {total_time:.3f}s")
        logger.info(f"[build_agent_skills] - DB/Cloud skills: {len(memory_skills)}")
        logger.info(f"[build_agent_skills] - Code skills: {len(code_skills or [])}")
        logger.info(f"[build_agent_skills] - Skill names: {skill_names}")

        # ── Detect duplicate names (should not happen with correct id-based dedup) ──
        _log_duplicate_names(all_skills)

        return all_skills

    except Exception as e:
        logger.error(f"[build_agent_skills] Error: {e}")
        logger.error(f"[build_agent_skills] Traceback: {traceback.format_exc()}")
        return []


def _get_skill_service(mainwin):
    """Get skill service from mainwin - centralized helper to avoid code duplication"""
    if mainwin and hasattr(mainwin, 'ec_db_mgr'):
        return mainwin.ec_db_mgr.skill_service
    # Fallback
    logger.warning("[build_agent_skills] mainwin.ec_db_mgr not available, using fallback ECDBMgr")
    from agent.db import ECDBMgr
    return ECDBMgr().skill_service


def _get_username(mainwin):
    """Get username from mainwin - centralized helper"""
    if mainwin and hasattr(mainwin, 'user'):
        return mainwin.user
    return None


async def _load_skills_from_database_async(mainwin):
    """Asynchronously load skill data from local database"""
    try:
        logger.info("[build_agent_skills] Loading skills from database...")

        username = _get_username(mainwin)
        if not username:
            logger.error("[build_agent_skills] Cannot get username: mainwin or mainwin.user not available")
            return []
        
        logger.info(f"[build_agent_skills] Querying skills for user: {username}")
        skill_service = _get_skill_service(mainwin)

        skills_result = skill_service.get_skills_by_owner(username)
        if skills_result.get('success'):
            db_skills = skills_result.get('data', [])
            logger.info(f"[build_agent_skills] Found {len(db_skills)} skills in database for user: {username}")
            return db_skills
        else:
            logger.warning(f"[build_agent_skills] Failed to get skills from database: {skills_result.get('error')}")
            return []

    except Exception as e:
        logger.error(f"[build_agent_skills] Error loading from database: {e}")
        return []


def _load_mapping_rules_from_path(skill_path: str, skill_name: str = "Unknown") -> dict | None:
    """Load mapping rules from data_mapping.json based on skill path.
    
    Args:
        skill_path: Path to skill JSON file (e.g., .../diagram_dir/<name>_skill.json)
        skill_name: Skill name for logging
        
    Returns:
        Mapping rules dict or None if not found/failed
    """
    try:
        spath = (skill_path or "").strip()
        if not spath:
            return None
            
        p = Path(spath)
        # Expected: <skill_root>/diagram_dir/<name>_skill.json
        skill_root = p.parent.parent if p.parent.name == "diagram_dir" else p.parent
        mapping_file = skill_root / "data_mapping.json"
        
        if mapping_file.exists():
            with mapping_file.open("r", encoding="utf-8") as mf:
                mapping_rules = json.load(mf)
            logger.info(f"[build_agent_skills] Loaded mapping rules for {skill_name} from {mapping_file}")
            return mapping_rules
        return None
    except Exception as e:
        logger.warning(f"[build_agent_skills] Failed to load mapping rules for {skill_name}: {e}")
        return None


def _schema_name(schema) -> str:
    """Return the name of an MCP tool schema object or dict."""
    return getattr(schema, "name", "") if not isinstance(schema, dict) else schema.get("name", "")


def _build_compact_tool_schema_str(schemas: list) -> str:
    """Build the same compact JSON that _provide_tools_schema produces, but for a subset."""
    result = []
    for schema in schemas:
        name = _schema_name(schema)
        desc = getattr(schema, "description", "") if not isinstance(schema, dict) else schema.get("description", "")
        inp_schema = getattr(schema, "inputSchema", {}) if not isinstance(schema, dict) else schema.get("inputSchema", {})
        clean_desc = _re.sub(r"<[^>]+>", " ", desc).strip()
        clean_desc = _re.sub(r"\s{2,}", " ", clean_desc)
        props = (inp_schema or {}).get("properties", {})
        inner = props.get("input", {})
        if isinstance(inner, dict) and inner.get("properties"):
            params = list(inner["properties"].keys())
        else:
            params = [p for p in props if p != "input"]
        entry = {"name": name, "description": clean_desc}
        if params:
            entry["params"] = params
        result.append(entry)
    return json.dumps(result, indent=2, ensure_ascii=False)


def _inject_toolset_skillset_variables(skill_obj: "EC_Skill", core_dict: dict) -> None:
    """Pre-compute toolset/skillset schema strings and inject into skill mapping_rules.prompt_variables.

    toolset: named subset of MCP tools → resolves to compact JSON (same format as {{tools_schema}})
    skillset: named subset of agent skills → resolves to summary JSON (same format as {{skills_schema}})

    The variable name is the toolset/skillset name (e.g. {{browser_tools}}).
    These are injected at lowest priority so explicit prompt-level declarations override them.
    """
    toolsets = core_dict.get("toolsets") or []
    skillsets = core_dict.get("skillsets") or []
    if not toolsets and not skillsets:
        return

    extra_vars: dict = {}

    if toolsets:
        all_schemas = []
        try:
            from app_context import AppContext
            mw = AppContext.get_main_window()
            if mw:
                all_schemas = getattr(mw, "mcp_tools_schemas", None) or []
        except Exception:
            pass
        if not all_schemas:
            try:
                from agent.mcp.server.tool_schemas import get_tool_schemas
                all_schemas = get_tool_schemas() or []
            except Exception:
                pass

        for ts in toolsets:
            name = (ts.get("name") or "").strip()
            if not name:
                continue
            tool_names = set(ts.get("toolNames") or [])
            selected = [s for s in all_schemas if _schema_name(s) in tool_names] if tool_names else []
            schema_str = _build_compact_tool_schema_str(selected) if selected else "[]"
            extra_vars[name] = {"source": "static", "value": schema_str}
            logger.debug(f"[build_agent_skills] Toolset '{name}': {len(selected)}/{len(tool_names)} tools matched")

    if skillsets:
        all_skills: list = []
        try:
            from app_context import AppContext
            mw = AppContext.get_main_window()
            if mw:
                all_skills = getattr(mw, "agent_skills", None) or []
        except Exception:
            pass

        for ss in skillsets:
            name = (ss.get("name") or "").strip()
            if not name:
                continue
            skill_ids = set(str(i) for i in (ss.get("skillIds") or []))
            selected = [sk for sk in all_skills if str(getattr(sk, "id", "")) in skill_ids] if skill_ids else []
            summaries = [
                {
                    "name": _re.sub(r"[\s_]+", "-", (getattr(sk, "name", "") or "unnamed").lower().strip()),
                    "description": (getattr(sk, "description", "") or "")[:1024],
                    "id": getattr(sk, "id", ""),
                }
                for sk in selected
            ]
            schema_str = json.dumps(summaries, indent=2, ensure_ascii=False)
            extra_vars[name] = {"source": "static", "value": schema_str}
            logger.debug(f"[build_agent_skills] Skillset '{name}': {len(selected)}/{len(skill_ids)} skills matched")

    if not extra_vars:
        return

    # Ensure mapping_rules["prompt_variables"] exists
    if not isinstance(skill_obj.mapping_rules, dict):
        skill_obj.mapping_rules = {}
    pv = skill_obj.mapping_rules.get("prompt_variables")
    if not isinstance(pv, dict):
        pv = {}
        skill_obj.mapping_rules["prompt_variables"] = pv

    # Inject only keys not already declared (toolset/skillset vars are lowest-priority)
    for k, v in extra_vars.items():
        if k not in pv:
            pv[k] = v

    logger.info(f"[build_agent_skills] Injected {len(extra_vars)} toolset/skillset variables for '{skill_obj.name}'")


def _load_diagram_from_path(skill_path: str, skill_name: str = "Unknown") -> dict | None:
    """Load diagram from skill JSON file.

    Args:
        skill_path: Path to skill JSON file
        skill_name: Skill name for logging
        
    Returns:
        Diagram dict or None if not found/failed
    """
    try:
        spath = (skill_path or "").strip()
        if not spath:
            return None
            
        p = Path(spath)
        if not (p.exists() and p.is_file() and p.suffix.lower() == ".json"):
            return None
            
        with p.open("r", encoding="utf-8") as f:
            file_obj = json.load(f)
            
        if not isinstance(file_obj, dict):
            return None
            
        # Try 'diagram' field first, then 'workFlow' for compatibility
        diagram = None
        if isinstance(file_obj.get("diagram"), dict) and file_obj.get("diagram"):
            diagram = file_obj.get("diagram")
        elif isinstance(file_obj.get("workFlow"), dict) and file_obj.get("workFlow"):
            diagram = file_obj.get("workFlow")
            
        if diagram:
            logger.info(f"[build_agent_skills] Loaded diagram for {skill_name} from {p}")
        return diagram
    except Exception as e:
        logger.warning(f"[build_agent_skills] Failed to load diagram for {skill_name}: {e}")
        return None


def _fill_skill_from_db_view(skill_obj: EC_Skill, v: DBAgentSkill) -> None:
    skill_obj.id = v.str('id', str(uuid.uuid4()))
    skill_obj.askid = v.int('askid', 0)
    skill_obj.name = v.str('name', 'Unknown Skill')
    skill_obj.description = v.str('description', '')
    skill_obj.version = v.str('version', '1.0.0')
    skill_obj.owner = v.str('owner', '')
    skill_obj.config = v.dict('config', {})
    skill_obj.level = v.str('level', 'entry')
    skill_obj.path = v.str('path', '')

    skill_obj.tags = v.list('tags', skill_obj.tags or [])
    skill_obj.examples = v.list('examples', skill_obj.examples or [])
    skill_obj.inputModes = v.list('inputModes', skill_obj.inputModes or [])
    skill_obj.outputModes = v.list('outputModes', skill_obj.outputModes or [])
    skill_obj.apps = v.json('apps', getattr(skill_obj, 'apps', None))
    skill_obj.limitations = v.json('limitations', getattr(skill_obj, 'limitations', None))
    skill_obj.price = v.int('price', getattr(skill_obj, 'price', 0) or 0)
    skill_obj.price_model = v.str('price_model', getattr(skill_obj, 'price_model', '') or '')
    skill_obj.public = v.bool('public', getattr(skill_obj, 'public', False) or False)
    skill_obj.rentable = v.bool('rentable', getattr(skill_obj, 'rentable', False) or False)
    skill_obj.ui_info = v.dict('ui_info', getattr(skill_obj, 'ui_info', {}) or {})
    skill_obj.objectives = v.list('objectives', getattr(skill_obj, 'objectives', []) or [])
    skill_obj.need_inputs = v.list('need_inputs', getattr(skill_obj, 'need_inputs', []) or [])
    
    # Cloud execution settings are stored in config dict
    config = skill_obj.config or {}
    skill_obj.run_in_cloud = bool(config.get('run_in_cloud', False))
    skill_obj.hybrid_cloud_mode = bool(config.get('hybrid_cloud_mode', False))
    skill_obj.local_helper_skill_id = config.get('local_helper_skill_id', None)
    skill_obj.local_helper_machine = config.get('local_helper_machine', None)

    # skill_owner tracks the original author (for prompt resolution on rented skills)
    skill_obj.skill_owner = v.str('skill_owner', '') or v.str('owner', '')
    skill_obj.cloud_id = v.str('cloud_id', '') or ''

    # run_mode: developing / released — stored in config or top-level
    config = skill_obj.config or {}
    skill_obj.run_mode = config.get('run_mode') or config.get('mode') or v.str('run_mode', 'developing')
    skill_obj.mapping_rules = config.get('mapping_rules') or skill_obj.mapping_rules or {}

    # status: active / inactive / deleted — stored in config or top-level
    skill_obj.status = config.get('status') or v.str('status', 'active')


def _resolve_code_file_paths(skill_dict: dict | None, skill_path: str | None = None) -> dict | None:
    """
    Replace file path references in code nodes with actual file contents.
    
    This allows code nodes to reference Python files (e.g., "send_a2a_response.py")
    instead of having inline code strings. The referenced files should be located
    in the skill's code_dir/ directory.
    
    Args:
        skill_dict: The skill JSON dict
        skill_path: Optional path to the skill JSON file (used to resolve relative paths)
    
    Returns:
        Modified skill_dict with file paths replaced by contents
    """
    if not isinstance(skill_dict, dict):
        return skill_dict
    
    import os
    
    # Determine skill name and code_dir path
    skill_name = skill_dict.get("skillName") or skill_dict.get("skill_name", "unknown")
    code_dir = None
    
    if skill_path:
        # Try to derive code_dir from the skill JSON file path
        try:
            skill_json_path = Path(skill_path)
            skill_dir = skill_json_path.parent.parent  # diagram_dir -> skill_dir
            code_dir = skill_dir / "code_dir"
        except Exception:
            pass
    
    if not code_dir or not code_dir.exists():
        # Use unified skill directory resolution from extern_skills
        from agent.ec_skills.extern_skills.extern_skills import resolve_skill_code_dir
        code_dir = resolve_skill_code_dir(skill_name)
    
    def resolve_file_content(content: str) -> str:
        """If content looks like a file path, try to read the file."""
        if not isinstance(content, str):
            return content
        
        # Check if it looks like a file path reference (ends with .py)
        if not content.endswith('.py'):
            return content
        
        # Try absolute path first
        if os.path.exists(content):
            try:
                with open(content, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception:
                pass
        
        # Try relative to code_dir
        if code_dir and code_dir.exists():
            file_path = code_dir / content
            if file_path.exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        return f.read()
                except Exception:
                    pass
        
        # Return original if not found
        return content
    
    def process_node(node: dict) -> None:
        """Recursively process a node's config to replace file paths."""
        if not isinstance(node, dict):
            return
        
        # Handle both formats:
        # 1. inputsValues.code.content
        # 2. inputsValues -> { code: { type: "code", content: "..." } }
        
        inputs_values = node.get("inputsValues", {})
        if isinstance(inputs_values, dict):
            code_config = inputs_values.get("code", {})
            if isinstance(code_config, dict):
                content = code_config.get("content")
                if isinstance(content, str) and content.endswith('.py'):
                    resolved = resolve_file_content(content)
                    code_config["content"] = resolved
            elif isinstance(code_config, str) and code_config.endswith('.py'):
                # Direct string content (shouldn't happen but handle it)
                inputs_values["code"] = {
                    "type": "template",
                    "content": resolve_file_content(code_config)
                }
        
        # Also handle legacy format: node.data.inputsValues
        data = node.get("data", {})
        if isinstance(data, dict):
            inputs_values = data.get("inputsValues", {})
            if isinstance(inputs_values, dict):
                code_config = inputs_values.get("code", {})
                if isinstance(code_config, dict):
                    content = code_config.get("content")
                    if isinstance(content, str) and content.endswith('.py'):
                        resolved = resolve_file_content(content)
                        code_config["content"] = resolved
    
    # Process nodes in workFlow
    workflow = skill_dict.get("workFlow", {})
    if isinstance(workflow, dict):
        nodes = workflow.get("nodes", [])
        if isinstance(nodes, list):
            for node in nodes:
                process_node(node)
    
    # Also check diagram.nodes (alternative location)
    diagram = skill_dict.get("diagram", {})
    if isinstance(diagram, dict):
        nodes = diagram.get("nodes", [])
        if isinstance(nodes, list):
            for node in nodes:
                process_node(node)
    
    # Process nodes at root level (for flat structure)
    nodes = skill_dict.get("nodes", [])
    if isinstance(nodes, list):
        for node in nodes:
            process_node(node)
    
    return skill_dict


def _load_core_and_bundle_for_skill_path(skill_path: str) -> tuple[dict | None, dict | None]:
    """Load (core_dict, bundle_dict) from skill json path.

    - core_dict: <name>_skill.json
    - bundle_dict: <name>_skill_bundle.json (optional, same folder)
    """
    try:
        spath = (skill_path or "").strip()
        if not spath:
            return None, None

        core_path = Path(spath)
        if not (core_path.exists() and core_path.is_file() and core_path.suffix.lower() == ".json"):
            return None, None

        with core_path.open("r", encoding="utf-8") as f:
            core_dict = json.load(f)
        if not isinstance(core_dict, dict):
            core_dict = None
        else:
            # Resolve file path references in code nodes
            core_dict = _resolve_code_file_paths(core_dict, skill_path)

        bundle_dict = None
        try:
            bundle_path = core_path.with_name(f"{core_path.stem}_bundle.json")
            if bundle_path.exists():
                with bundle_path.open("r", encoding="utf-8") as bf:
                    bundle_dict = json.load(bf)
                if not isinstance(bundle_dict, dict):
                    bundle_dict = None
                else:
                    # Resolve file path references in bundle dict too
                    bundle_dict = _resolve_code_file_paths(bundle_dict, skill_path)
        except Exception:
            bundle_dict = None

        return core_dict, bundle_dict
    except Exception:
        return None, None


def _extract_workflow_from_core_dict(skill_name: str, core_dict: dict | None) -> tuple[dict | None, dict | None]:
    """Extract (flow_for_convert, diagram) from file-loaded core_dict."""
    if not (isinstance(core_dict, dict) and core_dict):
        return None, None

    wf = core_dict.get("workFlow")
    if isinstance(wf, dict) and wf:
        return core_dict, wf

    d0 = core_dict.get("diagram")
    if isinstance(d0, dict) and d0:
        wf2 = d0.get("workFlow")
        if isinstance(wf2, dict) and wf2:
            return core_dict, wf2
        if isinstance(d0.get("nodes"), list) and isinstance(d0.get("edges"), list):
            return core_dict, d0

    if isinstance(core_dict.get("nodes"), list) and isinstance(core_dict.get("edges"), list):
        return {"skillName": skill_name, "workFlow": core_dict}, core_dict

    return None, None


def _compile_skill_workflow_from_flow(
    *,
    skill_obj: EC_Skill,
    flow_for_convert: dict,
    bundle_dict: dict | None,
) -> None:
    """Compile workflow via `flowgram2langgraph_v2` and set `skill_obj.runnable`.

    - `flow_for_convert` should be the file-loaded outer shell when available.
    - `bundle_dict` is optional.
    """
    logger.debug(f"[build_agent_skills] Rebuilding workflow for skill: {skill_obj.name}")
    wf_obj = flow_for_convert.get("workFlow") if isinstance(flow_for_convert.get("workFlow"), dict) else {}
    logger.debug(
        f"[build_agent_skills] Rebuilding workflow diagram: nodes={len(wf_obj.get('nodes') or [])}, edges={len(wf_obj.get('edges') or [])}"
    )

    bp_mgr = BreakpointManager()
    workflow, bp_list = flowgram2langgraph_v2(flow_for_convert, bundle_json=bundle_dict, enable_subgraph=False, bp_mgr=bp_mgr)
    try:
        if isinstance(bp_list, (list, tuple)):
            bp_mgr.set_breakpoints(list(bp_list))
    except Exception:
        pass

    if workflow:
        skill_obj.set_work_flow(workflow)
        logger.info(f"[build_agent_skills] ✅ Successfully compiled workflow for: {skill_obj.name}")
    else:
        logger.warning(f"[build_agent_skills] ⚠️ Failed to convert diagram to workflow for: {skill_obj.name}")


def _convert_db_skill_to_object(db_skill):
    """Convert database skill data to skill object with compiled workflow.

    IMPORTANT: If the local file exists at skill_obj.path, always prefer it over
    DB content. This ensures direct file edits take effect without requiring a
    DB sync. Only fall back to DB content when the file is missing (e.g. cloud-
    deployed machine with no local copy).
    """
    try:
        skill_obj = EC_Skill()
        v = DBAgentSkill.view(db_skill)

        _fill_skill_from_db_view(skill_obj, v)

        logger.debug(f"[build_agent_skills] 🔄 Converting DB skill to object: '{skill_obj.name}', path={skill_obj.path}")

        # ── ALWAYS use local file if it exists ─────────────────────────────────
        # This ensures that any changes made in the Skill Editor are immediately
        # reflected when the skill is executed, without requiring an app restart.
        # The database is treated as metadata storage only (id, name, path, config).
        # ─────────────────────────────────────────────────────────────────────────
        skill_path = (skill_obj.path or "").strip()
        skill_id = skill_obj.id
        
        # Try the DB path first
        loaded_from_file = False
        if skill_path:
            core_path = Path(skill_path)
            if core_path.exists() and core_path.is_file():
                # Always reload from local file - this is the source of truth
                _skill_root = core_path.parent.parent if core_path.parent.name == "diagram_dir" else core_path.parent
                local_sk = load_skill_from_folder(_skill_root, mainwin=None)
                if local_sk and hasattr(local_sk, 'name') and local_sk.runnable:
                    # Verify the loaded skill has the correct ID or name to avoid loading wrong file
                    # This handles cases where a skill file was renamed but DB still has old path
                    local_sk_id = getattr(local_sk, 'id', '') or ''
                    local_sk_name = getattr(local_sk, 'name', '') or ''
                    expected_name = skill_obj.name or ''
                    
                    # Check if this is the correct skill (by ID or by name)
                    id_match = (local_sk_id == skill_id) if skill_id else False
                    name_match = (local_sk_name.lower().strip() == expected_name.lower().strip()) if expected_name else False
                    
                    if id_match or name_match:
                        # Preserve the canonical DB id
                        local_sk.id = skill_obj.id
                        logger.info(
                            f"[build_agent_skills] 📁 Loaded '{skill_obj.name}' from local file "
                            f"(id_match={id_match}, name_match={name_match})"
                        )
                        loaded_from_file = True
                        return local_sk
                    else:
                        # File exists but contains wrong skill — this is an ERROR, not a fallback scenario.
                        # The file path in DB is incorrect or the file was replaced/corrupted.
                        # Do NOT silently fallback to DB — report the error.
                        logger.error(
                            f"[build_agent_skills] ❌ Local file at '{skill_path}' contains wrong skill: "
                            f"expected '{expected_name}' (id={skill_id}), "
                            f"got '{local_sk_name}' (id={local_sk_id})"
                        )
                        # Fallback to DB only when file genuinely does not exist
                        skill_path = None  # Clear path so we skip file-based loading entirely
                else:
                    # local_sk is None, missing 'name', or runnable is None
                    # This indicates a genuine skill loading failure - not a path issue
                    # Log the issue but don't add additional fallback here since load_skill_from_folder
                    # now correctly handles invalid code_dir by trying diagram_dir
                    logger.warning(
                        f"[build_agent_skills] ⚠️ Local file exists for '{skill_obj.name}' "
                        f"but load failed or has no runnable (local_sk={local_sk is not None}, "
                        f"name={'yes' if local_sk and hasattr(local_sk, 'name') else 'no'}, "
                        f"runnable={'yes' if local_sk and getattr(local_sk, 'runnable', None) else 'no'}). "
                        f"Will fall through to DB fallback below."
                    )
                    # Clear path to fall through to DB fallback
                    skill_path = None
            else:
                logger.debug(f"[build_agent_skills] No local file at {skill_path}")
        
        # ── End local-file-first ──────────────────────────────────────────────

        # Only fallback to DB when file genuinely doesn't exist (skill_path is empty/None).
        # If file exists but is wrong, we already logged the error above.
        if not skill_path:
            logger.error(f"[build_agent_skills] ❌ Failed to load skill '{skill_obj.name}' (id={skill_id}): "
                         f"local file not found. Cannot fallback to DB — skill_path is empty.")
            # Still return skill_obj so the caller has something to work with
            # but it won't have a runnable workflow

        # Load mapping rules from data_mapping.json
        mapping_rules = _load_mapping_rules_from_path(skill_obj.path, skill_obj.name)
        if mapping_rules:
            skill_obj.mapping_rules = mapping_rules

        core_dict, bundle_dict = _load_core_and_bundle_for_skill_path(skill_obj.path)

        # IMPORTANT: DB diagram is a fallback source.
        # Preferred source-of-truth for workflow is the on-disk JSON pointed by skill_obj.path.
        # Only when we cannot extract workflow from file, we fall back to db_skill['diagram'].
        # If we later enforce "file-only" workflows, we can remove the DB fallback block below.
        flow_for_convert, diagram = _extract_workflow_from_core_dict(skill_obj.name, core_dict)
        if flow_for_convert is None:
            logger.warning(f"[build_agent_skills] ⚠️ No workflow from file for '{skill_obj.name}', trying DB diagram fallback")
            raw_db_diagram = (db_skill or {}).get("diagram")
            if isinstance(raw_db_diagram, dict) and raw_db_diagram:
                wf = raw_db_diagram.get("workFlow")
                if isinstance(wf, dict) and wf:
                    flow_for_convert, diagram = raw_db_diagram, wf
                    logger.warning(f"[build_agent_skills] 📋 Using DB diagram for '{skill_obj.name}'")
                else:
                    flow_for_convert, diagram = {"skillName": skill_obj.name, "workFlow": raw_db_diagram}, raw_db_diagram
                    logger.warning(f"[build_agent_skills] 📋 Using DB diagram (alt format) for '{skill_obj.name}'")
        else:
            logger.debug(f"[build_agent_skills] 📁 Using file-based workflow for '{skill_obj.name}'")

        if diagram:
            skill_obj.diagram = diagram

        if flow_for_convert and isinstance(flow_for_convert, dict):
            try:
                _compile_skill_workflow_from_flow(
                    skill_obj=skill_obj,
                    flow_for_convert=flow_for_convert,
                    bundle_dict=bundle_dict,
                )
            except Exception as e:
                logger.error(f"[build_agent_skills] ❌ Error rebuilding workflow for {skill_obj.name}: {e}")
                logger.error(f"[build_agent_skills] Traceback: {traceback.format_exc()}")
            # Inject toolset/skillset variables from flowgram JSON
            try:
                _inject_toolset_skillset_variables(skill_obj, flow_for_convert)
            except Exception as _tse:
                logger.debug(f"[build_agent_skills] Toolset/skillset injection skipped for '{skill_obj.name}': {_tse}")
        else:
            logger.info(f"[build_agent_skills] No diagram data for skill '{skill_obj.name}' (pre-diagram version)")

        logger.info(f"[build_agent_skills] ✅ Converted DB skill: '{skill_obj.name}' (runnable: {skill_obj.runnable})")
        return skill_obj

    except Exception as e:
        logger.error(f"[build_agent_skills] Error converting DB skill: {e}")
        logger.error(f"[build_agent_skills] Traceback: {traceback.format_exc()}")
        return None

async def _update_database_with_cloud_skills(cloud_skills, mainwin):
    """Update local database with cloud skill data"""
    try:
        logger.info(f"[build_agent_skills] Updating database with {len(cloud_skills)} cloud skills...")

        username = _get_username(mainwin)
        if not username:
            logger.error("[build_agent_skills] Cannot get username: mainwin or mainwin.user not available")
            return

        skill_service = _get_skill_service(mainwin)
        updated_count = 0
        for cloud_skill in cloud_skills:
            try:
                # Convert cloud skill object to database format
                skill_data = {
                    'id': getattr(cloud_skill, 'id', f'cloud_skill_{updated_count}'),
                    'name': getattr(cloud_skill, 'name', 'Cloud Skill'),
                    'owner': username,
                    'description': getattr(cloud_skill, 'description', ''),
                    'version': getattr(cloud_skill, 'version', '1.0.0'),
                    'config': getattr(cloud_skill, 'config', {}),
                    'tags': getattr(cloud_skill, 'tags', []),
                    'public': getattr(cloud_skill, 'public', False),
                    'rentable': getattr(cloud_skill, 'rentable', False),
                    'price': getattr(cloud_skill, 'price', 0),
                }

                # Check if already exists
                existing = skill_service.get_skill_by_id(skill_data['id'])
                if existing.get('success') and existing.get('data'):
                    # Update existing skill
                    result = skill_service.update_skill(skill_data['id'], skill_data)
                else:
                    # Add new skill
                    result = skill_service.add_skill(skill_data)

                if result.get('success'):
                    updated_count += 1
                    logger.debug(f"[build_agent_skills] Updated DB with cloud skill: {skill_data['name']}")
                else:
                    logger.warning(f"[build_agent_skills] Failed to update DB with skill {skill_data['name']}: {result.get('error')}")

            except Exception as e:
                logger.error(f"[build_agent_skills] Error updating skill in DB: {e}")

        logger.info(f"[build_agent_skills] Successfully updated {updated_count}/{len(cloud_skills)} skills in database")

    except Exception as e:
        logger.error(f"[build_agent_skills] Error updating database with cloud skills: {e}")

async def _load_skills_from_cloud_async(mainwin):
    """Asynchronously load cloud skills (timeout controlled externally)"""
    try:
        logger.info("[build_agent_skills] 🌐 Loading skills from cloud...")

        # Execute synchronous cloud loading function in thread pool
        cloud_skills = await asyncio.get_event_loop().run_in_executor(
            None, load_agent_skills_from_cloud, mainwin
        )

        if cloud_skills:
            logger.info(f"[build_agent_skills] 🌐 Cloud returned {len(cloud_skills)} skills")
        else:
            logger.info("[build_agent_skills] 🌐 Cloud returned no skills")

        return cloud_skills or []

    except Exception as e:
        logger.error(f"[_load_skills_from_cloud_async] Error: {e}")
        return []


async def _build_local_skills_async(mainwin, skill_path="", db_skill_names: set = None):
    """Build local skills asynchronously
    
    Returns:
        List[EC_Skill]: Code-based skills (built-in + resource/my_skills examples)
    """
    try:
        logger.info("[_build_local_skills_async] Building local skills...")
        
        # Build all code-based skills (built-in + resource/my_skills examples)
        code_skills = await build_agent_skills_parallel(mainwin, db_skill_names=db_skill_names)
        logger.info(f"[_build_local_skills_async] Built {len(code_skills)} code skills")
        
        return code_skills
        
    except Exception as e:
        logger.error(f"[_build_local_skills_async] Error: {e}")
        logger.error(f"[_build_local_skills_async] Traceback: {traceback.format_exc()}")
        return []


def load_skill_from_folder(skill_folder_path: Path, mainwin=None) -> Optional[EC_Skill]:
    """Load a single skill from a skill folder.
    
    Simplified utility function to load one skill from a folder path.
    Replaces the old build_agent_skills_from_files scanning logic.
    
    Args:
        skill_folder_path: Path to <name>_skill folder
        mainwin: Optional main window reference
    
    Returns:
        EC_Skill object or None if loading fails
    
    Directory structure:
        <name>_skill/
        ├─ code_skill/ | code_dir/   # Python implementation
        └─ diagram_dir/              # JSON diagram files
    
    Pick strategy:
    - If only one exists, load from there
    - If both exist, pick the one with most recent modification time
    """
    try:
        if isinstance(skill_folder_path, str):
            skill_folder_path = Path(skill_folder_path)
        
        if not skill_folder_path.exists() or not skill_folder_path.is_dir():
            logger.error(f"[load_skill_from_folder] Invalid path: {skill_folder_path}")
            return None
        
        skill_root = skill_folder_path
        logger.debug(f"[load_skill_from_folder] Loading from {skill_root}")
        
        def load_mapping_rules(sk: EC_Skill, skill_root: Path) -> None:
            """Load mapping rules from data_mapping.json at skill root level."""
            mapping_file = skill_root / "data_mapping.json"
            if mapping_file.exists():
                try:
                    with mapping_file.open("r", encoding="utf-8") as mf:
                        sk.mapping_rules = json.load(mf)
                        logger.info(f"[build_agent_skills] Loaded mapping rules for {sk.name} from {mapping_file}")
                except Exception as e:
                    logger.warning(f"[build_agent_skills] Failed to load mapping rules from {mapping_file}: {e}")

        owner_username = _get_username(mainwin) or ""

        def _apply_owner(sk: EC_Skill) -> None:
            try:
                if owner_username and not getattr(sk, "owner", ""):
                    sk.owner = owner_username
                if owner_username and not getattr(sk, "skill_owner", ""):
                    sk.skill_owner = owner_username
            except Exception:
                pass

        def finalize_skill(sk: EC_Skill, source: str, path: str, skill_root: Path) -> EC_Skill:
            """Common finalization: set source, path, and load mapping rules
            
            Note: ID is automatically generated by EC_Skill.__init__ and model_post_init.
            No need to manually regenerate it here.
            """
            sk.source = source
            norm_path = path.replace('\\', '/')
            is_code_dir = '/code_dir' in norm_path
            is_code_skill_dir = '/code_skill' in norm_path

            if is_code_dir:
                sk.path = None
            elif is_code_skill_dir:
                diagram_path = skill_root / 'diagram_dir' / f"{skill_root.name}.json"
                sk.path = str(diagram_path) if diagram_path.exists() else None
            else:
                sk.path = path
            # ID will be automatically regenerated by model_post_init when source changes
            _apply_owner(sk)
            load_mapping_rules(sk, skill_root)
            log_path = sk.path or 'None (code_only)'
            logger.debug(f"[build_agent_skills] Finalized skill: {sk.name} (source={source}, path={log_path})")
            return sk

        def find_package_dir_in_code(code_dir: Path) -> Optional[Tuple[Path, Optional[str], str]]:
            """
            Locate a Python module for the skill inside code_dir and return where/how to import it.
            Rules:
            - Prefer any '*_skill.py' directly under code_dir (flat layout). In this case, return (code_dir, None, module_base)
            - Otherwise, look for a package dir (immediate child directory) that contains '*_skill.py'. Return (pkg_dir, pkg_name, module_base)
            """
            if not code_dir.exists():
                return None
            # 1) Flat layout: files directly under code_dir
            direct_candidates = sorted([p for p in code_dir.glob("*_skill.py")])
            if direct_candidates:
                return code_dir, None, direct_candidates[0].stem

            # 2) Package layout: child directory containing *_skill.py
            for child in code_dir.iterdir():
                if not child.is_dir():
                    continue
                # Prefer specific '*_skill.py' modules; fallback to 'abc_skill.py' for backward compat
                candidates = sorted([p for p in child.glob("*_skill.py")])
                if not candidates:
                    abc = child / "abc_skill.py"
                    if abc.exists():
                        candidates = [abc]
                if candidates:
                    mod_base = candidates[0].stem  # filename without .py
                    return child, child.name, mod_base
            return None

        def load_from_code(skill_root: Path, code_dir: Path) -> Optional[EC_Skill]:
            """
            Dynamically load a skill from code directory.
            
            ⚠️ IMPORTANT: This is for EXTERNAL/PLUGIN skills only!
            
            Current Usage:
            --------------
            - NOT used for built-in skills (they use build_agent_skills_parallel)
            - Only used for user-defined skills in ec_skills/ directory
            - Requires skill to have a build_skill() function
            
            How It Works:
            -------------
            1. Scans code_dir for *_skill.py files
            2. Dynamically imports the module
            3. Calls build_skill() function (standard interface)
            4. Returns the created EC_Skill object
            
            See: agent/ec_skills/skill_build_template.py for build_skill() template
            """
            logger.debug(f"[build_agent_skills] Loading from code: {skill_root} / {code_dir}")
            pkg = find_package_dir_in_code(code_dir)
            if not pkg:
                logger.warning(f"[build_agent_skills] No package with *_skill.py under {code_dir}")
                return None
            pkg_dir, pkg_name, module_base = pkg

            # prepare venv under skill root
            ensure_skill_venv(skill_root, reuse_host_libs=True)
            venv_dir = skill_root / ".venv"

            # import in-process
            from contextlib import ExitStack
            import importlib

            with ExitStack() as stack:
                # For flat layout (pkg_name is None), we need to treat code_dir as a package
                # to support relative imports like "from .helpers import ..."
                if pkg_name:
                    # Package layout: add pkg_dir's parent to sys.path
                    stack.enter_context(temp_sys_path([pkg_dir]))
                    stack.enter_context(temp_sys_path(_site_packages(venv_dir)))
                    mod = importlib.import_module(f"{pkg_name}.{module_base}")
                else:
                    # Flat layout: treat code_dir as a package
                    # Add code_dir's parent to sys.path so code_dir becomes importable as a package
                    stack.enter_context(temp_sys_path([pkg_dir.parent]))
                    stack.enter_context(temp_sys_path(_site_packages(venv_dir)))
                    # Use code_dir's name as the package name
                    flat_pkg_name = pkg_dir.name  # e.g., "code_dir"
                    mod = importlib.import_module(f"{flat_pkg_name}.{module_base}")
                if not hasattr(mod, "build_skill"):
                    where = f"{pkg_name}.{module_base}" if pkg_name else module_base
                    logger.error(f"[build_agent_skills] {where} missing build_skill()")
                    return None
                # Build using run_context if supported; remain backward compatible with (mainwin)
                build_fn = getattr(mod, "build_skill")
                logger.debug(f"[build_agent_skills] Found build_skill() in {module_base} (dynamic loading)")
                ctx = None
                try:
                    ctx = AppContext.get_useful_context()
                except Exception:
                    ctx = None

                try:
                    sig = inspect.signature(build_fn)
                    params = sig.parameters
                    if "run_context" in params and "mainwin" in params:
                        logger.debug("[build_agent_skills] Calling build_skill(run_context, mainwin)")
                        built = build_fn(run_context=ctx, mainwin=mainwin)
                    elif "run_context" in params:
                        logger.debug("[build_agent_skills] Calling build_skill(run_context)")
                        built = build_fn(run_context=ctx)
                    elif "mainwin" in params:
                        logger.debug("[build_agent_skills] Calling build_skill(mainwin)")
                        built = build_fn(mainwin)
                    else:
                        logger.debug("[build_agent_skills] Calling build_skill()")
                        built = build_fn()
                except Exception as e:
                    logger.warning(f"[build_agent_skills] build_skill signature fallback due to: {e}")
                    # Last resort: try legacy positional mainwin
                    try:
                        built = build_fn(mainwin)
                    except Exception:
                        built = build_fn()

                logger.debug(f"[build_agent_skills] Skill built: {type(built)}")
                # Accept either EC_Skill or (dto, stategraph)
                sk = None
                if isinstance(built, EC_Skill):
                    logger.debug("[build_agent_skills] Built object is EC_Skill")
                    sk = built
                elif isinstance(built, tuple) and len(built) == 2:
                    dto, sg = built
                    try:
                        sk = EC_Skill()
                        sk.name = getattr(dto, "name", pkg_name)
                        sk.description = getattr(dto, "description", "")
                        sk.config = getattr(dto, "config", {}) or {}
                        sk.set_work_flow(sg)
                        logger.debug(f"Just built skill from code: {sk.name}")
                    except Exception as e:
                        logger.error(f"[build_agent_skills] Failed to wrap tuple into EC_Skill: {e}")
                        return None
                else:
                    logger.error("[build_agent_skills] build_skill() returned unsupported type")
                    return None

                if sk:
                    # User-created code skills in my_skills/ are editable (source="ui")
                    # Only built-in code skills (from build_local_code_skills) are read-only (source="code")
                    return finalize_skill(sk, "ui", str(code_dir), skill_root)
                return None

        def _build_from_payload(
            core_dict: dict,
            bundle_dict: Optional[dict],
            mapping_rules: Optional[dict],
            core_path: Path,
            name: str,
            skill_root: Path,
        ) -> Optional[EC_Skill]:
            """Construct the EC_Skill from already-parsed inputs.

            Shared between the cold (read files + parse) and warm
            (skill_cache hit) paths. Heavy work — flowgram2langgraph_v2 +
            CompiledStateGraph compile + Pydantic — still runs here.
            """
            bp_mgr = BreakpointManager()
            workflow, _breakpoints = flowgram2langgraph_v2(
                core_dict, bundle_json=bundle_dict, enable_subgraph=False, bp_mgr=bp_mgr
            )
            try:
                if isinstance(_breakpoints, (list, tuple)):
                    bp_mgr.set_breakpoints(list(_breakpoints))
            except Exception:
                pass
            if not workflow:
                logger.warning(f"[build_agent_skills] flowgram2langgraph returned empty workflow for {core_path}")
                return None

            sk = _create_skill_from_workflow(
                core_dict=core_dict,
                workflow=workflow,
                skill_name=name,
                json_path=core_path,
                source="ui",
            )
            if not sk:
                return None

            _apply_owner(sk)
            if mapping_rules is not None:
                try:
                    sk.mapping_rules = mapping_rules
                except Exception:
                    pass
            else:
                load_mapping_rules(sk, skill_root)
            try:
                _inject_toolset_skillset_variables(sk, core_dict)
            except Exception as _tse:
                logger.debug(f"[build_agent_skills] Toolset/skillset injection skipped for '{sk.name}': {_tse}")
            return sk

        def load_from_diagram(diagram_dir: Path) -> Optional[EC_Skill]:
            # Expect files <name>_skill.json and optional <name>_skill_bundle.json under diagram_dir
            try:
                skill_root = diagram_dir.parent
                base = skill_root.name
                name = base[:-6] if base.endswith("_skill") else base

                # Phase A1: skip filesystem walk + JSON parse + mapping read
                # on a content-hash hit. Heavy LangGraph build still runs.
                try:
                    from agent.ec_skills import skill_cache as _skill_cache
                    cached = _skill_cache.load(skill_root)
                except Exception as _ce:
                    logger.debug(f"[build_agent_skills] skill_cache lookup error for {name}: {_ce}")
                    cached = None
                if cached is not None:
                    return _build_from_payload(
                        core_dict=cached.core_dict,
                        bundle_dict=cached.bundle_dict,
                        mapping_rules=cached.mapping_rules,
                        core_path=Path(cached.core_path_str),
                        name=name,
                        skill_root=skill_root,
                    )

                core_path = diagram_dir / f"{name}_skill.json"
                bundle_path = diagram_dir / f"{name}_skill_bundle.json"

                # If core_path doesn't exist, try to find any *_skill.json or *.json file
                # This handles cases like cloud temp directories where folder name doesn't match skill name
                if not core_path.exists():
                    # First try *_skill.json pattern
                    skill_jsons = list(diagram_dir.glob("*_skill.json"))
                    if not skill_jsons:
                        # Fall back to any .json that's not a bundle
                        skill_jsons = [p for p in diagram_dir.glob("*.json") if "_bundle" not in p.name]

                    if skill_jsons:
                        core_path = skill_jsons[0]
                        # Derive name from the found file
                        fname = core_path.stem  # e.g., "unnamed_skill" or "unnamed"
                        if fname.endswith("_skill"):
                            name = fname[:-6]
                        else:
                            name = fname
                        bundle_path = diagram_dir / f"{name}_skill_bundle.json"
                        if not bundle_path.exists():
                            bundle_path = diagram_dir / f"{name}_bundle.json"
                        logger.debug(f"[build_agent_skills] Found skill JSON by scan: {core_path}")

                if not core_path.exists():
                    logger.warning(f"[build_agent_skills] Diagram core JSON not found: {core_path}")
                    return None

                with core_path.open("r", encoding="utf-8") as f:
                    core_dict = json.load(f)
                bundle_dict = None
                if bundle_path.exists():
                    with bundle_path.open("r", encoding="utf-8") as bf:
                        bundle_dict = json.load(bf)

                # Read mapping rules once so they can be cached alongside the parsed diagram.
                mapping_rules: Optional[dict] = None
                mapping_file = skill_root / "data_mapping.json"
                if mapping_file.exists():
                    try:
                        with mapping_file.open("r", encoding="utf-8") as mf:
                            mapping_rules = json.load(mf)
                    except Exception as _me:
                        logger.warning(f"[build_agent_skills] Failed to read mapping rules from {mapping_file}: {_me}")

                sk = _build_from_payload(
                    core_dict=core_dict,
                    bundle_dict=bundle_dict,
                    mapping_rules=mapping_rules,
                    core_path=core_path,
                    name=name,
                    skill_root=skill_root,
                )
                if sk is None:
                    return None

                # Store cache only after a successful build so we never persist a
                # payload that fails downstream construction.
                try:
                    from agent.ec_skills import skill_cache as _skill_cache
                    _skill_cache.store(
                        skill_root,
                        _skill_cache.ResolvedPayload(
                            schema_version=_skill_cache.SCHEMA_VERSION,
                            core_dict=core_dict,
                            bundle_dict=bundle_dict,
                            mapping_rules=mapping_rules,
                            core_path_str=str(core_path),
                        ),
                    )
                except Exception as _se:
                    logger.debug(f"[build_agent_skills] skill_cache store error for {name}: {_se}")

                return sk
            except Exception as e:
                # Extract skill name for better error reporting
                skill_root = diagram_dir.parent
                base = skill_root.name
                skill_name = base[:-6] if base.endswith("_skill") else base
                logger.warning(f"[build_agent_skills] Diagram load failed for skill '{skill_name}' at {diagram_dir}: {e}")
                import traceback
                logger.debug(f"[build_agent_skills] Full traceback for '{skill_name}':\n{traceback.format_exc()}")
                return None

        def load_one_skill(skill_root: Path) -> Optional[EC_Skill]:
            if not skill_root.exists() or not skill_root.is_dir():
                return None

            diagram_dir = skill_root / "diagram_dir"
            code_dir = skill_root / "code_dir"

            # Priority: diagram_dir is the PRIMARY source (must exist for workflow skills)
            # code_dir is the FALLBACK for pure code skills (no diagram)
            if diagram_dir.exists():
                try:
                    sk = load_from_diagram(diagram_dir)
                    if sk is not None:
                        logger.info(f"[build_agent_skills] ✅ Successfully loaded skill from diagram_dir: {diagram_dir}")
                        return sk
                except Exception as e:
                    logger.error(f"[build_agent_skills] ❌ Failed to load from diagram_dir {diagram_dir}: {e}")

            # Fallback to code_dir for pure code skills (e.g. search_digikey_chatter_skill)
            if code_dir.exists():
                try:
                    sk = load_from_code(skill_root, code_dir)
                    if sk is not None:
                        logger.info(f"[build_agent_skills] ✅ Successfully loaded skill from code_dir: {code_dir}")
                        return sk
                except Exception as e:
                    logger.error(f"[build_agent_skills] ❌ Failed to load from code_dir {code_dir}: {e}")

            # Neither diagram_dir nor code_dir found
            logger.warning(f"[build_agent_skills] Neither diagram_dir nor code_dir found under {skill_root}")
            return None

        # Load the single skill using load_one_skill helper
        sk = load_one_skill(skill_root)
        if sk is not None:
            logger.info(f"[load_skill_from_folder] ✅ Loaded skill: {sk.name} (source={sk.source})")
            return sk
        else:
            logger.warning(f"[load_skill_from_folder] Failed to load skill from {skill_root}")
            return None

    except Exception as e:
        logger.error(f"[load_skill_from_folder] Error loading skill: {e}")
        logger.error(traceback.format_exc())
        return None


def build_agent_skills_from_files(mainwin, skill_path: str = ""):
    """Legacy function - kept for backward compatibility.
    
    Use load_skill_from_folder() for new code.
    """
    if skill_path:
        skill = load_skill_from_folder(Path(skill_path), mainwin)
        return [skill] if skill else []
    return []
