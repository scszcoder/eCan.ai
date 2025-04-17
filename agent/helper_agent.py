from agent.context_utils import build_context_from_step

async def helperAgentResolve(step_stat, steps, next_step_index, screen_shot_file, mission, symTab):
    fixed = False
    settings = mission.main_win_settings
    mainwin = mission.get_main_win()
    helper = mainwin.get_agent_helper()
    current_context = build_context_from_step(step_stat, steps, next_step_index, screen_shot_file, mission, symTab)
    result, fixed = await helper.resolve(current_context)

    return fixed