from agent.service import *
import asyncio


# test agent capabilities in a variety of ways.
# for now only test use_vision, and no test for playwright
async def test_helper(mwin):
    agent = mwin.get_agent_helper()
    runner = Runner()
    helper_Task = ""
    agent.set_task(helper_Task)
    history = await agent.run()

    result = history.final_result()
    if result:
        print('\n--------------------------------')
        print('result:', result)
        # print(f'Platform:         {profile.platform}')

    else:
        print('No result')
