import traceback
import asyncio
import time
from pathlib import Path
from typing import List, Optional, Tuple, Any
import inspect
import json
from agent.ec_agents.agent_utils import load_agent_skills_from_cloud
from agent.ec_skills.ecbot_rpa.ecbot_rpa_chatter_skill import create_rpa_helper_chatter_skill, create_rpa_operator_chatter_skill, create_rpa_supervisor_chatter_skill, create_rpa_supervisor_scheduling_chatter_skill
from agent.ec_skills.ecbot_rpa.ecbot_rpa_skill import create_rpa_helper_skill, create_rpa_operator_skill, create_rpa_supervisor_scheduling_skill, create_rpa_supervisor_skill
from agent.ec_skills.my_twin.my_twin_chatter_skill import create_my_twin_chatter_skill
from agent.ec_skills.search_1688.search_1688_skill import create_search_1688_skill
from agent.ec_skills.search_digi_key.search_digi_key_skill import create_search_digi_key_skill
from agent.ec_skills.search_parts.search_parts_chatter_skill import create_search_parts_chatter_skill
from agent.ec_skills.search_parts.search_parts_skill import create_search_parts_skill
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
    """优化的分批并行技能创建"""
    logger.info("[build_agent_skills] Building skills with optimized batching...")

    # 按优先级和依赖关系分组技能
    # 第一批：核心技能（快速创建）
    core_skills = [
        ("my_twin_chatter", create_my_twin_chatter_skill),
        ("self_test", create_self_test_skill),
        ("self_test_chatter", create_self_test_chatter_skill),
        ("test_dev", create_test_dev_skill)
    ]
    
    # 第二批：RPA技能（中等复杂度）
    rpa_skills = [
        ("rpa_helper", create_rpa_helper_skill),
        ("rpa_helper_chatter", create_rpa_helper_chatter_skill),
        ("rpa_operator", create_rpa_operator_skill),
        ("rpa_operator_chatter", create_rpa_operator_chatter_skill),
    ]
    
    # 第三批：高级RPA和搜索技能（较复杂）
    advanced_skills = [
        ("rpa_supervisor_scheduling", create_rpa_supervisor_scheduling_skill),
        ("rpa_supervisor_scheduling_chatter", create_rpa_supervisor_scheduling_chatter_skill),
        ("rpa_supervisor", create_rpa_supervisor_skill),
        ("rpa_supervisor_chatter", create_rpa_supervisor_chatter_skill),
        ("search_1688", create_search_1688_skill),
        ("search_digi_key", create_search_digi_key_skill),
        ("search_parts", create_search_parts_skill),
        ("search_parts_chatter", create_search_parts_chatter_skill),
    ]

    start_time = time.time()
    total_skills = len(core_skills) + len(rpa_skills) + len(advanced_skills)
    logger.info(f"[build_agent_skills] Starting optimized creation of {total_skills} skills in 3 batches...")

    all_skills = []
    
    # 批次1：核心技能（并发度4）
    logger.info(f"[build_agent_skills] Batch 1: Creating {len(core_skills)} core skills...")
    batch1_start = time.time()
    batch1_results = await _create_skills_batch(mainwin, core_skills, max_concurrent=4)
    all_skills.extend(batch1_results)
    batch1_time = time.time() - batch1_start
    logger.info(f"[build_agent_skills] Batch 1 completed in {batch1_time:.3f}s")
    
    # 批次2：RPA技能（并发度3，避免资源竞争）
    logger.info(f"[build_agent_skills] Batch 2: Creating {len(rpa_skills)} RPA skills...")
    batch2_start = time.time()
    batch2_results = await _create_skills_batch(mainwin, rpa_skills, max_concurrent=3)
    all_skills.extend(batch2_results)
    batch2_time = time.time() - batch2_start
    logger.info(f"[build_agent_skills] Batch 2 completed in {batch2_time:.3f}s")
    
    # 批次3：高级技能（并发度2，避免过载）
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
    """创建一批技能，控制并发数"""
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
    
    # 创建所有任务
    tasks = [
        create_single_skill(skill_name, creator_func) 
        for skill_name, creator_func in skill_creators
    ]
    
    # 并行执行，但限制并发数
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 过滤出有效的技能
    skills = [result for result in results if result is not None and not isinstance(result, Exception)]
    return skills

async def build_agent_skills(mainwin, skill_path=""):
    """构建 Agent Skills - 超级并行优化版本"""
    try:
        logger.info("[build_agent_skills] Starting ultra-parallel skill building...")
        start_time = time.time()
        
        # 🚀 并行策略：同时启动云端查询和本地构建
        cloud_task = asyncio.create_task(_load_skills_from_cloud_async(mainwin))
        local_task = asyncio.create_task(_build_local_skills_async(mainwin, skill_path))
        
        # 等待任一任务完成，优先使用云端结果
        done, pending = await asyncio.wait(
            [cloud_task, local_task], 
            return_when=asyncio.FIRST_COMPLETED,
            timeout=3.0  # 3秒超时保护
        )
        
        skills = []
        cloud_success = False
        
        # 检查云端任务结果
        if cloud_task in done:
            try:
                cloud_skills = await cloud_task
                if cloud_skills and len(cloud_skills) > 0:
                    skills = cloud_skills
                    cloud_success = True
                    logger.info(f"[build_agent_skills] ✅ Using {len(skills)} cloud skills")
                    
                    # 取消本地构建任务
                    if local_task in pending:
                        local_task.cancel()
                        logger.info("[build_agent_skills] 🚫 Cancelled local build (cloud success)")
                else:
                    logger.info("[build_agent_skills] ⚠️ Cloud returned empty, waiting for local...")
            except Exception as e:
                logger.warning(f"[build_agent_skills] ⚠️ Cloud task failed: {e}")
        
        # 如果云端失败或为空，使用本地构建结果
        if not cloud_success:
            if local_task in done:
                try:
                    local_skills = await local_task
                    skills = local_skills or []
                    logger.info(f"[build_agent_skills] ✅ Using {len(skills)} local skills")
                except Exception as e:
                    logger.error(f"[build_agent_skills] ❌ Local task failed: {e}")
            elif local_task in pending:
                try:
                    # 等待本地构建完成
                    logger.info("[build_agent_skills] ⏳ Waiting for local build completion...")
                    local_skills = await local_task
                    skills = local_skills or []
                    logger.info(f"[build_agent_skills] ✅ Using {len(skills)} local skills")
                except Exception as e:
                    logger.error(f"[build_agent_skills] ❌ Local build failed: {e}")
        
        # 清理未完成的任务
        for task in pending:
            if not task.cancelled():
                task.cancel()
        
        # 过滤掉None对象
        skills = [skill for skill in skills if skill is not None]
        
        # 记录最终结果
        total_time = time.time() - start_time
        skill_names = [s.name for s in skills] if skills else []
        logger.info(f"[build_agent_skills] 🎉 Ultra-parallel build completed in {total_time:.3f}s")
        logger.info(f"[build_agent_skills] Final result: {len(skills)} skills {skill_names}")
        
        return skills

    except Exception as e:
        logger.error(f"[build_agent_skills] Error: {e}")
        logger.error(f"[build_agent_skills] Traceback: {traceback.format_exc()}")
        return []


async def _load_skills_from_cloud_async(mainwin):
    """异步加载云端技能（带超时保护）"""
    try:
        logger.info("[build_agent_skills] 🌐 Loading skills from cloud...")
        
        # 使用超时保护，避免长时间等待
        cloud_skills = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, load_agent_skills_from_cloud, mainwin
            ),
            timeout=2.0  # 2秒超时
        )
        
        logger.info(f"[build_agent_skills] 🌐 Cloud returned {len(cloud_skills)} skills")
        return cloud_skills
        
    except asyncio.TimeoutError:
        logger.warning("[build_agent_skills] ⏰ Cloud loading timed out (2s)")
        return []
    except Exception as e:
        logger.warning(f"[build_agent_skills] ⚠️ Cloud loading failed: {e}")
        return []


async def _build_local_skills_async(mainwin, skill_path=""):
    """异步构建本地技能"""
    try:
        logger.info(f"[build_agent_skills] 🔧 Building local skills. Tool schemas: {len(tool_schemas)}")
        
        if not skill_path:
            # 并行创建所有本地技能
            local_skills = await build_agent_skills_parallel(mainwin)
            return local_skills
        else:
            # 从文件构建技能
            return await asyncio.get_event_loop().run_in_executor(
                None, build_agent_skills_from_files, mainwin, skill_path
            )
            
    except Exception as e:
        logger.error(f"[build_agent_skills] ❌ Local build error: {e}")
        return []


def build_agent_skills_from_files(mainwin, skill_path: str = ""):
    """从文件构建技能，目录结构：

    <skills_root>/<name>_skill/
      ├─ code_skill/ | code_dir/   # pure Python realization（package dir contains <module>_skill.py with build_skill()）
      └─ diagram_dir/              # Flowgram exported jsons: <name>_skill.json <name>_skill_bundle.json

    pick strategy：
    - if only 1 exists, just load from there
    - if both exist, pick the one with most recent modification date
    """
    try:
        skills: List[object] = []

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
                ctx = None
                try:
                    ctx = AppContext.get_useful_context()
                except Exception:
                    ctx = None

                try:
                    sig = inspect.signature(build_fn)
                    params = sig.parameters
                    if "run_context" in params and "mainwin" in params:
                        built = build_fn(run_context=ctx, mainwin=mainwin)
                    elif "run_context" in params:
                        built = build_fn(run_context=ctx)
                    elif "mainwin" in params:
                        built = build_fn(mainwin)
                    else:
                        built = build_fn()
                except Exception as e:
                    logger.warning(f"[build_agent_skills] build_skill signature fallback due to: {e}")
                    # Last resort: try legacy positional mainwin
                    try:
                        built = build_fn(mainwin)
                    except Exception:
                        built = build_fn()

                # Accept either EC_Skill or (dto, stategraph)
                sk = None
                if isinstance(built, EC_Skill):
                    sk = built
                elif isinstance(built, tuple) and len(built) == 2:
                    dto, sg = built
                    try:
                        sk = EC_Skill()
                        sk.name = getattr(dto, "name", pkg_name)
                        sk.description = getattr(dto, "description", "")
                        sk.config = getattr(dto, "config", {}) or {}
                        sk.set_work_flow(sg)
                    except Exception as e:
                        logger.error(f"[build_agent_skills] Failed to wrap tuple into EC_Skill: {e}")
                        return None
                else:
                    logger.error("[build_agent_skills] build_skill() returned unsupported type")
                    return None
                
                # Load mapping rules from data_mapping.json
                if sk:
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

                workflow, _breakpoints = flowgram2langgraph(core_dict, bundle_dict)
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
                # expect entries named <name>_skill
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
