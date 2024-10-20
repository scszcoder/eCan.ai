import asyncio
import json
import os.path

import selectors
import socket

import platform
import base64
from config.app_info import app_info
from config.app_settings import ecb_data_homepath
import utils.logger_helper

UDP_IP = "127.0.0.1"

UDP_PORT = 4868
TCP_PORT = 4898

MESSAGE = b"Hello, World!"
sel = selectors.DefaultSelector()

# UDP pack broadcasted every 15 second.
TICK = 30
COMMANDER_UDP_PERIOD = 5
PLATOON_UDP_PERIOD = 8
COMMANDER_WAIT_TIMEOUT = 8      # 8x8 = 64 seconds.

commanderXport = None
commanderIP = "0.0.0.0"
platoonProtocol = None
commanderServer = None
fieldLinks = []

myname = socket.gethostname()


class CommanderTCPServerProtocol(asyncio.Protocol):
    def __init__(self, topgui, on_con_lost):
        self.topgui = topgui
        self.on_con_lost = on_con_lost
        self.msg_queue = topgui.get_gui_msg_queue()
        print("tcp server protocol initialized....")

    def connection_made(self, transport):
        self.peername = transport.get_extra_info('peername')
        print('Connection from Platoon {}'.format(self.peername))
        ip_address = self.peername[0]
        try:
            hostname = socket.gethostbyaddr(ip_address)[0]
        except socket.herror:
            hostname = None  # If no reverse DNS is available
        print(f'IP Address: {ip_address}, Hostname: {hostname}')

        self.transport = transport
        new_link = {"ip": self.peername, "name": hostname, "transport": transport}
        fieldLinks.append(new_link)
        asyncio.create_task(self.msg_queue.put(self.peername[0] + "!connection!"+hostname))
        # if not self.topgui.mainwin == None:
        #     if self.topgui.mainwin.platoonWin == None:
        #         self.topgui.mainwin.platoonWin = PlatoonWindow(self.topgui.mainwin, "conn")
        #     self.topgui.mainwin.addVehicle(self)

    def data_received(self, data):
        message = data.decode()
        print("TCP recevied message:", message)
        if not self.topgui.main_win == None:
            print("Queueing TCP recevied message:", message)
            asyncio.create_task(self.msg_queue.put(self.peername[0]+"!net data!"+message))
            # self.topgui.mainwin.appendNetLogs(['Data received: {!r}'.format(message)])
            # self.topgui.mainwin.processPlatoonMsgs(message, self.peername)

        #print('Send: {!r}'.format(message))
        #self.transport.write(data)

        #print('Close the client socket')
        # self.transport.close()

    def connection_lost(self, exc):
        self.on_con_lost.set_result(True)
        #find and delete from fieldLinks
        lostone = next((x for x in fieldLinks if x["ip"] == self.peername), None)
        fieldLinks.remove(lostone)
        self.on_con_lost.set_result(True)
        asyncio.create_task(self.msg_queue.put(self.peername + "!net loss!"))


# main platoon side communication protocol
class communicatorProtocol(asyncio.Protocol):
    def __init__(self, topgui, message, on_con_lost):
        self.buffer = bytearray()
        self.expected_length = None
        self.message = message
        self.on_con_lost = on_con_lost
        self.topgui = topgui
        self.msg_queue = topgui.get_gui_msg_queue()
        print("comm protocol initialized.....")

    def connection_made(self, transport):
        self.peername = transport.get_extra_info('peername')
        print('Connection from commander {}'.format(self.peername))
        self.transport = transport
        asyncio.create_task(self.msg_queue.put(self.peername[0] + "!connection!"))

    def data_received(self, data):
        self.buffer.extend(data)
        print("recevied commander data::"+str(len(data)))
        while self.buffer:
            if self.expected_length is None and len(self.buffer) >= 4:
                # Read the length prefix
                self.expected_length = int.from_bytes(self.buffer[:4], byteorder='big')
                self.buffer = self.buffer[4:]  # Remove the length bytes from the buffer
                print("Got header length::" + str(self.expected_length))
            # Check if we have all data for the message
            if self.expected_length is not None and len(self.buffer) >= self.expected_length:
                # We have the full message
                message = self.buffer[:self.expected_length]
                self.buffer = self.buffer[self.expected_length:]  # Remove the message from the buffer
                self.expected_length = None
                print("Full data packet received")
                # Process the complete message
                try:
                    json_data = json.loads(message.decode('utf-8'))
                    # Now handle the JSON data
                    if json_data['cmd'] == "reqSendFile":
                        print('file received: '+json_data['file_name'])
                        file_data = base64.b64decode(json_data['file_contents'])

                        # Save the file data to a new file
                        fdir = os.path.dirname(json_data['file_name'])
                        fname = os.path.basename(json_data['file_name'])
                        if json_data["file_type"] == "ads profile":
                            if utils.logger_helper.login:
                                log_user = utils.logger_helper.login.getLogUser()
                            else:
                                log_user = 'anonymous'
                            fullfname = ecb_data_homepath + f"/{log_user}/ads_profiles/" + fname
                            fullfdir = ecb_data_homepath + f"/{log_user}/ads_profiles/"
                        elif json_data["file_type"] == "skill psk":
                            start_index = fdir.find("resource")
                            half_path = fdir[start_index:]
                            fullfdir = app_info.app_home_path + "/" + half_path + "/"
                            fullfname = fullfdir + fname

                        print(f'File DIR {fullfdir} checked')
                        # Ensure the directory exists
                        if not os.path.exists(fullfdir):
                            os.makedirs(fullfdir)  # Create any missing directories

                        with open(fullfname, 'wb') as file:
                            file.write(file_data)
                        print(f'File {fullfname} saved')
                    else:
                        print('Data received: {!r}'.format(message.decode('utf-8')))
                        asyncio.create_task(self.msg_queue.put(self.peername[0] + "!net data!" + message.decode('utf-8')))
                        # self.topgui.mainwin.processCommanderMsgs(message)
                except json.JSONDecodeError as e:
                    print("JSON decode error:", e)
            else:
                # Not enough data has been received yet
                print("filling buffer::" + str(len(self.buffer)))
                break

        # json_data = json.loads(data.decode('utf-8'))
        #
        # if json_data['cmd'] == "reqSendFile":
        #     print('file received: '+json_data['file_name'])
        #     file_data = base64.b64decode(json_data['file_contents'])
        #
        #     # Save the file data to a new file
        #     fdir = os.path.dirname(json_data['file_name'])
        #     fname = os.path.basename(json_data['file_name'])
        #     fullfname = fdir + "/temp/" + fname
        #
        #     # Ensure the directory exists
        #     if not os.path.exists(fdir + "/temp/"):
        #         os.makedirs(fdir + "/temp/")  # Create any missing directories
        #
        #     with open(fullfname, 'wb') as file:
        #         file.write(file_data)
        #     print(f'File {fullfname} saved')
        # else:
        #     message = data.decode()
        #     print('Data received: {!r}'.format(message))
        #     asyncio.create_task(self.msg_queue.put(self.peername[0] + "!net data!" + message))
        #     # self.topgui.mainwin.processCommanderMsgs(message)


        # print('Send: {!r}'.format(message))
        # self.transport.write(data)

    def connection_lost(self, exec):
        print("The commander is LOST....")
        self.on_con_lost.set_result(True)
        asyncio.create_task(self.msg_queue.put(self.peername[0] + "!net loss!"))


async def tcpServer(topgui):
    # Get a reference to the event loop as we plan to use
    # low-level APIs.
    hostname = socket.gethostname()
    myips = socket.gethostbyname_ex(hostname)[2]
    myip = myips[len(myips)-1]
    topgui.set_ip(myip)
    print("my host name is: ", hostname, " and my ip is: ", myip)
    tcp_loop = asyncio.get_running_loop()
    on_con_lost = tcp_loop.create_future()


    commanderServer = await tcp_loop.create_server(
        lambda: CommanderTCPServerProtocol(topgui, on_con_lost),
        myip, TCP_PORT)
    print("commanderServer: ", commanderServer)

    async with commanderServer:
        await commanderServer.serve_forever()

def udp_receiver():
    # Create a UDP socket
    usock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    usock.bind(('', UDP_PORT))

    while True:
        data, addr = usock.recvfrom(1024)
        print(f"Received data: {data.decode()} from {addr}")



# async def echo():
#     stdin, stdout = await aioconsole.get_standard_streams()
#     async for line in stdin:
#         stdout.write(line)

# loop = asyncio.get_event_loop()
# loop.run_until_complete(echo())

async def udpBroadcaster(topgui):
    over = False

    hostname = socket.gethostname()
    myips = socket.gethostbyname_ex(hostname)[-1]
    myip = myips[len(myips)-1]
    message = str.encode('Commander Calling:' + myip)

    usock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    # Enable port reusage so we will be able to run multiple clients and servers on single (host, port).
    # Do not use socket.SO_REUSEADDR except you using linux(kernel<3.9): goto https://stackoverflow.com/questions/14388706/how-do-so-reuseaddr-and-so-reuseport-differ for more information.
    # For linux hosts all sockets that want to share the same address and port combination must belong to processes that share the same effective user ID!
    # So, on linux(kernel>=3.9) you have to run multiple servers and clients under one user to share the same (host, port).
    # Thanks to @stevenreddie
    usock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Enable broadcasting mode
    usock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    while not over:
        # if not topgui.mainwin == None:
        #     topgui.mainwin.appendNetLogs(["broadcast"])
        print("Broadcasting...", 'Commander Calling:' + myip)
        # usock.sendto(message, ('255.255.255.255', UDP_PORT))
        usock.sendto(message, ('192.168.0.255', UDP_PORT))
        await asyncio.sleep(COMMANDER_UDP_PERIOD)
    #
    # message = data.decode()
    # print('Received %r from %s' % (message, addr))
    # print('Send %r to %s' % (message, addr))
    # self.transport.sendto(data, addr)

    # try:
    #     await asyncio.sleep(3600)  # Serve for 1 hour.
    # finally:
    #     transport.close()


async def udp_broadcast():
    udp_port = 4868
    broadcast_interval = 5

    message = "Hello, this is the server broadcasting its presence."

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    while True:
        sock.sendto(message.encode(), ('255.255.255.255', udp_port))
        print(f"Broadcast message sent every {broadcast_interval} seconds")
        await asyncio.sleep(broadcast_interval)


async def tcp_server():
    async def handle_echo(reader, writer):
        while True:
            data = await reader.read(100)
            message = data.decode()
            addr = writer.get_extra_info('peername')
            print(f"Received {message} from {addr}")
            if not data:
                break
            writer.write(data)
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle_echo, '192.168.1.111', 4898)
    addr = server.sockets[0].getsockname()
    print(f'Serving on {addr}')
    async with server:
        await server.serve_forever()


# this is the udp receiver on the platoon side.
# once received commander's UDP packet, start a tcp/ip task to communicate to/from commander via tcp
async def commanderFinder(topgui, thisloop, waitwin):
    global commanderXport
    over = False
    hostname = socket.gethostname()
    myips = socket.gethostbyname_ex(hostname)[-1]
    myip = myips[len(myips)-1]
    print("my IP is: ", myip)

    message = b'Commander Calling:'
    usock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    usock.bind(('', UDP_PORT))
    commander_wait_not_timeout = COMMANDER_WAIT_TIMEOUT
    while not over:
        print("listening for commander")
        data, addr = await thisloop.run_in_executor(None, usock.recvfrom, 1024)

        # rxmsg = usock.recvfrom(512)
        print("platoon received::", data.decode("utf-8"))

        # if "Commander" in rxmsg[0].decode("utf-8") and commanderXport == None:
        if "Commander" in data.decode("utf-8") and commanderXport is None:
            # commanderIP = rxmsg[1][0]
            rxmsg_parts = data.decode("utf-8").split(":")
            commanderIP = rxmsg_parts[1]
            print("recevied::", commanderIP)
            waitwin.close()
            topgui.show()

            loop = asyncio.get_running_loop()
            on_con_lost = loop.create_future()

            commanderXport, platoonProtocol = await loop.create_connection(
                lambda: communicatorProtocol(topgui, '', on_con_lost),
                commanderIP, TCP_PORT
            )
            topgui.set_xport(commanderXport)
            topgui.set_ip(myip)
            print("commanderXport created::", commanderXport)


            try:
                await on_con_lost
            finally:
                commanderXport.close()
            break

        await asyncio.sleep(PLATOON_UDP_PERIOD)
        if commander_wait_not_timeout:
            commander_wait_not_timeout = commander_wait_not_timeout - 1


class UDPServerProtocol:
    def __init__(self, loop, topgui, waitwin):
        self.loop = loop
        self.topgui = topgui
        self.waitwin = waitwin
        self.on_con_lost = loop.create_future()

    def connection_made(self, transport):
        self.transport = transport
        print("Listenting for Commander...")

    def datagram_received(self, data, addr):
        print(f"Received data: {data.decode()} from {addr}")
        global commanderXport
        message = data.decode("utf-8")
        print(f"platoon received: {message}")

        if "Commander" in message and commanderXport is None:
            rxmsg_parts = message.split(":")
            commanderIP = rxmsg_parts[1]
            print(f"received: {commanderIP}")
            if not self.topgui.getSignedIn():
                if self.waitwin.isVisible():
                    print("shut wait win...")
                    self.waitwin.close()
                if not self.topgui.isVisible():
                    print("show login win...")
                    self.topgui.show()
                    self.topgui.set_role("Platoon")

                print("create task to start tcp conn to commander....")
                self.loop.create_task(self.connect_to_commander(commanderIP))


    async def connect_to_commander(self, commanderIP):
        global commanderXport
        print(f"Attempting to connect to Commander at IP: {commanderIP}, PORT: {TCP_PORT}")

        # sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # sock.settimeout(10)
        # sock.connect((commanderIP, TCP_PORT))  # Blocking connection
        # print("commander IP:", commanderIP, "tcp port:", TCP_PORT)
        # # Set the socket to non-blocking and integrate it into the asyncio loop
        # sock.setblocking(False)
        loop = asyncio.get_running_loop()
        on_con_lost = loop.create_future()

        commanderXport, platoonProtocol = await loop.create_connection(
            lambda: communicatorProtocol(self.topgui, '', on_con_lost),
            commanderIP, TCP_PORT)

        # # Use the socket directly in the create_connection call (without specifying host/port)
        # commanderXport, platoonProtocol = await self.loop.create_connection(
        #     lambda: CommunicatorProtocol(self.topgui, '', self.on_con_lost),
        #     sock=sock)
        hostname = socket.gethostname()
        myips = socket.gethostbyname_ex(hostname)[-1]
        self.topgui.set_xport(commanderXport)
        self.topgui.set_ip(myips[-1])
        print(f"commanderXport created: {commanderXport}")

        try:
            await self.on_con_lost
        finally:
            commanderXport.close()

    # def error_received(self, exc):
    #     print(f"Error received: {exc}")
    #
    # def connection_lost(self, exc):
    #     print("Connection lost")

async def platoonUDPServer(thisloop, topgui, waitwin):
    print("Setting up UDP server...")
    topGuiNotYetChecked = True
    hostname = socket.gethostname()
    myips = socket.gethostbyname_ex(hostname)[-1]
    platoon_ip = myips[-1]  # Use the last IP in the list or choose as appropriate

    commander_wait_not_timeout = COMMANDER_WAIT_TIMEOUT
    # Setup UDP server
    transport, protocol = await thisloop.create_datagram_endpoint(
        lambda: UDPServerProtocol(thisloop, topgui, waitwin),
        local_addr=(platoon_ip, UDP_PORT)
    )
    print("UDP server kicked off....")
    try:
        # Keep the server running indefinitely
        while True:
            if not commander_wait_not_timeout:
                # stop wait anxiety, and show the main GUI anyways.
                if not topgui.getSignedIn() and topGuiNotYetChecked:
                    waitwin.close()
                    topgui.show()
                    topgui.set_role("Platoon")
                    topGuiNotYetChecked = False

            await asyncio.sleep(PLATOON_UDP_PERIOD)
            if commander_wait_not_timeout:
                print("commander wait tick....")
                commander_wait_not_timeout = commander_wait_not_timeout - 1

            # Sleep for an hour
    except asyncio.CancelledError:
        pass
    finally:
        transport.close()



async def runCommanderLAN(topgui):
    await asyncio.gather(
        udpBroadcaster(topgui),
        tcpServer(topgui),
        # tcp_server(),
        # udp_broadcast(),
    )


async def runPlatoonLAN(topgui, thisLoop, waitwin):
    # await asyncio.gather(
    #     commanderFinder(topgui, thisLoop, waitwin, topgui.get_msg_queue()),
    #     # topScheduler(topgui, net_queue),
    # )
    # await commanderFinder(topgui, thisLoop, waitwin)
    await platoonUDPServer(thisLoop, topgui, waitwin)
