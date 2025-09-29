import traceback
import asyncio
import time
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


def build_agent_skills_from_files(mainwin, skill_path=""):
    """从文件构建技能（占位符实现）"""
    logger.info(f"[build_agent_skills] Building skills from files: {skill_path}")
    # TODO: 实现从文件加载技能的逻辑
    return []
