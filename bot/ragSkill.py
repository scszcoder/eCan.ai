
from bot.Cloud import upload_file, req_cloud_read_screen, upload_file8, send_rag_store_request_to_cloud


# skill for enter documents to vector DB
def storeDocToVectorDB(session, token, ragReqs):

    reqs = []
    for rag in [ragReqs]:
        # upload_file(session, rag["file"], token, "rag txt")
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
    send_rag_store_request_to_cloud(session, reqs, token)
