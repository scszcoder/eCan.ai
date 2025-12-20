


def prep_ecbot_rpa_helper_skill(agent, task_id, msg='', current_state=None):
    msg_txt = msg
    return {
        "messages": [agent.card.id, "", "", task_id, msg],
        "attributes": {}
    }

def prep_ecbot_rpa_operator_skill(agent, task_id, msg='', current_state=None):
    msg_txt = msg
    return {
        "messages": [agent.card.id, "", "", task_id, msg_txt],
        "attributes": {}
    }

def prep_ecbot_rpa_superviser_skill(agent, task_id, msg='', current_state=None):
    msg_txt = msg
    return {
        "messages": [agent.card.id, "", "", task_id, msg_txt],
        "attributes": {}
    }

