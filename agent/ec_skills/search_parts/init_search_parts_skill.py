
def init_search_parts_skill(agent, msg=None, file_names=[]):
    print("init_search_parts_skill", type(msg), msg)  # msg.params.message[0].text

    attachments = []
    msg_txt = ""
    init_state = {
        "messages": [agent.card.id, msg_txt],
        "input": msg_txt,
        "attachments": attachments,
        "tool_input": {
        }
    }
    return init_state
