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
    """并行创建所有本地技能"""
    logger.info("[build_agent_skills] Building skills in parallel...")

    # 定义所有技能创建函数
    skill_creators = [
        ("my_twin_chatter", create_my_twin_chatter_skill),
        ("rpa_helper", create_rpa_helper_skill),
        ("rpa_helper_chatter", create_rpa_helper_chatter_skill),
        ("rpa_operator", create_rpa_operator_skill),
        ("rpa_operator_chatter", create_rpa_operator_chatter_skill),
        ("rpa_supervisor_scheduling", create_rpa_supervisor_scheduling_skill),
        ("rpa_supervisor_scheduling_chatter", create_rpa_supervisor_scheduling_chatter_skill),
        ("rpa_supervisor", create_rpa_supervisor_skill),
        ("rpa_supervisor_chatter", create_rpa_supervisor_chatter_skill),
        ("search_1688", create_search_1688_skill),
        ("search_digi_key", create_search_digi_key_skill),
        ("search_parts", create_search_parts_skill),
        ("search_parts_chatter", create_search_parts_chatter_skill),
        ("self_test_chatter", create_self_test_chatter_skill),
        ("self_test", create_self_test_skill),
        ("test_dev", create_test_dev_skill)
    ]

    start_time = time.time()
    logger.info(f"[build_agent_skills] Starting parallel creation of {len(skill_creators)} skills...")

    # 创建所有技能创建任务
    tasks = []
    for skill_name, creator_func in skill_creators:
        task = asyncio.create_task(creator_func(mainwin), name=skill_name)
        tasks.append(task)

    # 并行执行所有任务
    results = await asyncio.gather(*tasks, return_exceptions=True)

    end_time = time.time()
    duration = end_time - start_time
    logger.info(f"[build_agent_skills] Parallel creation completed in {duration:.3f}s")

    # 处理结果
    skills = []
    for i, (skill_name, _) in enumerate(skill_creators):
        result = results[i]
        if isinstance(result, Exception):
            logger.error(f"[build_agent_skills] Failed to create {skill_name}: {result}")
        elif result is not None:
            skills.append(result)
            logger.debug(f"[build_agent_skills] Successfully created {skill_name}")
        else:
            logger.warning(f"[build_agent_skills] {skill_name} returned None")

    logger.info(f"[build_agent_skills] Successfully created {len(skills)}/{len(skill_creators)} skills")
    return skills

async def build_agent_skills(mainwin, skill_path=""):
    """构建 Agent Skills - 优化版本"""
    try:
        # 1. 尝试从云端加载技能
        logger.info("[build_agent_skills] Loading skills from cloud...")
        skills = load_agent_skills_from_cloud(mainwin)
        logger.info(f"[build_agent_skills] Loaded {len(skills)} skills from cloud")

        # 2. 如果云端没有技能，则并行创建本地技能
        if not skills:
            logger.info(f"[build_agent_skills] No cloud skills, creating local skills. Tool schemas: {len(tool_schemas)}")

            if not skill_path:
                # 并行创建所有本地技能
                local_skills = await build_agent_skills_parallel(mainwin)
                skills.extend(local_skills)
            else:
                # 从文件构建技能（占位符）
                skills = build_agent_skills_from_files(mainwin, skill_path)

        # 3. 过滤掉None对象
        skills = [skill for skill in skills if skill is not None]

        # 4. 记录最终结果
        skill_names = [s.name for s in skills] if skills else []
        logger.info(f"[build_agent_skills] Final result: {len(skills)} skills {skill_names}")

        return skills

    except Exception as e:
        logger.error(f"[build_agent_skills] Error: {e}")
        logger.error(f"[build_agent_skills] Traceback: {traceback.format_exc()}")
        return []


def build_agent_skills_from_files(mainwin, skill_path=""):
    """从文件构建技能（占位符实现）"""
    logger.info(f"[build_agent_skills] Building skills from files: {skill_path}")
    # TODO: 实现从文件加载技能的逻辑
    return []
