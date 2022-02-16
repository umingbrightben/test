import time
import uuid
import logging

import firebase_admin
from bson.objectid import ObjectId
from dynaconf import settings
from fastapi import HTTPException
from firebase_admin import credentials
from typing import List

from app_lib.basic_func import write_data_to_mongo, get_db_data_by_filter
from app_lib.mongo_utility import DataLoader
from app_lib.rest_utility import send_restful
from core.devicemgr_config import (FIRE_CRED_PATH, MAX_EVPN_GROUP_ID)

# Setting Logger
LOGGER = logging.getLogger(__name__)


def setup_system_initialize():
    """ Setup device manager initialized status """
    setup_device_version(settings['AGENT_VERSION'])
    setup_evpn_group_list()
    firebase_admin.initialize_app(credentials.Certificate(FIRE_CRED_PATH))


def setup_device_version(version):
    """ Set device agent version """
    LOGGER.warning(f'Setup device version ({version})')
    db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                    settings['MONGO']['UPGRADE']['DB'], settings['MONGO']['UPGRADE']['COL'])

    version_data = {}
    version_data['name'] = 'upgrade'
    if db.check_exist_one(version_data):
        LOGGER.warning('Version Data exist.')
        db.delete_one_by_name('upgrade')

    version_data['version'] = version
    db.write_one(version_data)
    LOGGER.warning('Setup device version complete')


def generate_sequence_number(low, high):
    """
    Generate a seqence number list
    example: generate_sequence_number(2,10) --> [2,3,4,5,6,7,8,9.10]
    """
    return list(range(low, high+1))


def get_evpn_group_id():
    """ Get a new evpn group id from db avaiable list """
    db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                    settings['MONGO']['TUNNEL']['EVPN']['DB'], settings['MONGO']['TUNNEL']['EVPN']['GROUP']['COL'])

    search_key = 'available_id_list'
    data = db.get_one_by_name(search_key)
    new_id = data['list'].pop(0)
    LOGGER.warning(f'Apply new evpn group id: {new_id}')

    filter_dict = {'name': search_key}
    _ = update_db_data(db, filter_dict, data, "evpn group id list")
    return new_id


def delete_evpn_group_id(old_id):
    """ Recycle a evpn group id to db when evpn group delete """
    db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                    settings['MONGO']['TUNNEL']['EVPN']['DB'], settings['MONGO']['TUNNEL']['EVPN']['GROUP']['COL'])

    search_key = 'available_id_list'
    data = db.get_one_by_name(search_key)
    data['list'].append(old_id)

    filter_dict = {'name': search_key}
    _ = update_db_data(db, filter_dict, data, "evpn group id list")
    return


def setup_evpn_group_list():
    """ Setup evpn tunnel group id list """
    db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                    settings['MONGO']['TUNNEL']['EVPN']['DB'], settings['MONGO']['TUNNEL']['EVPN']['GROUP']['COL'])

    if len(db.get_all_elements()) == 0:
        LOGGER.warning('Tunnel evpn list in db initialization...')
        data = {}
        data['name'] = 'available_id_list'
        data['list'] = generate_sequence_number(1, MAX_EVPN_GROUP_ID)
        db.write_one(data)
    else:
        LOGGER.warning('Tunnel evpn list has set in db!')
        pass
    return


def set_time_and_location(content):
    """ Description: Used by gwpool.py """
    content.createTime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

    if content.location.type_ == 'auto':
        req_url = f"http://{content.ip}:3000/hermesvpn/gwinfo"
        data, res_code = send_restful(req_url)
        if res_code != 200:
            LOGGER.error(f"Get location from {req_url} error")
            raise HTTPException(status_code=500, detail='Get location error.')
        content.location.latitude = data.get('location').get('latitude')
        content.location.longitude = data.get('location').get('longitude')
    return content


def get_isp_location(public_ip):
    """ Get server location with isp url """
    LOGGER.debug(f"Retrieve location of pubic ip: {public_ip}")
    isp_url = settings['DETECT_ISP_URL'] + public_ip
    res_data, res_code = send_restful(isp_url)
    if res_code == 200 and res_data['status'] == 'success':
        return True, res_data.get('isp'), res_data.get('lat'), res_data.get('lon')
    else:
        LOGGER.error(f"Call {isp_url} to get location failed")
        LOGGER.error(f"Res code: {res_code}, res status: {res_data['status']}")
        return False, "", 0, 0


def get_device_status_data_by_name(device_name: str):
    """
    Description: Get device status data by name in device status db
    DB: device
    COL: management
    Input:
    device_name: SDWAN-xx-xx-xx-xx-xx-xx
    Output:
    {
      "name": "SDWAN-xx-xx-xx-xx-xx-xx", # str
      "organization": "CHT",             # str
      "status": Union(-1, 0, 1),         # int
      "display_name": "xxxx",            # str
      "location": {
        "type": "static",                # static or auto
        "latitude": <floating>,          # float
        "longitude": <floating>          # float
      }
    }
    """
    db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                    settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['MANAGEMENT']['COL'])
    if db.check_exist_one_by_name(device_name):
        device_mgmt_data = db.get_one_by_name(device_name)
        return device_mgmt_data
    else:
        LOGGER.warning(f"Input device name ({device_name}) not found in status db.")
        return None


def get_device_status_data():
    """
    Description: Get device status all data in device status db
    DB: device
    COL: management
    """
    db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                    settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['MANAGEMENT']['COL'])

    device_mgmt_data = []
    device_mgmt_data = db.get_all_elements()

    return device_mgmt_data


def get_host_list_by_org(organization: str) -> List:
    """ Get the hostname list filter by orgnization name """
    # Get status list in status_db
    status_data = get_device_status_data()

    res_data = []
    for d in status_data:
        if d.get('organization') == organization:
            res_data.append(d.get('name'))

    return res_data


def get_device_mgmt_data_by_name(device_name: str) -> str:
    """
    Description: Get device mgmt data from db
    DB: hermesGWPool
    COL: management
    Input: SDWAN-xx-xx-xx-xx-xx-xx
    Output:
    {
      "name": "SDWAN-00-90-0b-46-88-d0",
      "ip": "172.20.0.16",
      "netmask": "255.255.0.0",
      "uuid": "f6547b25cdae4a859eb7af2d7cdfaae8"
    }
    """
    db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                    settings['MONGO']['MANAGEMENT']['DB'], settings['MONGO']['MANAGEMENT']['COL'])

    if db.check_exist_one_by_name(device_name):
        device_mgmt_data = db.get_one_by_name(device_name)
    else:
        LOGGER.warning(f"Input device name ({device_name}) not found in management db.")
        return None

    return device_mgmt_data


def check_data_org(db, device_name: str, org_name: str, functionality: str, self_id: str = None) -> None:
    """ Avoid same app name when same organization """
    if db.check_exist_one_by_name(device_name):
        check_data = db.get_many_by_name(device_name)
        for d in check_data:
            if d['organization'] == org_name:
                if self_id and d['_id'] == ObjectId(self_id):
                    pass
                else:
                    LOGGER.error(f"{functionality} existed, name: {device_name}, org: {org_name}")
                    LOGGER.error(f"Detail data: {d}")
                    raise HTTPException(status_code=400, detail=f"{functionality} existed, name: {device_name}, org: {org_name}")
    return


def update_db_data(db, filter_dict, new_data, functionality: str):
    """ Update data in db with
    filter_dict:
    {
      "key1": value1,
      "key2": value2
    }
    """
    if '_id' in filter_dict:
        filter_dict['_id'] = ObjectId(filter_dict['_id'])
    if db.check_exist_one(filter_dict):
        for key, val in filter_dict.items():
            if key == '_id':
                continue
            elif new_data[key] != val:
                LOGGER.error("Please don't modify filter in new data")
                LOGGER.error(f"Filter key: {key}, Filter values: {val}")
                LOGGER.error(f"New data value: {new_data[key]}")
                raise HTTPException(status_code=400, detail=f"Post data value of key {key} is not same as input value in url.")
        else:
            # After for loop data, update db data by filter dict
            update_data = {"$set": new_data}
            db.update_one(filter_dict, update_data)
        return new_data
    else:
        detail_str = f"Device {functionality}, filter is not exist. Please use POST method. Filter: {filter_dict}"
        LOGGER.error(detail_str)
        raise HTTPException(status_code=400, detail=detail_str)


def check_igate_online(gw_ip: str, gw_port: str):
    """ Check iGate is online or not and update db """
    req_url = f"http://{gw_ip}:{gw_port}/hermesvpn/client"
    LOGGER.debug(f'Get url: {req_url}')
    try:
        data, res_code = send_restful(req_url, req_type='get', time_out=3)
        return True, data
    except HTTPException:
        LOGGER.error(f"The original status of iGate is Online, iGate is not online now, ip: {req_url}!")
        return False, []


def get_gw_data_and_check(gw_name: str, check_offline: bool):
    """ Get tgserver info from db and check online status """

    filter_dict = {'name': gw_name}
    gw_data = get_db_data_by_filter(settings['MONGO']['GWPOOL']['DB'], settings['MONGO']['GWPOOL']['COL'], filter_dict)

    if not gw_data:
        detail_str = f"iGate not found in db, {gw_name}"
        LOGGER.error(detail_str)
        raise HTTPException(status_code=404, detail=detail_str)

    LOGGER.debug('Gateway data:')
    LOGGER.debug(gw_data)

    is_online = False
    data = []
    if check_offline:
        # Check all iGate whether it online or not
        is_online, data = check_igate_online(gw_data['ip'], gw_data['port'])
    else:
        # Only check online iGate
        if gw_data['status']:
            is_online, data = check_igate_online(gw_data['ip'], gw_data['port'])

    # Renew db data when status changed
    if is_online != gw_data['status']:
        # Status changed, update gwpool db data
        LOGGER.warning(f"iGate online status has changed, before: {gw_data['status']}, after: {is_online}")
        gw_data['status'] = is_online
        write_data_to_mongo(settings['MONGO']['GWPOOL']['DB'], settings['MONGO']['GWPOOL']['COL'], filter_dict, gw_data, "iGate info")
    gw_data['device_list'] = data

    return gw_data


def get_gw_data(gw_name: str):
    """ Get gw data """
    gw_data = get_gw_data_and_check(gw_name, True)

    if not gw_data['status']:
        # Raise exception when iGate is down
        detail_str = f"iGate is not online, name: {gw_name}"
        LOGGER.error(detail_str)
        raise HTTPException(status_code=400, detail=detail_str)

    return gw_data


def search_and_append_dict_to_list_of_dict(origin_list: List, append_list: List) -> List:
    """
    Input:
    origin_list = [{"name": "A", "value": 1}, {"name": "B", "value": 2}]
    append_list = [{"name": "C"}, {"name": "B"}, {"name": "D"}, {"name": "E"}]

    Output:
    return_list = [{"name": "A", "value": 1}, {"name": "B", "value": 2}, {"name": "C"}, {"name": "D"}, {"name": "E"}]

    PS:
    The order of list is not important
    """
    # Get list of key in origin_list
    filter_list = [d['name'] for d in origin_list]
    LOGGER.debug(f"Key to be add: {filter_list}")
    # Check filter_list in append_list and get list need to be append to origin_list
    filtered_list = [d for d in append_list if d['name'] not in filter_list]

    # Append list of dict to origin_list
    origin_list.extend(filtered_list)

    return origin_list


def search_and_delete_dict_from_list_of_dict(origin_list: List, delete_list: List) -> List:
    """
    Input:
    origin_list = [{"name": "A", "value": 1}, {"name": "B", "value": 2}, {"name": "C"}, {"name": "D"}, {"name": "E"}]
    delete_list = [{"name": "A"}, {"name": "D"}, {"name": "E"}]

    Output:
    return_list = [{"name": "B", "value": 2}, {"name": "C"}]

    PS:
    The order of list is not important
    """
    # Get list of key in delete_list
    filter_list = [d['name'] for d in delete_list]
    LOGGER.debug(f"Key to be delete: {filter_list}")
    # Remain the dict which name is not in filter_list
    filtered_list = [d for d in origin_list if d['name'] not in filter_list]

    return filtered_list


def search_key_from_list_of_dict(origin_list: List, name_key: str, value_key: str):
    """
    Input:
    origin_list = [{"name": "A", "value": 1, "gg": 2}, {"name": "B", "value": 2}]
    name_key = "A"
    value_key = "gg"

    Output:
    return_value = 2
    """
    # Check filter_list in append_list and get list need to be append to origin_list
    filtered_list = [d for d in origin_list if d['name'] == name_key]
    if len(filtered_list) > 1:
        LOGGER.warning("It seems stange that there have two same keys in db!!!!")
        LOGGER.warning(f"Please check origin list: {origin_list}")
        LOGGER.warning(f"Please check the key of name: {name_key}")

    # We only check the first one!!!!!
    for d in filtered_list:
        if value_key in d:
            return d[value_key]
        else:
            LOGGER.warning("It seems stange that no value in db!!!!")
            LOGGER.warning(f"Please check origin list: {origin_list}, key: {name_key}")
            LOGGER.warning(f"Please check the key of your value: {value_key}")
            return None


def search_value_with_key_from_list_of_dict(origin_list: List, name_list: List, value_key: str):
    """
    Input:
    origin_list = [{"name": "A", "value": 1, "gg": 2}, {"name": "B", "value": 2}]
    name_list = [{"name": "A"}, {"name": "B"}, {"name": "E"}]
    value_key = "value"

    Output:
    return_value = [1, 2]
    """
    res_data = []
    for element in name_list:
        search_value = search_key_from_list_of_dict(origin_list, element['name'], value_key)
        if search_value is None:
            pass
        else:
            res_data.append(search_value)

    return res_data


def send_mgmt_notification(level: str, subject: str, api_url: str, detail_msg: str, body: dict = {}):
    """ When System error, send notification api to notifactionmgr """
    req_url = f"http://{settings['NOTIFICATIONMGR_SERVER']['IP']}:{settings['NOTIFICATIONMGR_SERVER']['PORT']}/hermesnotification/mgmt"
    send_data = {}
    send_data['name'] = 'devicemgr'
    send_data['level'] = level
    send_data['subject'] = subject
    send_data['req_url'] = str(api_url)
    send_data['detail_msg'] = detail_msg
    if body:
        send_data['body'] = body
    _, res_code = send_restful(req_url, req_type='post', payload=send_data, time_out=8)
    if res_code != 201:
        LOGGER.error(f"Send api to notification error, req_url: {req_url}")
    return


def send_device_notification(device_name: str, subject: str, level: str, detail_msg: str, timestamp: int):
    """
    When device event, send notification api to notificationmgr
    level: Info/Warning/Critical
    """
    req_url = f"http://{settings['NOTIFICATIONMGR_SERVER']['IP']}:{settings['NOTIFICATIONMGR_SERVER']['PORT']}/hermesnotification/agent"
    send_data = {}
    sub_data = {}
    send_data['name'] = device_name
    sub_data['uuid'] = str(uuid.uuid1())
    sub_data['subject'] = subject
    sub_data['read'] = False
    sub_data['level'] = level
    sub_data['message'] = detail_msg
    sub_data['timestamp'] = timestamp
    send_data['notification'] = sub_data
    _, res_code = send_restful(req_url, req_type='post', payload=send_data, time_out=8)
    if res_code != 201:
        LOGGER.error(f"Send api to notification error, req_url: {req_url}")
    return
