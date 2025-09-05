from agent.ec_skill import NodeState
from agent.ec_skills.llm_utils.llm_utils import try_parse_json

# whatever attachments should have been saved, read, packaged into the right form by the human twin agent
# and sent over via A2A, by the time we get them here, they'are already in the msg object
def prep_search_parts_chatter_skill(agent, msg, current_state=None):
    print("prep_search_parts_chatter_skill", type(msg), msg)  # msg.params.message[0].text
    # msg_txt = "I have three files here, please describe to me the contents of each of these files in detail."
    msg_parts = msg.params.message.parts
    attachments = []
    msg_txt = ""
    for part in msg_parts:
        if part.type == "text":
            msg_txt = part.text
        elif part.type == "file":
            attachments.append({"filename": part.file.name, "file_url": part.file.uri, "mime_type": part.file.mimeType,
                                "file_data": part.file.bytes})

    chat_id = msg.params.metadata["chatId"]
    msg_id = msg.id
    init_state = NodeState(
        messages=[agent.card.id, chat_id, msg_id, "", msg_txt],
        input=msg_txt,
        attachments=attachments,
        prompts=[],
        formatted_prompts=[],
        attributes={
            "preliminary_info": [
                {
                    "part name": "LDO",  # ✅ valid
                    "oems": ["NA"],  # ✅ valid
                    "model_part_numbers": ["NA"],  # ✅ valid
                    "applications_usage": "12V to 3V usb hand warmer",  # ✅ valid
                    "usage_grade": "NA"  # ✅ valid
                }
            ],
            "extra_info": [],
        },
        result={},
        tool_input={},
        tool_result={},
        threads = [],
        metadata = {},
        error="",
        retries=3,
        condition=False,
        case="",
        goals=[]
    )
    if not current_state:
        return init_state
    else:
        data = try_parse_json(msg_txt)
        if isinstance(data, dict):
            if data.get("type", "") == "normal":
                print("saving filled parametric filter form......")
                current_state["attributes"]["filled_parametric_filter"] = data
            elif data.get("type", "") == "score":
                print("saving filled fom form......")
                current_state["attributes"]["filled_fom_form"] = data
        current_state["attachments"] = attachments
        current_state["messages"].append(msg_txt)

        return current_state
