
from bot.Cloud import upload_file, req_cloud_read_screen, upload_file8, send_rag_store_request_to_cloud


# skill for enter documents to vector DB
def storeDocToVectorDB(session, token, sfile, pid, ftype, version):
    upload_file(session, sfile, token, "rag txt")
    reqs = []
    for f in [sfile]:
        req = {
            "fid": " ",
            "pid": pid,
            "file": sfile,
            "type": ftype,
            "format": "",
            "options": "",
            "version": version
        }
        reqs.append(req)
    send_rag_store_request_to_cloud(session, reqs, token)
