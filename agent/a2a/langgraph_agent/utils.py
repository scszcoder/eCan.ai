
import traceback
import socket

def get_lan_ip():
    try:
        # Connect to an external address, but don't actually send anything
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Google's DNS IP
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"  # fallback

def get_a2a_server_url(mainwin):
    try:
        host = get_lan_ip()
        free_ports = mainwin.get_free_agent_ports(1)
        print("getting a2a  serer ports:", host, free_ports)
        if not free_ports:
            return None
        a2a_server_port = free_ports[0]
        url=f"http://{host}:{a2a_server_port}"
        print("a2a server url:", url)

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorGetA2AServerURL:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorGetA2AServerURL: traceback information not available:" + str(e)
        mainwin.showMsg(ex_stat)
        return ""
    return url







