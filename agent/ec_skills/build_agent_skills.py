from agent.ec_skills.ecbot_rpa.ecbot_rpa_skill import *
from agent.ec_skills.ecbot_rpa.ecbot_rpa_chatter_skill import *
from agent.ec_skills.search_1688.search_1688_skill import *
from agent.ec_skills.search_1688.search_1688_chatter_skill import *
from agent.ec_skills.search_digi_key.search_digi_key_skill import *
from agent.ec_skills.search_parts.search_parts_skill import *
from agent.ec_skills.search_parts.search_parts_chatter_skill import *

from agent.ec_skills.my_twin.my_twin_chatter_skill import *
from agent.ec_agents.agent_utils import load_agent_skills_from_cloud
from agent.ec_skills.self_test.self_test_skill import create_self_test_skill
from agent.ec_skills.self_test.self_test_chatter_skill import create_self_test_chatter_skill
from utils.logger_helper import logger_helper as logger

async def build_agent_skills(mainwin, skill_path=""):
    try:
        skills = load_agent_skills_from_cloud(mainwin)
        logger.info("agent skills from cloud:", skills)
        if not skills:
            logger.info(f"tool_schemas: {len(tool_schemas)}.")
            if not skill_path:
                logger.info("build agent skills from code......")
                new_skill = await create_my_twin_chatter_skill(mainwin)
                # print("twin chatter skill:", len(new_skill.mcp_client.get_tools()))
                skills.append(new_skill)

                new_skill = await create_rpa_helper_skill(mainwin)
                # print("test skill mcp client:", len(new_skill.mcp_client.get_tools()))
                skills.append(new_skill)
                new_skill = await create_rpa_helper_chatter_skill(mainwin)
                skills.append(new_skill)

                new_skill = await create_rpa_operator_skill(mainwin)
                skills.append(new_skill)
                new_skill = await create_rpa_operator_chatter_skill(mainwin)
                skills.append(new_skill)

                new_skill = await create_rpa_supervisor_scheduling_skill(mainwin)
                skills.append(new_skill)
                new_skill = await create_rpa_supervisor_scheduling_chatter_skill(mainwin)
                skills.append(new_skill)

                new_skill = await create_rpa_supervisor_skill(mainwin)
                skills.append(new_skill)
                new_skill = await create_rpa_supervisor_chatter_skill(mainwin)
                skills.append(new_skill)

                new_skill = await create_search_1688_skill(mainwin)
                skills.append(new_skill)

                new_skill = await create_search_digi_key_skill(mainwin)
                skills.append(new_skill)

                new_skill = await create_search_parts_skill(mainwin)
                skills.append(new_skill)

                new_skill = await create_search_parts_chatter_skill(mainwin)
                skills.append(new_skill)

                new_skill = await create_self_test_chatter_skill(mainwin)
                skills.append(new_skill)

                new_skill = await create_self_test_skill(mainwin)
                skills.append(new_skill)
            else:
                skills = build_agent_skills_from_files(mainwin, skill_path)

        # 过滤掉None对象
        skills = [skill for skill in skills if skill is not None]
        
        logger.info(f"done built agent skills: {len(skills)} {[s.name for s in skills]}")
        return skills

    except Exception as e:
        logger.error(f"Error in get agent skills: {e} {traceback.format_exc()}")
        return []


def build_agent_skills_from_files(mainwin, skill_path=""):
    return []
