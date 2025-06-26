
def init_search_1688_chatter_skill(agent, msg, file_names=[]):
    msg_txt = msg.params.message.parts[0].text
    msg_txt = "I have three files here, please describe to me the contents of each of these files in detail."
    print("init task with message text:", msg_txt)
    if file_names:
        file_names = ["C:/Users/songc/PycharmProjects/ecbot/test0.png", "C:/Users/songc/PycharmProjects/ecbot/test1.pdf", "C:/Users/songc/PycharmProjects/ecbot/test2.wave"]  # Or generated dynamically
        # image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wisconsin-madison-the-nature-boardwalk.jpg/2560px-Gfp-wisconsin-madison-the-nature-boardwalk.jpg"
        # image_data = base64.b64encode(httpx.get(image_url).content).decode("utf-8")

        attachments = []
        for fname in file_names:
            with open(fname, "rb") as f:
                attachments.append({"filename": fname, "file_url": "", "file_data": f.read()})

        init_state = {
            "messages": [agent.card.id, msg_txt],
            "input": msg_txt,
            "attachments": attachments
        }
    else:
        init_state  = {
            "messages": [agent.card.id, msg_txt],
            "input": msg_txt,
            "attachments": []
        }

    return init_state

