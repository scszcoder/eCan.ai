def init_my_twin_chatter_skill(agent, msg):
    print("init_my_twin_chatter_skill", type(msg), msg)
    mesg = msg['params']['message'][0]
    msg_txt = mesg['content']
    print("init task with message text:", msg_txt)
    if mesg['attachments']:
        file_names = [f['file'] for f in mesg['attachments']]  # [f['file'] for f in mesg['attachments'] if f['file'].endswith('.png')]  # [f['file for f in mesg['attachments']]  # Or generated dynamically
        # image_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wisconsin-madison-the-nature-boardwalk.jpg/2560px-Gfp-wisconsin-madison-the-nature-boardwalk.jpg"
        # image_data = base64.b64encode(httpx.get(image_url).content).decode("utf-8")

        attachments = []
        for fname in file_names:
            # print("reading file:", fname)
            fext = fname.split(".")[-1].lower()
            if fext in ['bitmap', 'gif', 'jpeg', 'jpg', 'png', 'gif', 'webp']:
                mtype = "image/"+fext
            elif fext in ['mp3', 'wav']:
                mtype = "audio/"+fext
            else:
                mtype = "application/"+fext

            with open(fname, "rb") as f:
                fake_url = ""
                # fake_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wisconsin-madison-the-nature-boardwalk.jpg/2560px-Gfp-wisconsin-madison-the-nature-boardwalk.jpg"
                fdata = f.read()
                # fdata = ""
                attachments.append({"filename": fname, "file_url": fake_url, "mime_type": mtype, "file_data": fdata})

        init_state = {
            "messages": [agent.card.id, msg_txt],
            "input": msg_txt,
            "attachments": attachments
        }
    else:
        init_state = {
            "messages": [agent.card.id, msg_txt],
            "input": msg_txt,
            "attachments": []
        }

    return init_state