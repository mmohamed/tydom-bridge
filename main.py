import multiprocessing
from server import start_server 
from websocket import start_websocket

if __name__ == '__main__':              
    to_server_queue = multiprocessing.Queue()
    to_ws_queue = multiprocessing.Queue()
    p_server = multiprocessing.Process(target=start_server,args=(to_server_queue,to_ws_queue,))
    p_ws = multiprocessing.Process(target=start_websocket,args=(to_server_queue,to_ws_queue,))
    
    p_server.start()
    p_ws.start()

    p_server.join()
    p_ws.join()
