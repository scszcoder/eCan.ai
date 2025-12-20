

from agent.ec_skills.build_agent_skills import build_agent_skills_from_files
from agent.ec_skills.ecbot_rpa.ecbot_rpa_chatter_skill import create_rpa_helper_chatter_skill, create_rpa_operator_chatter_skill, create_rpa_supervisor_chatter_skill, create_rpa_supervisor_scheduling_chatter_skill
from agent.ec_skills.ecbot_rpa.ecbot_rpa_skill import create_rpa_helper_skill, create_rpa_operator_skill, create_rpa_supervisor_scheduling_skill, create_rpa_supervisor_skill
from agent.ec_skills.my_twin.my_twin_chatter_skill import create_my_twin_chatter_skill
from agent.ec_skills.search_1688.search_1688_chatter_skill import create_search_1688_chatter_skill
from agent.ec_skills.search_1688.search_1688_skill import create_search_1688_skill
from agent.mcp.server.tool_schemas import tool_schemas


async def save_agent_skills(mainwin, skills):
    for skill in skills:
        print(f"tool_schemas: {len(tool_schemas)}.")
        if not skill_path:
            print("build agent skills from code......")
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
            new_skill = await create_search_1688_chatter_skill(mainwin)
            skills.append(new_skill)
        else:
            skills = build_agent_skills_from_files(mainwin, skill_path)

    print(f"done built agent skills: {len(skills)} {[s.name for s in skills]}")
    return skills

