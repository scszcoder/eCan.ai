from agent.ec_skills.ecbot_rpa.ecbot_rpa_skill import *
from agent.ec_skills.search_1688.search_1688_skill import *

async def build_agent_skills(mainwin, skill_path=""):
    skills = []
    print(f"tool_schemas: {len(tool_schemas)}.")
    if not skill_path:
        print("build agent skills from code......")
        new_skill = await create_rpa_helper_skill(mainwin)
        print("test skill mcp client:", len(new_skill.mcp_client.get_tools()))
        skills.append(new_skill)
        new_skill = await create_rpa_operator_skill(mainwin)
        skills.append(new_skill)
        new_skill = await create_rpa_supervisor_scheduling_skill(mainwin)
        skills.append(new_skill)
        new_skill = await create_rpa_supervisor_serve_requests_skill(mainwin)
        skills.append(new_skill)
        new_skill = await create_search_1688_skill(mainwin)
        skills.append(new_skill)
    else:
        skills = build_agent_skills_from_files(mainwin, skill_path)
    return skills

def build_agent_skills_from_files(mainwin, skill_path=""):
    return []
