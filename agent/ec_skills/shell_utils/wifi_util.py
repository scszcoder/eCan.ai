import os

def wifi_reconnect():
    try:
        os.system("netsh wlan disconnect")
        os.system("netsh wlan connect name=" + "")
    except Exception as e:
        print(e)