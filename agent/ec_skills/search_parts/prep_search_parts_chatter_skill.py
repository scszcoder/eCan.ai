
# whatever attachments should have been saved, read, packaged into the right form by the human twin agent
# and sent over via A2A, by the time we get them here, they'are already in the msg object
def prep_search_parts_chatter_skill(agent, msg):
    print("init_search_parts_chatter_skill", type(msg), msg)  # msg.params.message[0].text
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

    init_state = {
        "messages": [agent.card.id, msg_txt],
        "input": msg_txt,
        "attachments": attachments
    }
    return init_state

