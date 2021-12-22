
from flask import Flask, jsonify, request
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import time
import os

app = Flask(__name__)
auth = HTTPBasicAuth()

out_queue = None
in_queue = None

data = {}
last_update = None

username = os.environ.get('HTTP_USERNAME', 'nobody')
password = generate_password_hash(os.environ.get('HTTP_PASSWORD', 'nobody'))

@auth.verify_password
def verify_password(user, passcode):
    global password;
    global username;
    if username == user and check_password_hash(password, passcode):
        return user

@auth.get_password
def get_pw(user):
    global username
    global password
    if user == username:
        return password
    return None

@app.route('/turn_off_light/<target>/<value>', methods=['POST'])
@auth.login_required
def switch_light(target, value):
    global data
    get_fresh_data()
    to_send = []
    if target == 'all':
        for device_id in data:
            if data[device_id]['type'] == 'light':
               to_send.append({'id' : device_id, 'endpoint': data[device_id]['endpoint'], 'value' : value, 'name' : 'level'})
    else:
        to_send = [{'id' : target, 'endpoint': data[device_id]['endpoint'], 'value' : value, 'name' : 'level'}]            
    return send_data(to_send)

@app.route('/turn_on_light/<target>', methods=['POST'])
@auth.login_required
def turn_on_light(target):
    return switch_light(target, 1)

@app.route('/turn_off_light/<target>', methods=['POST'])
@auth.login_required
def turn_off_light(target):
    return switch_light(target, 0)

@app.route('/switch_shutter/<target>/<value>', methods=['POST'])
@auth.login_required
def switch_shutter(target, value=100):    
    get_fresh_data()
    to_send = []
    if target == 'all':
        for device_id in data:
            if data[device_id]['type'] == 'shutter':
               to_send.append({'id' : device_id, 'endpoint': data[device_id]['endpoint'], 'value' : value, 'name' : 'position'})
    else:
        to_send = [{'id' : target, 'value' : value, 'endpoint': data[device_id]['endpoint'], 'name' : 'position'}]            
    return send_data(to_send)
    
@app.route('/open_shutter/<target>', methods=['POST'])
@auth.login_required
def open_shutter(target):
    return switch_shutter(target, value=100)

@app.route('/close_shutter/<target>', methods=['POST'])
@auth.login_required
def close_shutter(target):
    return switch_shutter(target, value=0)

@app.route('/', methods=['POST'])
@auth.login_required
def post():
    get_fresh_data()
    content = request.json
    return send_data(content)

@app.route('/', methods=['GET'])
@auth.login_required
def get():
    global data
    global last_update
    get_fresh_data()
    return jsonify({'last_update' : last_update, 'date' : data})



def send_data(to_send):
    global out_queue
    if out_queue != None and not out_queue.full():
        out_queue.put_nowait(to_send)  
        return jsonify({'status': True, 'data': to_send})
    return jsonify({'status': False, 'data' : []})


def start_server(to_server_queue,to_ws_queue):
    global out_queue
    global in_queue
    out_queue = to_ws_queue
    in_queue = to_server_queue
    app.run(host='0.0.0.0', debug=(None == os.environ.get('NODEBUG')))

def get_fresh_data():
    global queue
    global data
    global last_update
    if in_queue != None and not in_queue.empty():
        data = in_queue.get_nowait()
        last_update = int(time.time() * 1000)
        return True
    return False

if __name__ == '__main__': 
    start_server(to_server_queue=None, to_ws_queue=None)  