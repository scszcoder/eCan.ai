import traceback
import asyncio
import time
import uuid
from pathlib import Path
from typing import List, Optional, Tuple, Any
import inspect
import json
from agent.ec_agents.agent_utils import load_agent_skills_from_cloud
# from agent.ec_skills.ecbot_rpa.ecbot_rpa_chatter_skill import create_rpa_helper_chatter_skill, create_rpa_operator_chatter_skill, create_rpa_supervisor_chatter_skill, create_rpa_supervisor_scheduling_chatter_skill
# from agent.ec_skills.ecbot_rpa.ecbot_rpa_skill import create_rpa_helper_skill, create_rpa_operator_skill, create_rpa_supervisor_scheduling_skill, create_rpa_supervisor_skill
from agent.ec_skills.my_twin.my_twin_chatter_skill import create_my_twin_chatter_skill
# from agent.ec_skills.search_1688.search_1688_skill import create_search_1688_skill
# from agent.ec_skills.search_digi_key.search_digi_key_skill import create_search_digi_key_skill
# from agent.ec_skills.search_parts.search_parts_chatter_skill import create_search_parts_chatter_skill
# from agent.ec_skills.search_parts.search_parts_skill import create_search_parts_skill
from agent.ec_skills.self_test.self_test_skill import create_self_test_skill
from agent.ec_skills.self_test.self_test_chatter_skill import create_self_test_chatter_skill
from agent.ec_skills.dev_utils.skill_dev_utils import create_test_dev_skill

from agent.mcp.server.tool_schemas import tool_schemas
from utils.logger_helper import logger_helper as logger
from agent.ec_skills.extern_skills.extern_skills import user_skills_root, ensure_skill_venv
from agent.ec_skills.extern_skills.inproc_loader import temp_sys_path, _site_packages
from agent.ec_skill import EC_Skill
from agent.ec_skills.flowgram2langgraph import flowgram2langgraph
from app_context import AppContext

async def build_agent_skills_parallel(mainwin):
    """Optimized batch parallel skill creation"""
    logger.info("[build_agent_skills] Building skills with optimized batching...")

    # Group skills by priority and dependencies
    # Batch 1: Core skills (fast creation)
    core_skills = [
        ("my_twin_chatter", create_my_twin_chatter_skill),
        ("self_test", create_self_test_skill),
        ("self_test_chatter", create_self_test_chatter_skill),
        ("test_dev", create_test_dev_skill)
    ]

    # Batch 2: RPA skills (medium complexity)
    rpa_skills = [
        # ("rpa_helper", create_rpa_helper_skill),
        # ("rpa_helper_chatter", create_rpa_helper_chatter_skill),
        # ("rpa_operator", create_rpa_operator_skill),
        # ("rpa_operator_chatter", create_rpa_operator_chatter_skill),
    ]

    # Batch 3: Advanced RPA and search skills (more complex)
    advanced_skills = [
        # ("rpa_supervisor_scheduling", create_rpa_supervisor_scheduling_skill),
        # ("rpa_supervisor_scheduling_chatter", create_rpa_supervisor_scheduling_chatter_skill),
        # ("rpa_supervisor", create_rpa_supervisor_skill),
        # ("rpa_supervisor_chatter", create_rpa_supervisor_chatter_skill),
        # ("search_1688", create_search_1688_skill),
        # ("search_digi_key", create_search_digi_key_skill),
        # ("search_parts", create_search_parts_skill),
        # ("search_parts_chatter", create_search_parts_chatter_skill),
    ]

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


async def _create_skills_batch(mainwin, skill_creators, max_concurrent=4):
    """Create a batch of skills with controlled concurrency"""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def create_single_skill(skill_name, creator_func):
        async with semaphore:
            try:
                skill = await creator_func(mainwin)
                if skill is not None:
                    logger.debug(f"[build_agent_skills] ✅ Created {skill_name}")
                    return skill
                else:
                    logger.warning(f"[build_agent_skills] ⚠️ {skill_name} returned None")
                    return None
            except Exception as e:
                logger.error(f"[build_agent_skills] ❌ Failed to create {skill_name}: {e}")
                return None
    if skill_creators:
        # Create all tasks
        tasks = [
            create_single_skill(skill_name, creator_func)
            for skill_name, creator_func in skill_creators
        ]

        # Execute in parallel with concurrency limit
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out valid skills
        skills = [result for result in results if result is not None and not isinstance(result, Exception)]
    else:
        skills = []
    return skills

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

        # Step 3: Check cloud data, if available overwrite local database (async non-blocking)
        final_db_skills = []
        if cloud_skills and len(cloud_skills) > 0:
            logger.info(f"[build_agent_skills] Step 3: Cloud data available, using cloud skills...")

            # Cloud data overwrites local database (background async execution, non-blocking)
            asyncio.create_task(_update_database_with_cloud_skills(cloud_skills, mainwin))
            logger.info(f"[build_agent_skills] 🔄 Database update started in background (non-blocking)")

            # Use cloud data as final database skills
            final_db_skills = cloud_skills
            logger.info(f"[build_agent_skills] ✅ Using {len(cloud_skills)} cloud skills")
        else:
            # No cloud data, use local database data
            logger.info(f"[build_agent_skills] Step 3: No cloud data, using database skills...")
            final_db_skills = db_skills

        # Step 4: Convert database skills to skill objects
        logger.info("[build_agent_skills] Step 4: Converting DB skills to objects...")
        logger.info(f"[build_agent_skills] DB skills to convert: {len(final_db_skills)}")
        memory_skills = []
        for i, db_skill in enumerate(final_db_skills):
            try:
                logger.debug(f"[build_agent_skills] Converting DB skill {i+1}/{len(final_db_skills)}: {db_skill.get('name', 'unknown')}")
                skill_obj = _convert_db_skill_to_object(db_skill)
                if skill_obj:
                    memory_skills.append(skill_obj)
                    logger.debug(f"[build_agent_skills] ✅ Successfully converted: {skill_obj.name}")
                else:
                    logger.warning(f"[build_agent_skills] ⚠️ Conversion returned None for: {db_skill.get('name', 'unknown')}")
            except Exception as e:
                logger.error(f"[build_agent_skills] ❌ Failed to convert skill {db_skill.get('name', 'unknown')}: {e}")
                logger.error(f"[build_agent_skills] Traceback: {traceback.format_exc()}")

        logger.info(f"[build_agent_skills] ✅ Converted {len(memory_skills)} DB skills to objects")

        # Step 5: Build local code skills
        logger.info("[build_agent_skills] Step 5: Building local code skills...")
        try:
            local_code_skills = await _build_local_skills_async(mainwin, skill_path)
            logger.info(f"[build_agent_skills] ✅ Built {len(local_code_skills or [])} local code skills")
        except Exception as e:
            logger.error(f"[build_agent_skills] ❌ Local build failed: {e}")
            local_code_skills = []

        # Step 6: Merge all skill data with deduplication
        logger.info("[build_agent_skills] Step 6: Merging all skills...")
        
        # Use a dictionary to track skills by name (code skills override DB skills)
        skills_dict = {}
        code_skill_names = set()
        
        # First add database/cloud skills
        for skill in memory_skills:
            if skill is not None and hasattr(skill, 'name'):
                skills_dict[skill.name] = skill
        
        # Then add locally built skills from code (these will override DB skills with same name)
        if local_code_skills:
            for skill in local_code_skills:
                if skill is not None and hasattr(skill, 'name'):
                    code_skill_names.add(skill.name)
                    if skill.name in skills_dict:
                        logger.info(f"[build_agent_skills] 🔄 Code skill '{skill.name}' overrides DB skill")
                        logger.info(f"[build_agent_skills] 💡 Consider deleting '{skill.name}' from database to avoid conflicts")
                    skills_dict[skill.name] = skill
        
        # Convert back to list and mark source
        all_skills = []
        for skill_name, skill in skills_dict.items():
            if skill_name in code_skill_names:
                skill.source = "code"
            else:
                skill.source = "ui"  # Assuming skills not from code are from UI
            all_skills.append(skill)

        # Step 7: Update mainwindow.agent_skills memory
        logger.info("[build_agent_skills] Step 7: Updating mainwindow.agent_skills...")
        mainwin.agent_skills = all_skills

        # Log final results
        total_time = time.time() - start_time
        skill_names = [s.name for s in all_skills] if all_skills else []
        logger.info(f"[build_agent_skills] 🎉 Complete! Total: {len(all_skills)} skills in {total_time:.3f}s")
        logger.info(f"[build_agent_skills] - DB/Cloud skills: {len(memory_skills)}")
        logger.info(f"[build_agent_skills] - Local code skills: {len(local_code_skills or [])}")
        logger.info(f"[build_agent_skills] - Skill names: {skill_names}")

        return all_skills

    except Exception as e:
        logger.error(f"[build_agent_skills] Error: {e}")
        logger.error(f"[build_agent_skills] Traceback: {traceback.format_exc()}")
        return []


async def _load_skills_from_database_async(mainwin):
    """Asynchronously load skill data from local database"""
    try:
        logger.info("[build_agent_skills] Loading skills from database...")

        # Get current user from mainwin
        if not mainwin or not hasattr(mainwin, 'user'):
            logger.error("[build_agent_skills] Cannot get username: mainwin or mainwin.user not available")
            return []
        
        username = mainwin.user
        logger.info(f"[build_agent_skills] Querying skills for user: {username}")

        # Get database service from mainwin (uses correct user-specific database path)
        if mainwin and hasattr(mainwin, 'ec_db_mgr'):
            skill_service = mainwin.ec_db_mgr.skill_service
            logger.info(f"[build_agent_skills] Using database from mainwin.ec_db_mgr")
        else:
            # Fallback: create new ECDBMgr (will use current directory)
            logger.warning("[build_agent_skills] mainwin.ec_db_mgr not available, using fallback ECDBMgr")
            from agent.db import ECDBMgr
            db_mgr = ECDBMgr()
            skill_service = db_mgr.skill_service

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

def _convert_db_skill_to_object(db_skill):
    """Convert database skill data to skill object with compiled workflow"""
    try:
        # Create EC_Skill object
        skill_obj = EC_Skill()

        # Set basic attributes
        skill_obj.id = db_skill.get('id', str(uuid.uuid4()))
        skill_obj.name = db_skill.get('name', 'Unknown Skill')
        skill_obj.description = db_skill.get('description', '')
        skill_obj.version = db_skill.get('version', '1.0.0')
        skill_obj.owner = db_skill.get('owner', '')
        skill_obj.config = db_skill.get('config', {})
        skill_obj.level = db_skill.get('level', 'entry')

        # Set other optional attributes
        if 'tags' in db_skill:
            skill_obj.tags = db_skill.get('tags', [])
        if 'ui_info' in db_skill:
            skill_obj.ui_info = db_skill.get('ui_info', {})
        if 'objectives' in db_skill:
            skill_obj.objectives = db_skill.get('objectives', [])
        if 'need_inputs' in db_skill:
            skill_obj.need_inputs = db_skill.get('need_inputs', [])

        diagram = db_skill.get('diagram')
        if diagram and isinstance(diagram, dict):
            try:
                logger.debug(f"[build_agent_skills] Rebuilding workflow for skill: {skill_obj.name}")
                # Store diagram for reference
                skill_obj.diagram = diagram
                logger.debug(f"[build_agent_skills] Rebuilding workflow diagram: {diagram}")

                # Convert flowgram diagram to LangGraph workflow with breakpoint support (v2 preprocessing)
                from agent.ec_skills.dev_defs import BreakpointManager
                from agent.ec_skills.flowgram2langgraph_v2 import flowgram2langgraph_v2
                bp_mgr = BreakpointManager()
                workflow, bp_list = flowgram2langgraph_v2(diagram, bundle_json=None, enable_subgraph=False, bp_mgr=bp_mgr)
                try:
                    # Populate manager after construction; node wrappers hold the same reference
                    if isinstance(bp_list, (list, tuple)):
                        bp_mgr.set_breakpoints(list(bp_list))
                except Exception:
                    pass
                
                if workflow:
                    # Compile the workflow with checkpointer
                    from langgraph.checkpoint.memory import InMemorySaver
                    checkpointer = InMemorySaver()
                    skill_obj.runnable = workflow.compile(checkpointer=checkpointer)
                    logger.info(f"[build_agent_skills] ✅ Successfully compiled workflow for: {skill_obj.name}")
                else:
                    logger.warning(f"[build_agent_skills] ⚠️ Failed to convert diagram to workflow for: {skill_obj.name}")
            except Exception as e:
                logger.error(f"[build_agent_skills] ❌ Error rebuilding workflow for {skill_obj.name}: {e}")
                logger.error(f"[build_agent_skills] Traceback: {traceback.format_exc()}")
        else:
            logger.warning(f"[build_agent_skills] ⚠️ No diagram data for skill: {skill_obj.name}")
            logger.warning(f"[build_agent_skills] 💡 This skill was created before diagram support was added")

        logger.debug(f"[build_agent_skills] Converted DB skill: {skill_obj.name} (runnable: {'✅' if skill_obj.runnable else '❌'})")
        return skill_obj

    except Exception as e:
        logger.error(f"[build_agent_skills] Error converting DB skill: {e}")
        logger.error(f"[build_agent_skills] Traceback: {traceback.format_exc()}")
        return None

async def _update_database_with_cloud_skills(cloud_skills, mainwin):
    """Update local database with cloud skill data"""
    try:
        logger.info(f"[build_agent_skills] Updating database with {len(cloud_skills)} cloud skills...")

        # Get current user from mainwin
        if not mainwin or not hasattr(mainwin, 'user'):
            logger.error("[build_agent_skills] Cannot get username: mainwin or mainwin.user not available")
            return
        
        username = mainwin.user

        # Get database service from mainwin (uses correct user-specific database path)
        if mainwin and hasattr(mainwin, 'ec_db_mgr'):
            skill_service = mainwin.ec_db_mgr.skill_service
        else:
            # Fallback: create new ECDBMgr (will use current directory)
            logger.warning("[build_agent_skills] mainwin.ec_db_mgr not available, using fallback ECDBMgr")
            from agent.db import ECDBMgr
            db_mgr = ECDBMgr()
            skill_service = db_mgr.skill_service

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
        logger.warning(f"[build_agent_skills] ⚠️ Cloud loading failed: {e}")
        return []


async def _build_local_skills_async(mainwin, skill_path=""):
    """Asynchronously build local skills"""
    try:
        logger.info(f"[build_agent_skills] 🔧 Building local skills. Tool schemas: {len(tool_schemas)}, {skill_path}")

        local_skills = []
        local_skills = await build_agent_skills_parallel(mainwin)

        # Build skills from files
        local_extern_skills = await asyncio.get_event_loop().run_in_executor(
            None, build_agent_skills_from_files, mainwin, skill_path
        )
        local_skills.extend(local_extern_skills)

        return local_skills
    except Exception as e:
        logger.error(f"[build_agent_skills] ❌ Local build error: {e}")
        return []


def build_agent_skills_from_files(mainwin, skill_path: str = ""):
    """Build skills from files, directory structure:

    <skills_root>/<name>_skill/
      ├─ code_skill/ | code_dir/   # pure Python realization (package dir contains <module>_skill.py with build_skill())
      └─ diagram_dir/              # Flowgram exported jsons: <name>_skill.json <name>_skill_bundle.json

    pick strategy:
    - if only 1 exists, just load from there
    - if both exist, pick the one with most recent modification date
    """
    try:
        skills: List[object] = []
        logger.debug("build_agent_skills_from_files", mainwin, skill_path)
        def latest_mtime(path: Path) -> float:
            if not path.exists():
                return -1.0
            if path.is_file():
                return path.stat().st_mtime
            m = -1.0
            for p in path.rglob("*"):
                try:
                    m = max(m, p.stat().st_mtime)
                except Exception:
                    pass
            return m

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
                stack.enter_context(temp_sys_path([pkg_dir]))
                stack.enter_context(temp_sys_path(_site_packages(venv_dir)))
                # Import the discovered module. If pkg_name is None, module lives directly under code_dir.
                if pkg_name:
                    mod = importlib.import_module(f"{pkg_name}.{module_base}")
                else:
                    mod = importlib.import_module(f"{module_base}")
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

                logger.debug(f"[build_agent_skills] Skill ready: {sk.name if sk else None}")
                # Load mapping rules from data_mapping.json
                if sk:
                    # Mark as code-based skill
                    sk.source = "code"
                    
                    mapping_file = skill_root / "data_mapping.json"
                    if mapping_file.exists():
                        try:
                            with mapping_file.open("r", encoding="utf-8") as mf:
                                mapping_data = json.load(mf)
                                sk.mapping_rules = mapping_data
                                logger.info(f"[build_agent_skills] Loaded mapping rules for {sk.name}")
                        except Exception as e:
                            logger.warning(f"[build_agent_skills] Failed to load mapping rules: {e}")
                
                return sk

        def load_from_diagram(diagram_dir: Path) -> Optional[EC_Skill]:
            # Expect files <name>_skill.json and optional <name>_skill_bundle.json under diagram_dir
            try:
                # Derive name from parent folder '<name>_skill'
                skill_root = diagram_dir.parent
                base = skill_root.name
                name = base[:-6] if base.endswith("_skill") else base
                core_path = diagram_dir / f"{name}_skill.json"
                bundle_path = diagram_dir / f"{name}_skill_bundle.json"

                if not core_path.exists():
                    logger.warning(f"[build_agent_skills] Diagram core JSON not found: {core_path}")
                    return None

                with core_path.open("r", encoding="utf-8") as f:
                    core_dict = json.load(f)
                bundle_dict = None
                if bundle_path.exists():
                    with bundle_path.open("r", encoding="utf-8") as bf:
                        bundle_dict = json.load(bf)

                from agent.ec_skills.dev_defs import BreakpointManager
                bp_mgr = BreakpointManager()
                workflow, _breakpoints = flowgram2langgraph(core_dict, bundle_dict, bp_mgr)
                try:
                    if isinstance(_breakpoints, (list, tuple)):
                        bp_mgr.set_breakpoints(list(_breakpoints))
                except Exception:
                    pass
                if not workflow:
                    logger.error(f"[build_agent_skills] flowgram2langgraph returned empty workflow for {core_path}")
                    return None

                sk = EC_Skill()
                sk.name = name
                # Try to set description/config/run_mode if present in core_dict
                try:
                    sk.description = core_dict.get("description", "") or sk.description
                except Exception:
                    pass
                try:
                    cfg = core_dict.get("config")
                    if isinstance(cfg, dict):
                        sk.config = cfg
                except Exception:
                    pass
                try:
                    run_mode = core_dict.get("run_mode")
                    if run_mode in ("developing", "released"):
                        sk.run_mode = run_mode
                except Exception:
                    pass
                sk.set_work_flow(workflow)
                
                # Load mapping rules from data_mapping.json (check both diagram_dir and parent skill_root)
                mapping_file = diagram_dir / "data_mapping.json"
                if not mapping_file.exists():
                    mapping_file = skill_root / "data_mapping.json"
                
                if mapping_file.exists():
                    try:
                        with mapping_file.open("r", encoding="utf-8") as mf:
                            mapping_data = json.load(mf)
                            sk.mapping_rules = mapping_data
                            logger.info(f"[build_agent_skills] Loaded mapping rules for {sk.name}")
                    except Exception as e:
                        logger.warning(f"[build_agent_skills] Failed to load mapping rules: {e}")
                
                return sk
            except Exception as e:
                logger.error(f"[build_agent_skills] Diagram load failed at {diagram_dir}: {e}")
                return None

        def load_one_skill(skill_root: Path) -> Optional[EC_Skill]:
            if not skill_root.exists() or not skill_root.is_dir():
                return None
            # Support both legacy 'code_skill' and new 'code_dir'
            code_dir_legacy = skill_root / "code_skill"
            code_dir_new = skill_root / "code_dir"
            # Prefer whichever exists; if both exist, pick the newer one
            if code_dir_legacy.exists() and code_dir_new.exists():
                code_dir = code_dir_legacy if latest_mtime(code_dir_legacy) >= latest_mtime(code_dir_new) else code_dir_new
            elif code_dir_new.exists():
                code_dir = code_dir_new
            else:
                code_dir = code_dir_legacy
            diagram_dir = skill_root / "diagram_dir"

            code_exists = code_dir.exists()
            diagram_exists = diagram_dir.exists()

            chosen = None
            if code_exists and not diagram_exists:
                chosen = ("code", code_dir)
            elif diagram_exists and not code_exists:
                chosen = ("diagram", diagram_dir)
            elif code_exists and diagram_exists:
                mc = latest_mtime(code_dir)
                md = latest_mtime(diagram_dir)
                chosen = ("code", code_dir) if mc >= md else ("diagram", diagram_dir)
            else:
                logger.warning(f"[build_agent_skills] No code_skill or diagram_dir under {skill_root}")
                return None

            kind, path_sel = chosen
            if kind == "code":
                return load_from_code(skill_root, path_sel)
            else:
                return load_from_diagram(path_sel)

        # Scan and load
        if not skill_path:
            root = user_skills_root()
            root.mkdir(parents=True, exist_ok=True)
            logger.info(f"[build_agent_skills] Scanning skills under: {root}")
            for entry in sorted(root.iterdir()):
                # Expect entries named <name>_skill
                if entry.is_dir() and entry.name.endswith("_skill"):
                    sk = load_one_skill(entry)
                    if sk is not None:
                        skills.append(sk)
        else:
            sdir = Path(skill_path)
            # If user points to inside code_skill or diagram_dir, go up to the skill root (<name>_skill)
            if sdir.name in ("code_skill", "diagram_dir"):
                skill_root = sdir.parent
            else:
                skill_root = sdir
            sk = load_one_skill(skill_root)
            if sk is not None:
                skills.append(sk)

        logger.info(f"[build_agent_skills] Loaded {len(skills)} skill(s) from files")
        return skills

    except Exception as e:
        logger.error(f"[build_agent_skills] Error loading skills from files: {e}")
        logger.error(traceback.format_exc())
        return []
