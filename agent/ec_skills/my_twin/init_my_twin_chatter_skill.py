def init_my_twin_chatter_skill(agent, msg):
    msg_txt = msg['params']['content']
    return {
        "messages": [agent.card.id, msg_txt],
        "attributes": {}
    }