from agent.ec_skill import NodeState

def prep_search_parts_skill(agent, task_id, msg=None, current_state=None):
    logger.debug("init_search_parts_skill", type(msg), msg)  # msg.params.message[0].text

    attachments = []
    msg_txt = ""
    init_state = NodeState(
        messages=[agent.card.id, "", "", task_id, msg_txt],
        input=msg_txt,
        attachments=attachments,
        prompts=[],
        history=[],
        attributes={},
        result={},
        tool_input={
            "url": "https://www.digikey.com/en/products"
        },
        tool_result={},
        threads=[],
        metadata={},
        error="",
        retries=3,
        condition=False,
        case="",
        goals=[]
    )
    if not current_state:
        return init_state
    else:
        current_state["attachments"] = attachments
        current_state["messages"].append(msg_txt)
        current_state["tool_input"]={
            "url": "https://www.digikey.com/en/products"
        }
        return current_state