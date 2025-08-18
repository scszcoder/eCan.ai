from agent.ec_skill import NodeState

def prep_search_parts_skill(agent, msg=None, file_names=[]):
    print("init_search_parts_skill", type(msg), msg)  # msg.params.message[0].text

    attachments = []
    msg_txt = ""
    init_state = NodeState(
        messages=[agent.card.id, msg_txt],
        input=msg_txt,
        attachments=attachments,
        prompts=[],
        formatted_prompts=[],
        attributes={},
        result={},
        tool_input={
            "url": "https://www.digikey.com/en/products"
        },
        tool_result={},
        error="",
        retries=3,
        condition=False,
        case="",
        goals=[]
    )
    return init_state
