from agent.service import *
import asyncio


# test agent capabilities in a variety of ways.
# for now only test use_vision, and no test for playwright
async def test_helper(mwin):
    helper = mwin.get_helper_agent()
    runner = Runner()
    helper_Task = ""
    helper.set_task(helper_Task)
    history = await helper.resolve()

    result = history.final_result()
    if result:
        print('\n--------------------------------')
        print('result:', result)
        # print(f'Platform:         {profile.platform}')

    else:
        print('No result')
