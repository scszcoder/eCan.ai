
def prep_search_digi_key_skill(agent, task_id, msg=None, file_names=[]):
    print("init_search_digi_key_skill", type(msg), msg)  # msg.params.message[0].text

    attachments = []
    msg_txt = ""
    init_state = {
        "messages": [agent.card.id, "", "", task_id, msg_txt],
        "input": msg_txt,
        "attachments": attachments,
        "tool_input": {
            "url": "https://www.digikey.com/en/products"
        }
    }
    return init_state
