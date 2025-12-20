import asyncio
import json
import os.path

import selectors
import socket

import platform
import base64

from app_context import AppContext
from config.app_info import app_info
from config.app_settings import ecb_data_homepath
import utils.logger_helper
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback

UDP_IP = "127.0.0.1"

UDP_PORT = 4868
TCP_PORT = 4898

MESSAGE = b"Hello, World!"
sel = selectors.DefaultSelector()

# UDP pack broadcasted every 15 second.
TICK = 30
COMMANDER_UDP_PERIOD = 10
PLATOON_UDP_PERIOD = 8
COMMANDER_WAIT_TIMEOUT = 8  # 8x8 = 64 seconds.

commanderXport = None
commanderIP = "127.0.0.1"
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
        self.transport = None
        print("tcp server protocol initialized....")

    def connection_made(self, transport):
        self.peername = transport.get_extra_info('peername')
        logger.debug('[CommanderTCPServerProtocol] Connection from Platoon {}'.format(self.peername), "tcpip", self.topgui)
        ip_address = self.peername[0]
        self.transport = transport
        try:
            hostname = socket.gethostbyaddr(ip_address)[0]
        except socket.herror:
            hostname = None  # If no reverse DNS is available
        logger.debug(f'[CommanderTCPServerProtocol] IP Address: {ip_address}, Hostname: {hostname}', "tcpip", self.topgui)

        self.transport = transport
        new_link = {"ip": self.peername[0], "port": self.peername[1], "name": hostname, "transport": transport}
        fieldLinks.append(new_link)
        logger.debug(f"[CommanderTCPServerProtocol] now we have {len(fieldLinks)} field links")
        asyncio.create_task(self.msg_queue.put(self.peername[0] + "!connection!" + hostname))

    def send_data(self, data):
        """ Safe transport write function """
        if self.transport is None or self.transport.is_closing():
            logger.debug("[CommanderTCPServerProtocol][send_data] Transport is unavailable or closing. Cannot send data.")
            return

        try:
            self.transport.write(data)
        except Exception as e:
            logger.debug(f"Error writing to transport: {e}")

    def data_received(self, data):
        try:
            # Decode the incoming data safely with error handling
            decoded_data = data.decode('utf-8', errors='ignore')

            # Append incoming decoded data to the buffer
            self.buffer += decoded_data

            # Process each complete message in the buffer
            while "!ENDMSG!" in self.buffer:
                message, self.buffer = self.buffer.split("!ENDMSG!", 1)
                if len(message) < 128:
                    print("TCP received message (raw):", message)
                else:
                    print("TCP received message (raw): ...", message[-127:])

                # Find the first '{' to clean up any junk before the JSON
                start_index = message.find('{')

                # Clean the message by slicing from the first '{'
                if start_index != -1:
                    clean_message = message[start_index:]
                else:
                    clean_message = message  # No '{' found, keep the original message

                # Handle concatenated JSONs
                while clean_message.strip():
                    try:
                        # Attempt to parse the first JSON object
                        json_obj, end_index = json.JSONDecoder().raw_decode(clean_message)

                        # Enqueue the parsed JSON object
                        asyncio.create_task(self.msg_queue.put(self.peername[0] + "!net data!" + json.dumps(json_obj)))

                        # Remove the processed JSON from the clean_message
                        clean_message = clean_message[end_index:].lstrip()
                    except json.JSONDecodeError:
                        # Break the loop if no more valid JSON objects can be decoded
                        break

        except UnicodeDecodeError as e:
            # Handle decoding errors gracefully
            print(f"Error decoding data: {e}. Skipping this chunk of data.")
        except Exception as e:
            # Handle unexpected errors
            print(f"Unexpected error in data_received: {e}")

    #
    # def data_received(self, data):
    #     try:
    #         # Append incoming data to the buffer
    #         self.buffer += data.decode()
    #
    #         # Process each complete message in the buffer
    #         while "!ENDMSG!" in self.buffer:
    #             message, self.buffer = self.buffer.split("!ENDMSG!", 1)
    #             print("TCP received message:", message)
    #             start_index = message.find('{')
    #
    #             # Clean the message by slicing from the first '{'
    #             if start_index != -1:
    #                 clean_message = message[start_index:]
    #             else:
    #                 clean_message = message  # No '{' found, keep the original message
    #
    #             # Enqueue the complete message
    #             asyncio.create_task(self.msg_queue.put(self.peername[0] + "!net data!" + clean_message))
    #
    #     except Exception as e:
    #         print(f"Error in data_received: {e}")

    # if not self.topgui == None:
    #     print("Queueing TCP recevied message:", message)
    #     asyncio.create_task(self.msg_queue.put(self.peername[0]+"!net data!"+message))

    # print('Send: {!r}'.format(message))
    # self.transport.write(data)

    # print('Close the client socket')
    # self.transport.close()

    def connection_lost(self, exc):
        logger.debug(f"Connection to {self.peername[0]} lost", "tcpip", self.topgui)

        # Find and delete from fieldLinks
        lostone = next((x for x in fieldLinks if x["ip"] == self.peername[0]), None)
        if lostone:  # Ensure that the link exists in the list before trying to remove it
            lostName = lostone["name"]
            fieldLinks.remove(lostone)
            logger.debug(f"Removed connection: {lostone['ip']} - {lostName}", "tcpip", self.topgui)

        # Notify the GUI about the lost connection
        asyncio.create_task(self.msg_queue.put(self.peername[0] + "!net loss!" + lostName))

        # Signal that the connection was lost, but only set it if it's not already done
        if not self.on_con_lost.done():
            self.on_con_lost.set_result(True)


# main platoon side communication protocol
class CommunicatorProtocol(asyncio.Protocol):
    def __init__(self, topgui, message, on_con_lost):
        self.buffer = bytearray()
        self.expected_length = None
        self.message = message
        self.on_con_lost = on_con_lost
        self.topgui = topgui
        self.msg_queue = topgui.getGuiMsgQueue()
        self.transport = None
        print("comm protocol initialized.....")

    def connection_made(self, transport):
        self.peername = transport.get_extra_info('peername')
        logger.debug('Connection from commander {}'.format(self.peername), "tcpip", self.topgui)
        ip_address = self.peername[0]
        self.transport = transport
        try:
            hostname = socket.gethostbyaddr(ip_address)[0]
        except socket.herror:
            hostname = ""  # If no reverse DNS is available
        self.topgui.setCommanderName(hostname)
        print(f'IP Address: {ip_address}, Hostname: {hostname}')

        asyncio.create_task(self.msg_queue.put(ip_address + "!connection!" + hostname))

    def send_data(self, data):
        """ Safe transport write function """
        if self.transport is None or self.transport.is_closing():
            print("Transport is unavailable or closing. Cannot send data.")
            return

        try:
            print("write transport....")
            self.transport.write(data)
        except Exception as e:
            print(f"Error writing to transport: {e}")

    def set_transport(self, transport):
        """ Manually assign transport (needed for asyncio.open_connection) """
        self.transport = transport

    def data_received(self, data):
        self.buffer.extend(data)
        print(
            f"Platoon TCP Received commander data: {len(data)} bytes, expected_length: {self.expected_length}, Buffer size: {len(self.buffer)}")

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
                        decodedMsg = message.decode('utf-8')
                        if len(decodedMsg) < 128:
                            print('none file data received:' + json_data['cmd'] + " ..." + decodedMsg)
                        else:
                            print('none file data received:' + json_data['cmd'] + " ..." + decodedMsg[-127:])
                        asyncio.create_task(
                            self.msg_queue.put(self.peername[0] + "!net data!" + decodedMsg))

                except json.JSONDecodeError as e:
                    print("JSON decode error:", e)
            else:
                print(f"Filling buffer, current size: {len(self.buffer)}")
                break

    def _construct_file_path(self, json_data):
        fdir = os.path.dirname(json_data['file_name'])
        fname = os.path.basename(json_data['file_name'])
        print("json_data:", json_data['file_name'])
        dir_names = os.path.normpath(fdir).split(os.sep)

        if json_data["file_type"] == "ads profile":
            if AppContext.login:
                log_user = AppContext.getLogUser()
            else:
                log_user = 'anonymous'
            fullfdir = ecb_data_homepath + f"/{log_user}/ads_profiles/"
            fullfname = fullfdir + fname
        elif json_data["file_type"] == "skill psk":
            if "my_skills" in fdir:
                target_dir_level = 2
                target_index = len(dir_names) - target_dir_level - 1  # Adjust for 0-based indexing
                # Construct the relative path, starting from the target directory
                relative_path = os.path.join(*dir_names[target_index:])

                print("relative_path:", dir_names, target_index, relative_path)

                # Combine the prefix and relative path
                fullfdir = os.path.join(app_info.app_home_path, relative_path)
                fullfname = os.path.join(fullfdir, fname)
            else:
                start_index = fdir.find("resource")
                half_path = fdir[start_index:]
                fullfdir = app_info.app_home_path + "/" + half_path + "/"
                fullfname = fullfdir + fname
                print("half path", fdir, start_index, half_path, fullfdir, fullfname)

        else:
            print("unknow file type")

        # Ensure the directory exists
        if not os.path.exists(fullfdir):
            os.makedirs(fullfdir)

        print("fullfdir:", fullfdir, fullfname)
        return fullfname

    def connection_lost(self, exec):
        logger.debug("The commander is LOST....", "tcpip", self.topgui)
        self.on_con_lost.set_result(True)
        asyncio.create_task(self.msg_queue.put(self.peername[0] + "!net loss!"))


async def tcpServer(topgui):
    # Get a reference to the event loop as we plan to use
    # low-level APIs.
    hostname = socket.gethostname()
    myips = socket.gethostbyname_ex(hostname)[2]
    myip = myips[len(myips) - 1]
    topgui.setIP(myip)
    logger.info("my host name is: ", hostname, " and my ip is: ", myip)
    tcp_loop = asyncio.get_running_loop()
    on_con_lost = tcp_loop.create_future()

    commanderServer = await tcp_loop.create_server(
        lambda: CommanderTCPServerProtocol(topgui, on_con_lost),
        myip, TCP_PORT)
    logger.info("commanderServer: ", commanderServer)

    async with commanderServer:
        await commanderServer.serve_forever()


def udp_receiver(stop_event=None):
    """
    UDP receiver with graceful shutdown support

    Args:
        stop_event: threading.Event to signal when to stop
    """
    # Create a UDP socket
    usock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    usock.bind(('', UDP_PORT))
    # Set timeout to allow checking stop_event
    usock.settimeout(1.0)

    try:
        while stop_event is None or not stop_event.is_set():
            try:
                data, addr = usock.recvfrom(1024)
                print(f"Received data: {data.decode()} from {addr}")
            except socket.timeout:
                # Timeout is normal, continue loop
                continue
            except Exception as e:
                print(f"UDP receive error: {e}")
                break
    finally:
        usock.close()
        print("UDP receiver closed")


async def udpBroadcaster(topgui):
    over = False

    hostname = socket.gethostname()
    myips = socket.gethostbyname_ex(hostname)[-1]
    myip = myips[len(myips) - 1]

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
        logger.debug("Broadcasting..." + 'Commander Calling:' + myip + " " + topgui.getUser(), "tcpip", topgui)
        if "Commander" in topgui.host_role:
            logger.debug("sending as commander....")
            message = str.encode('Commander Calling:' + myip + ":" + topgui.getUser())
        elif "Staff" in topgui.host_role:
            message = str.encode('Staff Officer Calling:' + myip + ":" + topgui.getUser())
        else:
            message = str.encode('Platoon Calling:' + myip + ":" + topgui.getUser())

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
        self.active_reconnect_task = None

    def connection_made(self, transport):
        self.transport = transport
        logger.debug("[UDPServerProtocol][connection_made] Listenting for Commander...")

    def datagram_received(self, data, addr):
        logger.debug(f"Received UDP data: {data.decode()} from {addr}")
        global commanderXport
        message = data.decode("utf-8")
        logger.debug(f"[UDPServerProtocol][connection_made] platoon UDP received: {message}")

        myBoss = self.topgui.getUser()
        print("my boss:", myBoss)
        if "Commander" in message and myBoss in message and commanderXport is None:
            rxmsg_parts = message.split(":")
            commanderIP = rxmsg_parts[1]
            logger.debug(f"[UDPServerProtocol][connection_made] received commander IP: {commanderIP}")

            if not self.commander_connect_attempted:
                logger.debug("[UDPServerProtocol][connection_made] create task to start tcp conn to commander....")
                # self.loop.create_task(self.reconnect_to_commander(commanderIP))
                self.commander_connect_attempted = True
                if self.active_reconnect_task is None or self.active_reconnect_task.done():
                    self.active_reconnect_task = self.loop.create_task(self.reconnect_to_commander(commanderIP))
        elif "MILAN" in message:
            rxmsg_parts = message.split(":")
            milanServerIP = rxmsg_parts[1].strip()
            logger.debug(f"[UDPServerProtocol][connection_made] received milan server IP: {milanServerIP}")
            self.topgui.setMILANServer(milanServerIP)

        elif "LANDB" in message:
            rxmsg_parts = message.split(":")
            lanDBServerIP = rxmsg_parts[1]
            logger.debug(f"[UDPServerProtocol][connection_made] received lan DB server IP: {lanDBServerIP}")
            self.topgui.setLanDBServer(lanDBServerIP)

    def error_received(self, exc):
        """Optional UDP error callback to satisfy Datagram Protocol interface."""
        try:
            logger.debug(f"[UDPServerProtocol][error_received] UDP server error received: {exc}", "tcpip", self.topgui)
        except Exception:
            pass

    def connection_lost(self, exc):
        """Handle UDP transport close gracefully to avoid AttributeError on shutdown."""
        try:
            logger.debug("[UDPServerProtocol][connection_lost] UDP server transport closed", "tcpip", self.topgui)
            if self.on_con_lost and not self.on_con_lost.done():
                self.on_con_lost.set_result(True)
        except Exception:
            pass

    async def reconnect_to_commander(self, commanderIP):
        global commanderXport

        reconnect_attempts = 0
        max_retries = 17280  # 17280 x 5 = 86400 which is 24hrs. if net is lost for 24hrs, we really should restart the whole program......

        if commanderXport is not None and not commanderXport.is_closing():
            logger.debug("[UDPServerProtocol][reconnect_to_commander] Already connected to Commander. Skipping reconnection.", "tcpip", self.topgui)
            return

        while reconnect_attempts < max_retries:
            try:
                if commanderXport is not None and not commanderXport.is_closing():
                    logger.debug(f"[UDPServerProtocol][reconnect_to_commander] Transport is still active. Skipping reconnection.")
                    return  # Avoid reconnecting if transport is still alive

                loop = asyncio.get_running_loop()
                on_con_lost = loop.create_future()
                logger.debug(f"[UDPServerProtocol][reconnect_to_commander] Attempting to connect to Commander at IP: {commanderIP}, PORT: {TCP_PORT}")

                # Ensure previous transport is closed before reconnecting
                if commanderXport:
                    logger.debug("[UDPServerProtocol][reconnect_to_commander] closing transport....", "tcpip", self.topgui)
                    commanderXport.close()
                    commanderXport = None

                commanderXport, platoonProtocol = await loop.create_connection(
                    lambda: CommunicatorProtocol(self.topgui, '', on_con_lost),
                    commanderIP, TCP_PORT)

                hostname = socket.gethostname()
                myips = socket.gethostbyname_ex(hostname)[-1]
                self.topgui.setCommanderXPort(commanderXport)
                self.topgui.setIP(myips[-1])
                logger.debug(f"[UDPServerProtocol][reconnect_to_commander] commanderXport created: {commanderXport}", "tcpip", self.topgui)

                # Wait for the connection to be lost
                await on_con_lost
                logger.debug("[UDPServerProtocol][reconnect_to_commander] Connection to commander lost...", "tcpip", self.topgui)

            except Exception as e:
                # Get the traceback information
                ex_stat = get_traceback(e, "ErrorReconnectToCommander")
                logger.error(f"{ex_stat}", "tcpip")
                reconnect_attempts += 1
                # Optionally add a delay between reconnection attempts
                await asyncio.sleep(5)

            finally:
                if commanderXport:
                    commanderXport.close()
                    commanderXport = None

            # Retry if the connection is lost
            logger.debug("[UDPServerProtocol][reconnect_to_commander] Retrying connection...")

        logger.debug(f"[UDPServerProtocol][reconnect_to_commander] Failed to reconnect after {max_retries} attempts.")
        # If max retri


async def platoonUDPServer(thisloop, topgui):
    logger.debug(f"[UDPServerProtocol][reconnect_to_commander] Setting up UDP server...")
    hostname = socket.gethostname()
    myips = socket.gethostbyname_ex(hostname)[-1]
    platoon_ip = myips[-1]  # Use the last IP in the list or choose as appropriate

    commander_wait_not_timeout = COMMANDER_WAIT_TIMEOUT
    # Setup UDP server
    transport, protocol = await thisloop.create_datagram_endpoint(
        lambda: UDPServerProtocol(thisloop, topgui),
        local_addr=(platoon_ip, UDP_PORT)
    )
    logger.debug(f"[PlatoonUDPServer] UDP server kicked off....")
    try:
        # Keep the server running indefinitely
        while True:

            await asyncio.sleep(PLATOON_UDP_PERIOD)
            if commander_wait_not_timeout:
                logger.debug(f"[PlatoonUDPServer] commander wait tick....")
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
