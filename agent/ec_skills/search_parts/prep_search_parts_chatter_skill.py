from agent.ec_skill import NodeState
from agent.ec_skills.llm_utils.llm_utils import try_parse_json
import json
import ast

# whatever attachments should have been saved, read, packaged into the right form by the human twin agent
# and sent over via A2A, by the time we get them here, they'are already in the msg object
def prep_search_parts_chatter_skill(agent, task_id, msg, current_state=None):
    logger.debug("prep_search_parts_chatter_skill", type(msg), msg)  # msg.params.message[0].text
    # msg_txt = "I have three files here, please describe to me the contents of each of these files in detail."
    if not isinstance(msg, dict):
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
        form = msg.params.metadata.get("form", {})
        msg_id = msg.id
    else:
        chat_id = ""
        msg_id = ""
        msg_txt = ""
        attachments = []

    init_state = NodeState(
        messages=[agent.card.id, chat_id, msg_id, task_id, msg_txt],
        input=msg_txt,
        attachments=attachments,
        prompts=[],
        history=[],
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
        logger.debug("prep_search_parts_chatter_skill: set init state")
        return init_state
    else:
        logger.debug("prep_search_parts_chatter_skill: set to resume")
        data = try_parse_json(msg_txt)
        if isinstance(data, dict):
            if data.get("type", "") == "normal":
                logger.debug("saving filled parametric filter form......")
                current_state["attributes"]["filled_parametric_filter"] = data
            elif data.get("type", "") == "score":
                logger.debug("saving filled fom form......")
                current_state["attributes"]["filled_fom_form"] = data
        current_state["attachments"] = attachments
        current_state["messages"].append(msg_txt)

        if msg.get("workType", "") == "rerank_search_results":
            try:
                # Parse Python dictionary string (not JSON) using ast.literal_eval
                results_str = msg.get("results", "{}")
                results_dict = ast.literal_eval(results_str)
                ranked_results = results_dict.get("ranked_results", [])
                current_state["tool_result"] = ranked_results
                current_state["attributes"]["rank_results"] = ranked_results
                current_state["attributes"]["i_tag"] = msg.get("taskID", "")
            except (ValueError, SyntaxError) as e:
                logger.error(f"Error parsing results: {e}")
                current_state["tool_result"] = []
                current_state["attributes"]["rank_results"] = []
                current_state["attributes"]["i_tag"] = msg.get("taskID", "")
        return current_state
