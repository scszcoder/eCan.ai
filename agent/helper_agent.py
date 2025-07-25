
async def helperAgentResolve(mission, fault_context):
    fixed = False
    settings = mission.main_win_settings
    mainwin = mission.get_main_win()
    helper = mainwin.get_agent_helper()
    helper = next((ag for ag in mainwin.agents if ag.get_card().name == "ECBot Helper Agent" and not ag.is_busy()), None)
    if helper:
        secret_rpa_agent = next((ag for ag in mainwin.agents if ag.get_card().name == "ECBot Secret Agent" and not ag.is_busy()),
                      None)
        # now secret_rpa_agent will send an a2a request to a local helper agent for help.
        result, fixed = await secret_rpa_agent.request_help(helper)
    else:
        print("no helper available")

    return fixed