from agent.ec_skill import FileAttachment
from agent.ec_skill import NodeState
from agent.a2a.common.types import SendTaskRequest
from agent.ec_skills.my_twin.my_twin_chatter_skill import human_message


def prep_my_twin_chatter_skill(agent, task_id, msg, current_state=None):
    print("prep_my_twin_chatter_skill", type(msg), msg)

    if isinstance(msg, SendTaskRequest):
        msg_txt = msg.params.message.parts[0].text
        chat_id = msg.params.metadata["chatId"]
        msg_id = msg.id
        atts = []
        human = False
        params = msg.params
        method = msg.method
        form = msg.params.metadata["form"]
    else:
        print("prep response message", msg)
        msg_txt = msg['params']['content']
        print("prep task with message text:", msg_txt)
        atts = []
        if msg['params']['attachments']:
            for att in msg['params']['attachments']:
                atts.append(FileAttachment(name= att['name'],type= att['type'],url= att['url'], data=""))

        chat_id = msg['params']['chatId']
        msg_id = msg['id']
        human = msg['params']['human']
        params = msg['params']
        method = msg["method"]
        if msg["method"] == "form_submit":
            form = msg["params"].get("formData", {})
        else:
            form = {}



    init_state = NodeState(
        messages=[agent.card.id, chat_id, msg_id, task_id, msg_txt],
        input=msg_txt,
        attachments=atts,
        prompts=[],
        formatted_prompts=[],
        attributes={"human": human, "method": method, "params": params, "form": form},
        result={},
        tool_input={},
        tool_result={},
        threads=[],
        metadata={"form":form},
        error="",
        retries=3,
        condition=False,
        case="",
        goals=[]
    )

    if not current_state:
        return init_state
    else:
        current_state["attachments"] = atts
        current_state["messages"].append(msg_txt)
        return current_state