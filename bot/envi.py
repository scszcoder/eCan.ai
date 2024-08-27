# taken from stackoverflow
# https://stackoverflow.com/questions/5227107/python-code-to-read-registry

from config.app_info import app_info

# import errno, os, winreg
# proc_arch = os.environ['PROCESSOR_ARCHITECTURE'].lower()
#proc_arch64 = os.environ['PROCESSOR_ARCHITEW6432'].lower()

# def getECBotHome():
#     ecbhome = ""
#     print(proc_arch)
# #    print(proc_arch64)
# #     if proc_arch == 'x86' and not proc_arch64:
# #         arch_keys = {0}
# #    elif proc_arch == 'x86' or proc_arch == 'amd64':
#     if proc_arch == 'x86' or proc_arch == 'amd64':
#         arch_keys = {winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY}
#     else:
#         raise Exception("Unhandled arch: %s" % proc_arch)
#
#     print("arch_keys: ", arch_keys)
#
#     for arch_key in arch_keys:
#         key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ | arch_key)
#         # print("key: ", key)
#         # print("range: ", winreg.QueryInfoKey(key)[0])
#
#         try:
#             ecbhome = winreg.QueryValueEx(key, 'ECBOT_HOME')[0]
#         except OSError as e:
#             if e.errno == errno.ENOENT:
#                 # DisplayName doesn't exist in this skey
#                 pass
#         finally:
#             key.Close()
#             ecbhome = ecbhome.replace('\\', '/')
#             print("ECBot Home: ", ecbhome)
#             return ecbhome

def getECBotDataHome():
#     ecb_data_home = ""
#     print(proc_arch)
# #    print(proc_arch64)
# #     if proc_arch == 'x86' and not proc_arch64:
# #         arch_keys = {0}
# #    elif proc_arch == 'x86' or proc_arch == 'amd64':
#     if proc_arch == 'x86' or proc_arch == 'amd64':
#         arch_keys = {winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY}
#     else:
#         raise Exception("Unhandled arch: %s" % proc_arch)
#
#     print("arch_keys: ", arch_keys)
#
#     for arch_key in arch_keys:
#         key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ | arch_key)
#         # print("key: ", key)
#         # print("range: ", winreg.QueryInfoKey(key)[0])
#
#         try:
#             ecb_data_home = winreg.QueryValueEx(key, 'ECBOT_DATA_HOME')[0]
#         except OSError as e:
#             if e.errno == errno.ENOENT:
#                 # DisplayName doesn't exist in this skey
#                 pass
#         finally:
#             key.Close()
#             ecb_data_home = ecb_data_home.replace('\\', '/')
#             print("ECBot DATA Home: ", ecb_data_home)
#             return ecb_data_home
    return app_info.appdata_path
