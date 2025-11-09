from agent.cloud_api.cloud_api import upload_file, req_cloud_read_screen, upload_file8, send_rag_store_request_to_cloud


# skill for enter documents to vector DB
def storeDocToVectorDB(mission, session, token, ragReqs):
    mainwin = mission.get_main_win()
    reqs = []
    for rag in [ragReqs]:
        # upload_file(session, rag["file"], token,  mainwin.getWanApiEndpoint(), "rag txt")
        req = {
            "fid": rag["fid"],
            "pid": rag["pid"],
            "file": rag["file"],
            "type": rag["type"],
            "format": rag["format"],
            "options": rag["options"],
            "version": rag["version"]
        }
        reqs.append(req)
    send_rag_store_request_to_cloud(session, reqs, token, mainwin.getWanApiEndpoint())
