import json

device_types = ['light', 'shutter', 'hvac'] # conso for consumation service

def parse_information(data):
    return data['mac']

def parse_devices(data):
    devices = {}
    for device in data['endpoints']:
        if device['first_usage'] in device_types:
            devices[device['id_device']] = {'endpoint': device['id_endpoint'],'id': device['id_device'], 'name': device['name'], 'type': device['first_usage'], 'value': None}
    return devices


def parse_data(devices, data):
    for device in data:
        device_id = device['id']
        for endpoint in device['endpoints']:
            endpoint_id = endpoint['id']
            endpoint_data = endpoint['data']
            if endpoint_id in devices: # if is a relevant device
                target = devices[device_id]
                if target['type'] == 'light':
                    value_attr = 'level'
                elif target['type'] == 'shutter':
                    value_attr = 'position'
                elif target['type'] == 'hvac':
                    value_attr = 'hvacMode.setpoint.temperature'
                else:
                    value_attr = None
                value = get_value(endpoint_data, value_attr)
                target['value'] = value
                devices[device_id] = target
    return devices                


def get_value(data, attr):
    value = {}
    for slug in attr.split('.'):
        for dt in data:
            if dt['name'] == slug and dt['validity'] == 'upToDate':
                value[slug] = dt['value']
    return value;                
                

if __name__ == '__main__':
    f = open('info.json')
    config_data = json.load(f)
    f.close()
    mac = parse_information(config_data)
    f = open('devices.json')
    devices_data = json.load(f)
    f.close()
    devices = parse_devices(devices_data)
    f = open('data.json')
    data = json.load(f)
    f.close()
    print(parse_data(devices, data))
