


def prep_ecbot_rpa_helper_skill(agent, msg=''):
    msg_txt = msg
    return {
        "messages": [agent.card.id, msg],
        "attributes": {}
    }

def prep_ecbot_rpa_operator_skill(agent, msg=''):
    msg_txt = msg
    return {
        "messages": [agent.card.id, msg_txt],
        "attributes": {}
    }

def prep_ecbot_rpa_superviser_skill(agent, msg=''):
    msg_txt = msg
    return {
        "messages": [agent.card.id, msg_txt],
        "attributes": {}
    }

