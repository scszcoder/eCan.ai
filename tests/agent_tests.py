from agent.ec_agent import *
import asyncio


# test agent capabilities in a variety of ways.
# for now only test use_vision, and no test for playwright
async def test_helper(mwin):
    # create a a2a_client, test a2a.
    print("# agents....", len(mwin.agents))
    helper = next((ag for ag in mwin.agents if ag and "helper" in ag.card.name), None)

    if helper:
        helper_card = helper.get_card()

        test_a2a_client = A2AClient(helper_card)

        payload = {
            "id": "task-001",
            "sessionId": "sess-abc",
            "message": Message(role="user", parts=[TextPart(type="text", text="Summarize this report")]),
            "acceptedOutputModes": ["json"],
            "skill": "resolve_rpa_failure"  # Or whatever your agent expects
        }
        # send a say message to helper agent
        response = await test_a2a_client.send_task(payload)

        if response:
            print('\n--------------------------------')
            print('a2a  result:', response)
            # print(f'Platform:         {profile.platform}')

        else:
            print('No result')


        # create a MCP client to test mcp server.
        reponse = await helper.skills[0].runnable.ainvoke({"messages": "say hello to me"})
        print(response)
