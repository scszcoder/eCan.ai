


def init_search_1688_chatter_skill(agent, msg):
    msg_txt = msg.params.message.parts[0].text
    print("init task with message text:", msg_txt)
    return {
        "messages": [agent.card.id, msg_txt],
        "input": msg_txt
    }