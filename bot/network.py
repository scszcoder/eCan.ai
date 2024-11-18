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
COMMANDER_UDP_PERIOD = 10
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
        self.msg_queue = topgui.getGuiMsgQueue()
        self.buffer = ""
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
        new_link = {"ip": self.peername[0], "port": self.peername[1], "name": hostname, "transport": transport}
        fieldLinks.append(new_link)
        print(f"now we have {len(fieldLinks)} field links")
        asyncio.create_task(self.msg_queue.put(self.peername[0] + "!connection!"+hostname))


    def data_received(self, data):
        try:
            # Append incoming data to the buffer
            self.buffer += data.decode()

            # Process each complete message in the buffer
            while "!ENDMSG!" in self.buffer:
                message, self.buffer = self.buffer.split("!ENDMSG!", 1)
                print("TCP received message:", message)

                # Enqueue the complete message
                asyncio.create_task(self.msg_queue.put(self.peername[0] + "!net data!" + message))

        except Exception as e:
            print(f"Error in data_received: {e}")

        # if not self.topgui == None:
        #     print("Queueing TCP recevied message:", message)
        #     asyncio.create_task(self.msg_queue.put(self.peername[0]+"!net data!"+message))


        #print('Send: {!r}'.format(message))
        #self.transport.write(data)

        #print('Close the client socket')
        # self.transport.close()

    def connection_lost(self, exc):
        print(f"Connection to {self.peername[0]} lost")

        # Find and delete from fieldLinks
        lostone = next((x for x in fieldLinks if x["ip"] == self.peername[0]), None)
        if lostone:  # Ensure that the link exists in the list before trying to remove it
            lostName = lostone["name"]
            fieldLinks.remove(lostone)
            print(f"Removed connection: {lostone['ip']} - {lostName}")

        # Notify the GUI about the lost connection
        asyncio.create_task(self.msg_queue.put(self.peername[0] + "!net loss!" + lostName))

        # Signal that the connection was lost, but only set it if it's not already done
        if not self.on_con_lost.done():
            self.on_con_lost.set_result(True)

# main platoon side communication protocol
class communicatorProtocol(asyncio.Protocol):
    def __init__(self, topgui, message, on_con_lost):
        self.buffer = bytearray()
        self.expected_length = None
        self.message = message
        self.on_con_lost = on_con_lost
        self.topgui = topgui
        self.msg_queue = topgui.getGuiMsgQueue()
        print("comm protocol initialized.....")

    def connection_made(self, transport):
        self.peername = transport.get_extra_info('peername')
        print('Connection from commander {}'.format(self.peername))
        ip_address = self.peername[0]
        try:
            hostname = socket.gethostbyaddr(ip_address)[0]
        except socket.herror:
            hostname = ""  # If no reverse DNS is available
        print(f'IP Address: {ip_address}, Hostname: {hostname}')

        self.transport = transport
        asyncio.create_task(self.msg_queue.put(ip_address + "!connection!" + hostname))


    def data_received(self, data):
        self.buffer.extend(data)
        print(f"Received commander data: {len(data)} bytes, Buffer size: {len(self.buffer)}")

        while self.buffer:
            if self.expected_length is None and len(self.buffer) >= 4:
                self.expected_length = int.from_bytes(self.buffer[:4], byteorder='big')
                self.buffer = self.buffer[4:]
                print(f"Got header length: {self.expected_length}")

            # Process the message only once the full expected length is received
            if self.expected_length is not None and len(self.buffer) >= self.expected_length:
                message = self.buffer[:self.expected_length]
                self.buffer = self.buffer[self.expected_length:]
                self.expected_length = None
                print(f"Full data packet received, length: {len(message)}")

                try:
                    json_data = json.loads(message.decode('utf-8'))
                    if json_data['cmd'] == "reqSendFile":
                        print(f"File received: {json_data['file_name']}")

                        # Check and correct base64 padding
                        file_contents = json_data['file_contents']
                        if len(file_contents) % 4 != 0:
                            print("Warning: Base64 data length is not a multiple of 4. Adding padding.")
                            file_contents += "=" * (4 - len(file_contents) % 4)

                        file_data = base64.b64decode(file_contents)
                        print(f"Decoded file data size after padding check: {len(file_data)}")

                        # Save the file to disk
                        fullfname = self._construct_file_path(json_data)
                        file_name = os.path.basename(fullfname)
                        dir_name = os.path.dirname(fullfname)

                        # new_fullname = dir_name + "/p_" + file_name
                        new_fullname = dir_name + "/" + file_name
                        with open(new_fullname, 'wb') as file:
                            file.write(file_data)
                            print(f"File {new_fullname} saved, size: {len(file_data)} bytes")
                    else:
                        print('Other data received:', message.decode('utf-8'))
                        asyncio.create_task(
                            self.msg_queue.put(self.peername[0] + "!net data!" + message.decode('utf-8')))

                except json.JSONDecodeError as e:
                    print("JSON decode error:", e)
            else:
                print(f"Filling buffer, current size: {len(self.buffer)}")
                break

    def _construct_file_path(self, json_data):
        fdir = os.path.dirname(json_data['file_name'])
        fname = os.path.basename(json_data['file_name'])

        if json_data["file_type"] == "ads profile":
            if utils.logger_helper.login:
                log_user = utils.logger_helper.login.getLogUser()
            else:
                log_user = 'anonymous'
            fullfdir = ecb_data_homepath + f"/{log_user}/ads_profiles/"
            fullfname = fullfdir + fname
        elif json_data["file_type"] == "skill psk":
            start_index = fdir.find("resource")
            half_path = fdir[start_index:]
            fullfdir = app_info.app_home_path + "/" + half_path + "/"
            fullfname = fullfdir + fname

        # Ensure the directory exists
        if not os.path.exists(fullfdir):
            os.makedirs(fullfdir)

        return fullfname

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
    topgui.setIP(myip)
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


async def udpBroadcaster(topgui):
    over = False

    hostname = socket.gethostname()
    myips = socket.gethostbyname_ex(hostname)[-1]
    myip = myips[len(myips)-1]

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
        print("Broadcasting...", 'Commander Calling:' + myip + " " + topgui.getUser())
        message = str.encode('Commander Calling:' + myip+":"+topgui.getUser())
        usock.sendto(message, ('192.168.0.255', UDP_PORT))
        await asyncio.sleep(COMMANDER_UDP_PERIOD)


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



class UDPServerProtocol:
    def __init__(self, loop, topgui):
        self.loop = loop
        self.topgui = topgui
        self.on_con_lost = loop.create_future()
        self.commander_connect_attempted = False

    def connection_made(self, transport):
        self.transport = transport
        print("Listenting for Commander...")

    def datagram_received(self, data, addr):
        print(f"Received data: {data.decode()} from {addr}")
        global commanderXport
        message = data.decode("utf-8")
        print(f"platoon received: {message}")

        myBoss = self.topgui.getUser()
        print("my boss:", myBoss)
        if "Commander" in message and  myBoss in message and commanderXport is None:
            rxmsg_parts = message.split(":")
            commanderIP = rxmsg_parts[1]
            print(f"received: {commanderIP}")

            if not self.commander_connect_attempted:
                print("create task to start tcp conn to commander....")
                self.loop.create_task(self.reconnect_to_commander(commanderIP))
                self.commander_connect_attempted = True


    async def reconnect_to_commander(self, commanderIP):
        global commanderXport
        print(f"Attempting to connect to Commander at IP: {commanderIP}, PORT: {TCP_PORT}")

        reconnect_attempts = 0
        max_retries = 17280    # 17280 x 5 = 86400 which is 24hrs. if net is lost for 24hrs, we really should restart the whole program......

        while reconnect_attempts < max_retries:
            try:
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
                self.topgui.setCommanderXPort(commanderXport)
                self.topgui.setIP(myips[-1])
                print(f"commanderXport created: {commanderXport}")

                # Wait for the connection to be lost
                await on_con_lost
                print("Connection to commander lost...")

            except Exception as e:
                print(f"Failed to connect to commander: {e}")
                reconnect_attempts += 1
                # Optionally add a delay between reconnection attempts
                await asyncio.sleep(5)

            finally:
                if commanderXport:
                    commanderXport.close()
                    commanderXport = None

            # Retry if the connection is lost
            print("Retrying connection...")

        print(f"Failed to reconnect after {max_retries} attempts.")
        # If max retri

async def platoonUDPServer(thisloop, topgui):
    print("Setting up UDP server...")
    hostname = socket.gethostname()
    myips = socket.gethostbyname_ex(hostname)[-1]
    platoon_ip = myips[-1]  # Use the last IP in the list or choose as appropriate

    commander_wait_not_timeout = COMMANDER_WAIT_TIMEOUT
    # Setup UDP server
    transport, protocol = await thisloop.create_datagram_endpoint(
        lambda: UDPServerProtocol(thisloop, topgui),
        local_addr=(platoon_ip, UDP_PORT)
    )
    print("UDP server kicked off....")
    try:
        # Keep the server running indefinitely
        while True:

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


async def runPlatoonLAN(topgui, thisLoop):

    await platoonUDPServer(thisLoop, topgui)
