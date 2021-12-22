import asyncio
from datetime import datetime
import websockets
import sys
import json
import os
import base64
import time
import ssl

from requests.auth import HTTPDigestAuth
import http.client
from http.client import HTTPResponse
from io import BytesIO

from parser import parse_information
from parser import parse_devices
from parser import parse_data

websocket = None
mac = None
devices = None
out_queue = None
in_queue = None

def log(msg):
    now = datetime.now()
    dt = now.strftime("%d/%m/%Y %H:%M:%S")
    print("[", dt, "] - ", msg)

remote_adress = os.environ.get('REMOTE_HTTP_TYDOM', "mediation.tydom.com")
mac_address = os.environ.get('TYDOM_MAC_ADDRESS', "")
tydom_ip = os.environ.get('TYDOM_IP', remote_adress)
password = os.environ.get('TYDOM_PASSWORD', "")

# Local use ?
local = tydom_ip != remote_adress
host = tydom_ip

if (local):
    log('Local Execution Detected')
    ssl_context = ssl._create_unverified_context()
    cmd_prefix = ""
else:
    log('Remote Execution Detected')
    ssl_context = None
    cmd_prefix = "\x02"

async def execute_cmd(medthod, cmd, body = ''):
    global websocket
    global cmd_prefix
    cmd_bytes = bytes(cmd_prefix + medthod + " " + cmd +" HTTP/1.1\r\nContent-Length: "+ str(len(body)) +"\r\nContent-Type: application/json; charset=UTF-8\r\nTransac-Id: 0\r\n\r\n"+ body, "ascii")
    await websocket.send(cmd_bytes)
    
async def request_info():
    log('>>> Request information cmd')
    await execute_cmd('GET', '/info')

async def request_refresh_data():
    log('>>> Request fresh data cmd')
    await execute_cmd('POST', '/refresh/all')

async def request_configuration():
    log('>>> Request configuration file cmd')
    await execute_cmd('GET', '/configs/file')

async def request_devices_data():
    log('>>> Request devices data cmd')
    await execute_cmd('GET', '/devices/data')    

async def set_devices_data(device, endpoint, value, attr):
    log('>>> Set devices data cmd')
    body = '[{"value": '+ str(value) + ', "name": "'+str(attr)+'"}]'
    body = body.replace('\'', '"')
    await execute_cmd('PUT', '/devices/{}/endpoints/{}/data'.format(str(device),str(endpoint)), body+"\r\n\r\n")

# Generate 16 bytes random key for Sec-WebSocket-Keyand convert it to base64
def generate_random_key():
    return base64.b64encode(os.urandom(16))

# Build the headers of Digest Authentication
def build_digest_headers(nonce):
    digestAuth = HTTPDigestAuth(mac_address, password)
    chal = dict()
    chal["nonce"] = nonce[2].split('=', 1)[1].split('"')[1]
    chal["realm"] = "ServiceMedia" if local is False else "protected area"
    chal["qop"] = "auth"
    digestAuth._thread_local.chal = chal
    digestAuth._thread_local.last_nonce = nonce
    digestAuth._thread_local.nonce_count = 1
    return digestAuth.build_digest_header('GET', "https://{}:443/mediation/client?mac={}&appli=1".format(host, mac_address))

class FakeSocket():
    def __init__(self, response_string):
        self._file = BytesIO(response_string.encode())
    def makefile(self, *args, **kwargs):
        return self._file

async def consumer_handler():
    global websocket
    global mac_address
    global devices
    global out_queue
    while True :
        try:
            #In case of exception
            if websocket == None:
                return await main_task()
            bytes_str = await websocket.recv()           
            response_str = bytes_str.decode()
            
            """ Same response start by HTTP method and Uri """
            response_body = 'HTTP/{}'.format(response_str[response_str.index('HTTP/') + len('HTTP/'):])
            response_prefix = response_str[0 : response_str.index('HTTP/')]     
            if response_prefix != '':
                response_body = response_body.replace('HTTP/1.1\r\n', 'HTTP/1.1 200 OK\r\n')           
            response = HTTPResponse(FakeSocket(response_body))
            response.begin()
            message_type = response.getheader('Uri-Origin')
            message_body = response.read().decode()
            message_encoding = response.getheader('Content-Type')
            message_length = len(str(message_body))
            message_status = response.status
            
            if message_length == 0:
                log('<<< Received ACK POST/PUT/DELETE command for '+message_type)                
            elif message_type == '/info':
                log('<<< Received information data')
                data = json.loads(str(message_body))
                mac = parse_information(data)
            #elif message_type == '/refresh/all':
            #    log('<<< Received refresh data')                
            #    fresh_data = json.loads(str(message_body))
            elif message_type == '/configs/file':
                log('<<< Received config data')
                data = json.loads(str(message_body))   
                devices = parse_devices(data)               
                if out_queue != None and not out_queue.full():
                    out_queue.put(devices)          
            elif message_type == '/devices/data':
                log('<<< Received device data (sensors)')       
                devices_data = json.loads(str(message_body))   
                if devices != None:              
                    devices = parse_data(devices, devices_data)
                    #log(devices)
                    if out_queue != None and not out_queue.full():
                        out_queue.put(devices)  
            elif message_type == None:
                log('<<< Received status data (updating)')
                status_data = json.loads(str(message_body))
                if devices != None:              
                    devices = parse_data(devices, status_data)
                    #log(devices)
                    if out_queue != None and not out_queue.full():
                        out_queue.put(devices)  
            else:
                log('Undefined message type.')            
                log("Received message type : "+ str(message_type))
                log("Received message content : "+ str(message_body))
                log("Received message encoding : "+ str(message_encoding))
                log("Received message status : "+ str(message_status))
            
        except Exception as e:
            log('Unable to parse http response : ' + response_str)
            log(e)
            #import traceback
            #traceback.print_exc()
            websocket = None
            #await asyncio.sleep(8)
            #await websocket_connection()

async def producer_handler():
    global websocket
    global in_queue
    while True :
        if (websocket != None):
            try:   
                await asyncio.sleep(3)
                if in_queue != None and not in_queue.empty():
                    data = in_queue.get_nowait()
                    for device in data:                        
                        await set_devices_data(device['id'], device['endpoint'], device['value'], device['name'])                
            except Exception as e:
                log("Producer error ! {}".format(e))
        else: 
            await asyncio.sleep(3)
            log('Producer : no websocket available')

async def handler():
    global websocket
    try:
        consumer_task = asyncio.ensure_future(consumer_handler())
        producer_task = asyncio.ensure_future(producer_handler())

        done, pending = await asyncio.wait(
            [consumer_task, producer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        log('Producer & Consumer are done !')
        for task in pending:
            task.cancel()
        log('All pending task are canceled !') 

    except Exception as e:
        log("Webconnection handler error ! {}, retrying in 8 seconds...".format(e))           
        websocket = None
        await asyncio.sleep(8)
        await main_task()

async def websocket_connection():
    global websocket
    global mac_address
    global devices
    httpHeaders =  {"Connection": "Upgrade",
                    "Upgrade": "websocket",
                    "Host": host + ":443",
                    "Accept": "*/*",
                    "Sec-WebSocket-Key": generate_random_key(),
                    "Sec-WebSocket-Version": "13"
                    }

    conn = http.client.HTTPSConnection(host, 443, context=ssl_context)    
    conn.request("GET", "/mediation/client?mac={}&appli=1".format(mac_address), None, httpHeaders)
    res = conn.getresponse()
    nonce = res.headers["WWW-Authenticate"].split(',', 3)
    res.read()
    conn.close()
    websocketHeaders = {'Authorization': build_digest_headers(nonce)}
    if ssl_context is not None:
        websocket_ssl_context = ssl_context
    else:
        websocket_ssl_context = True # Verify certificate

    try:
        log('Attempting websocket connection...')
        websocket = await websockets.client.connect('wss://{}:443/mediation/client?mac={}&appli=1'.format(host, mac_address),
                                             extra_headers=websocketHeaders, ssl=websocket_ssl_context, ping_interval=None)
        log("Tydom Websocket is Connected")   
        if mac_address == None:     
            await request_info()
        if devices == None:
            await request_configuration()
        await request_devices_data()        
        await request_refresh_data()
        
        await handler()
    except Exception as e:
        log('Main task retrying in 8 seconds...')
        log("Websocket main connexion error ! {}".format(e))
        await asyncio.sleep(8)
        websocket = None
        await main_task()

# Main async task
async def main_task():
    global websocket
    try:
        if (websocket == None) or not websocket.open:
            log("Tydom new connection")
            await websocket_connection()
    except Exception as e:                
        log("Main task crashed ! {}".format(e))
        log('Main task crashed !, reconnecting in 8 s...')
        await asyncio.sleep(8)
        websocket = None
        await main_task()

def start_websocket(to_server_queue,to_ws_queue):
    global out_queue
    global in_queue
    out_queue = to_server_queue
    in_queue = to_ws_queue
    try:            
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main_task())            
        loop.run_forever()
    except Exception as e:
        log("FATAL ERROR ! {}".format(e))
        sys.exit(-1)

if __name__ == '__main__':     
    start_websocket(to_server_queue=None, to_ws_queue=None)
