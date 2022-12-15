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
UDP_PERIOD = 15
commanderServer = None
fieldLinks = []

async def handle_client(reader, writer):
    request = None
    while request != 'quit':
        request = (await reader.read(255)).decode('utf8')
        response = str(eval(request)) + '\n'
        writer.write(response.encode('utf8'))
        await writer.drain()
    writer.close()

async def run_server():
    finished = False;
    server = await asyncio.start_server(handle_client, 'localhost', 15555)
    async with server:
        await server.serve_forever()


def start_server():
    asyncio.run(run_server())


def _start_async():
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever).start()
    return loop


_loop = _start_async()


# Submits awaitable to the event loop, but *doesn't* wait for it to
# complete. Returns a concurrent.futures.Future which *may* be used to
# wait for and retrieve the result (or exception, if one was raised)
def submit_async(awaitable):
    return asyncio.run_coroutine_threadsafe(awaitable, _loop)

def stop_async():
    _loop.call_soon_threadsafe(_loop.stop)


# With these tools in place( and possibly in a separate module), you can do things like this:
class Commander:
    over = False
    usock = None
    tsock = None
    myip = None
    hostname = None

    def __init__(self):
        self.usock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # Enable port reusage so we will be able to run multiple clients and servers on single (host, port).
        # Do not use socket.SO_REUSEADDR except you using linux(kernel<3.9): goto https://stackoverflow.com/questions/14388706/how-do-so-reuseaddr-and-so-reuseport-differ for more information.
        # For linux hosts all sockets that want to share the same address and port combination must belong to processes that share the same effective user ID!
        # So, on linux(kernel>=3.9) you have to run multiple servers and clients under one user to share the same (host, port).
        # Thanks to @stevenreddie
        self.usock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

        # Enable broadcasting mode
        self.usock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        self.tsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.hostname = socket.gethostname()
        self.myip = socket.gethostbyname(self.hostname)
        self.tsock.bind((self.myip, TCP_PORT))


        submit_async(self.broadcaster())
        # ...



class CommanderTCPServerProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        print('Connection from Platoon {}'.format(peername))
        self.transport = transport
        fieldLinks.append({"ip": peername, "link": self})

    def data_received(self, data):
        message = data.decode()
        print('Data received: {!r}'.format(message))

        #print('Send: {!r}'.format(message))
        #self.transport.write(data)

        #print('Close the client socket')
        # self.transport.close()


class PlatoonTCPServerProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        print('Connection from {}'.format(peername))
        self.transport = transport

    def data_received(self, data):
        message = data.decode()
        print('Data received: {!r}'.format(message))

        print('Send: {!r}'.format(message))
        self.transport.write(data)


# this is the tcp server for the platoon side.
async def communicator():
    # Get a reference to the event loop as we plan to use
    # low-level APIs.
    hostname = socket.gethostname()
    myips = socket.gethostbyname_ex(hostname)[2]
    myip = myips[len(myips)-1]
    print("my host name is: ", hostname, " and my ip is: ", myip)
    tcp_loop = asyncio.get_running_loop()

    tserver = await tcp_loop.create_server(
        lambda: PlatoonTCPServerProtocol(),
        '192.168.1.20', TCP_PORT)

    async with tserver:
        await tserver.serve_forever()




async def tcpServer():
    # Get a reference to the event loop as we plan to use
    # low-level APIs.
    hostname = socket.gethostname()
    myips = socket.gethostbyname_ex(hostname)[2]
    myip = myips[len(myips)-1]
    print("my host name is: ", hostname, " and my ip is: ", myip)
    tcp_loop = asyncio.get_running_loop()

    commanderServer = await tcp_loop.create_server(
        lambda: CommanderTCPServerProtocol(),
        myip, TCP_PORT)

    async with commanderServer:
        await commanderServer.serve_forever()


# async def echo():
#     stdin, stdout = await aioconsole.get_standard_streams()
#     async for line in stdin:
#         stdout.write(line)

# loop = asyncio.get_event_loop()
# loop.run_until_complete(echo())


async def udpBroadcaster():
    over = False

    hostname = socket.gethostname()
    myips = socket.gethostbyname_ex(hostname)[-1]
    myip = myips[len(myips)-1]
    message = str.encode('Commander Calling:' + myip)
    print('Commander Calling:' + myip)


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
        print("sending....")
        usock.sendto(message, ('255.255.255.255', UDP_PORT))
        await asyncio.sleep(UDP_PERIOD)
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
async def commanderFinder():
    over = False
    hostname = socket.gethostname()
    myips = socket.gethostbyname_ex(hostname)[-1]
    myip = myips[len(myips)-1]
    message = b'Commander Calling:'
    usock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    usock.bind(('', UDP_PORT))

    while not over:
        print("listening....")
        rxmsg = usock.recvfrom(1024)
        print("received::", rxmsg)
        await asyncio.sleep(UDP_PERIOD)



async def runCommanderLAN():
    await asyncio.gather(
        udpBroadcaster(),
        tcpServer(),
    )


async def runPlatoonLAN():
    await asyncio.gather(
        commanderFinder(),
        communicator(),
    )
