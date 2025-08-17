


def prep_search_1688_skill(agent, msg, file_names=[]):
    msg_txt = msg.params.message.parts[0].text
    print("init task with message text:", msg_txt)
    if file_names:
        file_names = ["report1.pdf", "report2.pdf", "report3.pdf"]  # Or generated dynamically

        attachments = []
        for fname in file_names:
            with open(fname, "rb") as f:
                attachments.append({"filename": fname, "content": f.read()})

        init_state = {
            "messages": [agent.card.id, msg_txt],
            "input": msg_txt,
            "attachments": attachments,
            "attributes": {"url": "https://www.1688.com"}
        }
    else:
        init_state  = {
            "messages": [agent.card.id, msg_txt],
            "input": msg_txt,
            "attributes": {"url": "https://www.1688.com"}
        }

    return init_state

