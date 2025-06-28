from agent.ec_skill import FileAttachment
def init_my_twin_chatter_skill(agent, msg):
    print("init_my_twin_chatter_skill", type(msg), msg)

    msg_txt = msg['params']['content']
    print("init task with message text:", msg_txt)
    atts = []
    if msg['params']['attachment']:
        for att in msg['params']['attachment']:
            atts.append(FileAttachment(name= att['name'],type= att['type'],url= att['url'], data=""))

    init_state = {
        "messages": [agent.card.id, msg_txt],
        "input": msg_txt,
        "attachments": atts
    }
    return init_state