


def init_ecbot_rpa_helper_chatter_skill(agent, msg):
    msg = ""
    return {
        "messages": [agent.card.id, msg],
        "attributes": {}
    }

def init_ecbot_rpa_operator_chatter_skill(agent, msg):
    msg_txt = msg['params']['content']
    return {
        "messages": [agent.card.id, msg_txt],
        "attributes": {}
    }

def init_ecbot_rpa_superviser_chatter_skill(agent, msg):
    msg_txt = msg['params']['content']
    return {
        "messages": [agent.card.id, msg_txt],
        "attributes": {}
    }