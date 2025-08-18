from agent.ec_skill import FileAttachment
from agent.ec_skill import NodeState

from agent.ec_skills.my_twin.my_twin_chatter_skill import human_message


def prep_my_twin_chatter_skill(agent, msg):
    print("prep_my_twin_chatter_skill", type(msg), msg)

    msg_txt = msg['params']['content']
    print("prep task with message text:", msg_txt)
    atts = []
    if msg['params']['attachments']:
        for att in msg['params']['attachments']:
            atts.append(FileAttachment(name= att['name'],type= att['type'],url= att['url'], data=""))

    chat_id = msg['params']['chatId']
    msg_id = msg['id']
    human = msg['params']['human']

    init_state = NodeState(
        messages=[agent.card.id, chat_id, msg_id, "", msg_txt],
        input=msg_txt,
        attachments=atts,
        prompts=[],
        formatted_prompts=[],
        attributes={"human": human, "params": msg['params']},
        result={},
        tool_input={},
        tool_result={},
        error="",
        retries=3,
        condition=False,
        case="",
        goals=[]
    )
    return init_state