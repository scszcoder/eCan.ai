import asyncio
import socket
import threading
import selectors
import aioconsole

UDP_IP = "127.0.0.1"

UDP_PORT = 4868
TCP_PORT = 4898

MESSAGE = b"Hello, World!"
sel = selectors.DefaultSelector()

# UDP pack broadcasted every 15 second.
TICK = 30
COMMANDER_UDP_PERIOD = 10
PLATOON_UDP_PERIOD = 10

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

    def connection_made(self, transport):
        self.peername = transport.get_extra_info('peername')
        print('Connection from Platoon {}'.format(self.peername))
        self.transport = transport
        fieldLinks.append({"ip": self.peername, "name": "nyk", "link": self})
        if not self.topgui.mainwin == None:
            self.topgui.mainwin.addVehicle(self)

    def data_received(self, data):
        message = data.decode()
        if not self.topgui.mainwin == None:
            self.topgui.mainwin.appendNetLogs(['Data received: {!r}'.format(message)])
            self.topgui.mainwin.processPlatoonMsgs(message, self.peername)

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

class communicatorProtocol(asyncio.Protocol):
    def __init__(self, topgui, message, on_con_lost):
        self.message = message
        self.on_con_lost = on_con_lost
        self.topgui = topgui

    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        print('Connection from commander {}'.format(peername))
        self.transport = transport

    def data_received(self, data):
        message = data.decode()
        print('Data received: {!r}'.format(message))
        self.topgui.mainwin.processCommanderMsgs(message)

        # print('Send: {!r}'.format(message))
        # self.transport.write(data)

    def connection_lost(self, exec):
        print("The commander is LOST....")
        self.on_con_lost.set_result(True)


async def tcpServer(topgui):
    # Get a reference to the event loop as we plan to use
    # low-level APIs.
    hostname = socket.gethostname()
    myips = socket.gethostbyname_ex(hostname)[2]
    myip = myips[len(myips)-1]
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
        if not topgui.mainwin == None:
            topgui.mainwin.appendNetLogs(["broadcast"])
        print("Broadcasting...", 'Commander Calling:' + myip)
        usock.sendto(message, ('255.255.255.255', UDP_PORT))
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

# this is the udp receiver on the platoon side.
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

    while not over:
        print("listening....")
        data, addr = await thisloop.run_in_executor(None, usock.recvfrom, 1024)

        # rxmsg = usock.recvfrom(512)
        print("platoon received::", data.decode("utf-8"))

        # if "Commander" in rxmsg[0].decode("utf-8") and commanderXport == None:
        if "Commander" in data.decode("utf-8") and commanderXport == None:
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

# top level work scheduler on the commander side.
async def topScheduler(topgui):
    running = True
    while running:
        if not topgui.mainwin == None:
            await topgui.mainwin.runbotworks()
        await asyncio.sleep(TICK)



async def runCommanderLAN(topgui):
    await asyncio.gather(
        udpBroadcaster(topgui),
        tcpServer(topgui),
        topScheduler(topgui),
    )


async def runPlatoonLAN(topgui, thisLoop, waitwin):
    await asyncio.gather(
        commanderFinder(topgui, thisLoop, waitwin),
        topScheduler(topgui),
    )
