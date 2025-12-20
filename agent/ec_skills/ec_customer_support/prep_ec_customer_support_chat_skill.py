

def prep_ec_customer_support_chat_skill(agent, task_id, msg, current_state=None):
    msg_txt = msg.params.message.parts[0].text
    print("init task with message text:", msg_txt)
    file_names = current_state.get("attachments", [])
    if file_names:
        file_names = ["report1.pdf", "report2.pdf", "report3.pdf"]  # Or generated dynamically

        attachments = []
        for fname in file_names:
            with open(fname, "rb") as f:
                attachments.append({"filename": fname, "content": f.read()})

        init_state = {
            "messages": [agent.card.id, "", "", task_id, msg_txt],
            "input": msg_txt,
            "attachments": attachments
        }
    else:
        init_state  = {
            "messages": [agent.card.id, "", "", task_id, msg_txt],
            "input": msg_txt
        }

    return init_state
