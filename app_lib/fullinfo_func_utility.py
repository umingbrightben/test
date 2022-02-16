import copy
import time
import logging

from deepdiff import DeepDiff
from dynaconf import settings
from fastapi import HTTPException

from app_lib.func_utility import (update_db_data, get_isp_location, get_device_status_data_by_name,
                                  get_device_mgmt_data_by_name)
from app_lib.mongo_utility import DataLoader
from app_lib.rest_utility import send_restful

# Setting Logger
LOGGER = logging.getLogger(__name__)


def auto_gen_device_location(wans_data):
    """
    Description: Auto generate device location data, when setting auto
    Input: wans_data in device full info
    Output:
    {
      "type": "auto",
      "latitude": float,
      "longitude": float
    }
    """
    location_dict = {}
    # Get first wans public ip
    for d in wans_data:
        if d['public_ip']:
            # is not none
            location_dict['type'] = 'auto'
            location_status, _, location_dict['latitude'], location_dict['longitude'] = get_isp_location(d['public_ip'])
            if location_status:
                break

    return location_dict


def gen_device_wans_isp(wans_data: dict) -> dict:
    """
    Description: Auto generate device wans isp_name with public_ip setting
    Input: wans_data in device full info
    Output: wans_data with modified isp_name, if not public will input empty string
    """
    isp_db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                        settings['MONGO']['ISP_CACHE']['DB'], settings['MONGO']['ISP_CACHE']['COL'])
    for d in wans_data:
        if d['public_ip']:
            # is not none
            if isp_db.check_exist_one_by_name(d['public_ip']):
                isp_data = isp_db.get_one_by_name(d['public_ip'])
                d['isp_name'] = isp_data['isp']
            else:
                _, isp_name, _, _ = get_isp_location(d['public_ip'])
                # Insert data
                isp_data = {
                    "name": d['public_ip'],
                    "isp": isp_name
                }
                isp_db.write_one(isp_data)
                LOGGER.info(f"Write isp_data into isp_db: {isp_data}")
                d['isp_name'] = isp_data['isp']
        else:
            d['isp_name'] = ""
    return wans_data


def check_device_status(device_name: str, device_content: dict):
    """
    Description: Check device status in db
    Input:
    device_name: SDWAN-xx-xx-xx-xx-xx-xx
    Output:
    device_org: device organization name, return None if not set yet.
    device_status: device status (-1: manufacturer, 0: pre-deploy, 1: deployed, 2: upgrading)
    """
    db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                    settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['MANAGEMENT']['COL'])

    device_mgmt_data = get_device_status_data_by_name(device_name)
    if device_mgmt_data:
        return device_mgmt_data['organization'], device_mgmt_data['status']
    else:
        # Insert new data in db
        insert_data = {}
        insert_data['name'] = device_name
        insert_data['organization'] = None
        insert_data['status'] = -1
        insert_data['display_name'] = device_name
        # Get first wans public ip
        insert_data['location'] = auto_gen_device_location(device_content['wans'])
        db.write_one(insert_data)
        return None, -1


def check_device_up_status(device_info_list):
    """
    Description: Check device full info static data
    1. Check timestamp and set device['up']
    """
    for device in device_info_list:
        # 1. Check timestamp and set
        accual_time_now = time.time()
        if -90 < (accual_time_now - device['timestamp']) < 90:
            device['up'] = True
        else:
            device['up'] = False

    return device_info_list


def check_device_mgmt_status(device_info_list, device_status_code=[1]):
    """
    Description: Check device full info static data
    Input:
    device_status_code: -1: manufacturer, 0: pre-deploy, 1: deployed, 2: upgrading
    1. Check device status db
    2. Check device mgmt db
    3. Filter device status by input device_status_code
    4. set device['ip']
    5. set device['organization'], device['display_name'], device['location']
    """
    # By default setting display_name as device unique name
    res_data = []
    for device in device_info_list:
        status_data = get_device_status_data_by_name(device['name'])
        mgmt_data = get_device_mgmt_data_by_name(device['name'])
        mgmt_ip = 'Not assign' if 'ip' not in mgmt_data else mgmt_data['ip']
        mgmt_uuid = 'Not assign' if 'uuid' not in mgmt_data else mgmt_data['uuid']
        if status_data and mgmt_data:
            # filter device_status_code
            if status_data['status'] in device_status_code:
                device['ip'] = mgmt_ip
                device['uuid'] = mgmt_uuid
                device['organization'] = status_data['organization']
                device['display_name'] = status_data['display_name']
                device['location'] = status_data['location']
                res_data.append(device)
        else:
            LOGGER.error(f"Strange status, device name {device['name']}, please check!!")
            LOGGER.error(f"Status data: {status_data}")
            LOGGER.error(f"Mgmt IP: {mgmt_ip}, Mgmt UUID: {mgmt_uuid}")
            raise HTTPException(status_code=400, detail=f"Device ({device['name']}) data not found in db.")

    return res_data


def handle_device_status_update(device_name: str, update_col: str, old_status_data: dict, update_status_data: dict):
    """
    Description: Handle gui update status db data.
    Input:
    device_name: SDWAN-xx-xx-xx-xx-xx-xx
    update_col: organization, display_name, location (sholud not see status)
    old_status_data: status data in status db
    update_status_data:
    {
        "name": xxxx
        "location": xxxxx
    }
    """
    input_exception = HTTPException(
        status_code=400,
        detail="Input data error.",
    )
    # Check first
    white_list = ['organization', 'display_name', 'location', 'status']
    if device_name != update_status_data['name']:
        LOGGER.error(f"Device data error, device name: {device_name}")
        LOGGER.error(f"Data you input: {update_status_data}")
        raise input_exception
    if update_status_data[update_col] is None or update_col not in white_list:
        # If data is None, or is not valid
        LOGGER.error(f"Device data error, update column: {update_col}")
        LOGGER.error(f"Data you input: {update_status_data}")
        raise input_exception

    if update_col == 'location':
        if update_status_data['location']['type'] == 'static':
            old_status_data[update_col] = update_status_data[update_col]
        else:
            # auto
            db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                            settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['FULLINFO']['COL'])
            fullinfo_data = db.get_one_by_name(device_name)
            old_status_data[update_col] = auto_gen_device_location(fullinfo_data['wans'])
    elif update_col == 'status':
        LOGGER.warning("Device status should not update this column by your own. Skip this change!!!!!")
    else:
        # organization, display_name
        old_status_data[update_col] = update_status_data[update_col]

    return old_status_data


def handle_device_stock_assign_org(content):
    """
    Description: Handle device stock assign organization data and migrate db data from manufacturer to fullinfo
    """
    status_db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                           settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['MANAGEMENT']['COL'])

    manufacturer_db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                                 settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['MANUFACTURER']['COL'])

    fullinfo_db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                             settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['FULLINFO']['COL'])

    # 1. Check the input content is all valid, otherwise return 500
    for device in content.device_pool:
        device_status_data = get_device_status_data_by_name(device.name)
        if not device_status_data:
            LOGGER.warning(f"Input device list: {content.device_pool}")
            LOGGER.error(f"Input device name ({device.name}) not found in status db strange")
            raise HTTPException(status_code=500, detail='Device not found in status db.')

        # device_status: device status (-1: manufacturer, 0: pre-deploy, 1: deployed, 2: upgrading)
        if device_status_data['organization'] or device_status_data['status'] != -1:
            LOGGER.warning(f"Input device list: {content.device_pool}")
            LOGGER.critical(f"Input device name ({device.name}) status db strange")
            LOGGER.critical(f"org: {device_status_data['organization']}, status: {device_status_data['status']}")
            raise HTTPException(status_code=400, detail='Device status error in status db.')

        if not manufacturer_db.check_exist_one_by_name(device.name):
            LOGGER.warning(f"Input device list: {content.device_pool}")
            LOGGER.error(f"Input device name ({device.name}) not found in manufacturer db.")
            raise HTTPException(status_code=400, detail=f"Device ({device.name}) not found in manufacturer db.")

        if fullinfo_db.check_exist_one_by_name(device.name):
            LOGGER.warning(f"Input device list: {content.device_pool}")
            LOGGER.error(f"Input device name ({device.name}) should not found in fullinfo db.")
            raise HTTPException(status_code=400, detail=f"Device ({device.name}) should not found in fullinfo db.")

    # 2. Migrate device content from manufacturer_db to fullinfo_db, and update info to status_db
    for device in content.device_pool:
        LOGGER.warning(f"Migrate basic report data from manufacture_db to fullinfo_db, name: {device.name}")
        manufacturer_device_data = manufacturer_db.get_one_by_name(device.name)
        device_status_data = get_device_status_data_by_name(device.name)
        fullinfo_db.write_one(manufacturer_device_data)
        manufacturer_db.delete_one_by_name(device.name)
        # Update status db
        device_status_data['status'] = 0
        device_status_data['organization'] = content.organization
        filter_dict = {'name': device.name}
        _ = update_db_data(status_db, filter_dict, device_status_data, "device status info")
        LOGGER.warning(f"Migrate basic report data success, name: {device.name}")

    return content


def handle_device_parkinglot_reset(content):
    """
    Description: Handle device parkinglot reset, and migrate db data from fullinfo to manufacturer
    """
    status_db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                           settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['MANAGEMENT']['COL'])

    manufacturer_db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                                 settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['MANUFACTURER']['COL'])

    fullinfo_db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                             settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['FULLINFO']['COL'])

    # 1. Check the input content is all valid, otherwise return 500
    for device in content.device_pool:
        device_status_data = get_device_status_data_by_name(device.name)
        if not device_status_data:
            LOGGER.warning(f"Input device list: {content.device_pool}")
            LOGGER.error(f"Input device name ({device.name}) not found in status db strange")
            raise HTTPException(status_code=500, detail='Device not found in status db.')

        # device_status: device status (-1: manufacturer, 0: pre-deploy, 1: deployed, 2: upgrading)
        if not device_status_data['organization'] or device_status_data['status'] != 0:
            LOGGER.warning(f"Input device list: {content.device_pool}")
            LOGGER.critical(f"Input device name ({device.name}) status db strange, must have org_name and status = 0")
            LOGGER.critical(f"org: {device_status_data['organization']}, status: {device_status_data['status']}")
            raise HTTPException(status_code=400, detail='Device status error in status db.')

        if manufacturer_db.check_exist_one_by_name(device.name):
            LOGGER.warning(f"Input device list: {content.device_pool}")
            LOGGER.error(f"Input device name ({device.name}) should not found in manufacturer db.")
            raise HTTPException(status_code=400, detail=f"Device ({device.name}) should not found in manufacturer db.")

        if not fullinfo_db.check_exist_one_by_name(device.name):
            LOGGER.warning(f"Input device list: {content.device_pool}")
            LOGGER.error(f"Input device name ({device.name}) not found in fullinfo db.")
            raise HTTPException(status_code=400, detail=f"Device ({device.name}) not found in fullinfo db.")

    # 2. Migrate device content from fullinfo_db to manufacturer_db, and update info to status_db
    for device in content.device_pool:
        LOGGER.warning(f"Migrate basic report data from fullinfo_db to manufacture_db, name: {device.name}")
        fullinfo_device_data = fullinfo_db.get_one_by_name(device.name)
        device_status_data = get_device_status_data_by_name(device.name)
        manufacturer_db.write_one(fullinfo_device_data)
        fullinfo_db.delete_one_by_name(device.name)
        # Update status db
        device_status_data['status'] = -1
        device_status_data['organization'] = None
        filter_dict = {'name': device.name}
        _ = update_db_data(status_db, filter_dict, device_status_data, "device status info")

    return content


def set_device_info_4_manufacturer_db(content):
    """
    Description: Handle device basic report and save in manufacturer db
    """
    db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                    settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['MANUFACTURER']['COL'])

    device_fullinfo = content.dict(by_alias=True)
    # Check wans.isp_name
    device_fullinfo['wans'] = gen_device_wans_isp(device_fullinfo['wans'])

    if db.check_exist_one_by_name(device_fullinfo['name']):
        LOGGER.warning(f"Update device {device_fullinfo['name']} basic report in manufacturer db!")
        filter_dict = {'name': device_fullinfo['name']}
        _ = update_db_data(db, filter_dict, device_fullinfo, "device manufacturer full info")
    else:
        LOGGER.warning(f"New device {device_fullinfo['name']} basic report insert in manufacturer db!")
        db.write_one(device_fullinfo)

    return


def compare_two_device_template_dict(data_A, data_B):
    """
    Description: Use deepdiff to check data is different or not
    Output: If {}, data_A = data_B
    """
    # Note the below re_path will let deepdiff not show the difference in these columns
    # wan_exclude_path: data['wans'][int]['up|uptime|public_ip|isp_name']
    # res_diff = DeepDiff(data_A, data_B, exclude_regex_paths=[wans_exclude_path])
    res_diff = DeepDiff(data_A, data_B)

    return res_diff


def generate_action_data_and_append(original_data: list, action: str, data):
    """
    Description: generate action data and append to original_data
    original_data: []
    action: POST, PUT, DELETE
    key: wans, lans, etc.
    """
    action_data = {}
    action_data['action'] = action
    action_data['data'] = data
    original_data.append(action_data)
    return original_data


def generate_diff_data_detail(old_data, new_data):
    """
    Description: Generate the detail data for user reading
    Input data:
    old_data: Device config template structure
    [refs]: https://hackmd.io/ussreznjSbWUcdLQ3Kp3xQ?view#Device-full-info-hermesvpndevicefullinfo
    new_data: Device config template update structure
    [refs]: https://hackmd.io/ussreznjSbWUcdLQ3Kp3xQ?view#Device-full-info-hermesvpndevicefullinfo
    Output data: 'detail' in staging response data
    [refs]: https://hackmd.io/ussreznjSbWUcdLQ3Kp3xQ?view#Device-staging-info-db
    """
    res_data = {}

    if set(old_data.keys()) != set(new_data.keys()):
        # Suppose keys in old data and new data is same, if not should be error
        LOGGER.error("Key error, the key is different")
        LOGGER.error(f"Keys in old_data: {old_data.keys()}")
        LOGGER.error(f"Keys in new_data: {new_data.keys()}")
        raise HTTPException(status_code=400, detail='Data key error')

    for key in new_data.keys():
        LOGGER.debug(f"Parse key: {key}")
        LOGGER.debug(f"Values in old_data: {old_data[key]}")
        LOGGER.debug(f"Values in new_data: {new_data[key]}")
        res_sub_data_list = []
        if type(new_data[key]) is str:
            # key = model_name
            if old_data[key] != new_data[key]:
                res_sub_data_list = generate_action_data_and_append(res_sub_data_list, 'PUT', new_data[key])
        elif type(new_data[key]) is list:
            if key == 'controller' or key == 'tunnel_gateway':
                # key = controller, tunnel_gateway
                list_to_be_add = list(set(new_data[key]) - set(old_data[key]))
                list_to_be_del = list(set(old_data[key]) - set(new_data[key]))
                # If not empty list
                if list_to_be_add:
                    res_sub_data_list = generate_action_data_and_append(res_sub_data_list, 'POST', list_to_be_add)
                if list_to_be_del:
                    res_sub_data_list = generate_action_data_and_append(res_sub_data_list, 'DELETE', list_to_be_del)
            else:
                # wans, lans, dhcp, firewall, port_forwarding, routes, l7_policy
                if key == 'dhcp':
                    primary_key = 'lan_name'
                else:
                    primary_key = 'name'
                # Check the len of old data and new data is difference or not, ex: list of firewall number
                old_data_name_list = [d[primary_key] for d in old_data[key]]
                new_data_name_list = [d[primary_key] for d in new_data[key]]
                list_to_be_add = list(set(new_data_name_list) - set(old_data_name_list))
                list_to_be_del = list(set(old_data_name_list) - set(new_data_name_list))
                list_to_be_put = list(set(old_data_name_list).intersection(new_data_name_list))
                if list_to_be_add:
                    # data to be add
                    for data in new_data[key]:
                        if data[primary_key] in list_to_be_add:
                            res_sub_data_list = generate_action_data_and_append(res_sub_data_list, 'POST', data)
                if list_to_be_del:
                    # data to be delete
                    for data in old_data[key]:
                        if data[primary_key] in list_to_be_del:
                            res_sub_data_list = generate_action_data_and_append(res_sub_data_list, 'DELETE', data)
                if list_to_be_put:
                    # data to be put, error
                    for data_old in old_data[key]:
                        for data_new in new_data[key]:
                            if data_old[primary_key] == data_new[primary_key]:
                                if compare_two_device_template_dict(data_old, data_new):
                                    # different data
                                    res_sub_data_list = generate_action_data_and_append(res_sub_data_list, 'PUT', data_new)
                                    break
        else:
            LOGGER.error(f"Type error, yout data type: {type(new_data[key])}")
            LOGGER.error(f"Values in old_data: {old_data[key]}")
            LOGGER.error(f"Values in new_data: {new_data[key]}")
            raise HTTPException(status_code=400, detail='Data type error')

        # If not empty list, create in res_data
        if res_sub_data_list:
            res_data[key] = res_sub_data_list
    LOGGER.debug(f"Diff data: {res_data}")
    return res_data


def generate_diff_data(device_name, old_data, new_device_data, new_gui_data):
    """ Generate data structure ready to save in staging db """
    res_data = {}
    res_data['name'] = device_name
    res_data['old_data'] = old_data
    res_data['new_device_data'] = new_device_data
    res_data['new_gui_data'] = new_gui_data
    diff_detail_device_data = {}
    diff_detail_gui_data = {}
    if new_device_data:
        # if is not empty {}
        diff_detail_device_data = generate_diff_data_detail(old_data, new_device_data)
    if new_gui_data:
        # if is not empty {}
        diff_detail_gui_data = generate_diff_data_detail(old_data, new_gui_data)
    res_data['detail'] = {'device_config': diff_detail_device_data, 'gui_config': diff_detail_gui_data}

    return res_data


def compare_device_config(device_name, old_data, new_data, staging_type: str):
    """
    Compare two device template with deepdiff and response what data we want to keep in fullinfo db
    Input:
    staging_type: device, gui
    """
    staging_db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                            settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['STAGING']['COL'])

    if staging_db.check_exist_one_by_name(device_name):
        # staging db exists data
        staging_data = staging_db.get_one_by_name(device_name)
        if staging_type == 'device':
            if not compare_two_device_template_dict(new_data, staging_data['new_device_data']):
                # input data is same as old staging data, not action
                return old_data
            else:
                staging_device_data = new_data
                staging_gui_data = staging_data['new_gui_data']
        elif staging_type == 'gui':
            if not compare_two_device_template_dict(new_data, staging_data['new_gui_data']):
                # input data is same as old staging data, not action
                return old_data
            else:
                staging_device_data = staging_data['new_device_data']
                staging_gui_data = new_data

        # when data is not empty, check data, otherwise, empty {}
        diff_device_data = {}
        diff_gui_data = {}
        if staging_device_data:
            diff_device_data = compare_two_device_template_dict(old_data, staging_device_data)
        if staging_gui_data:
            diff_gui_data = compare_two_device_template_dict(old_data, staging_gui_data)

        if not diff_device_data and not diff_gui_data:
            # All same, delete data
            LOGGER.warning(f"Device {device_name} template config data (new_data) is same as old_data, delete data in staging db!")
            staging_db.delete_one_by_name(device_name)
        else:
            # data has difference, update staging db
            LOGGER.warning(f"Device {device_name} template config data from {staging_type} has changed, update data in staging db!")
            diff_data = generate_diff_data(device_name, old_data, staging_device_data, staging_gui_data)
            filter_dict = {'name': device_name}
            _ = update_db_data(staging_db, filter_dict, diff_data, "device template config data")
    else:
        # staging db no data.
        res_diff = compare_two_device_template_dict(old_data, new_data)
        if not res_diff:
            # no action
            return old_data
        else:
            # generate diff data, insert to staging db
            if staging_type == 'device':
                staging_device_data = new_data
                staging_gui_data = {}
            elif staging_type == 'gui':
                staging_device_data = {}
                staging_gui_data = new_data
            diff_data = generate_diff_data(device_name, old_data, staging_device_data, staging_gui_data)
            staging_db.write_one(diff_data)
    return old_data


def set_device_info_4_fullinfo_db(content, skip_compare):
    """
    Description: Handle device basic report and save in fullinfo db
    Input:
    skip_compare: True/False
    """
    db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                    settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['FULLINFO']['COL'])

    device_fullinfo = content.dict(by_alias=True)
    # Check wans.isp_name
    device_fullinfo['wans'] = gen_device_wans_isp(device_fullinfo['wans'])

    if db.check_exist_one_by_name(device_fullinfo['name']):
        if not skip_compare:
            # status = deployed(1), check diff
            old_device_info = db.get_one_by_name(device_fullinfo['name'])
            device_fullinfo['device_config'] = compare_device_config(device_fullinfo['name'],
                                                                     old_device_info['device_config'],
                                                                     device_fullinfo['device_config'],
                                                                     'device')
            LOGGER.debug(device_fullinfo['device_config'])
        else:
            # status = pre-deploy(0), upgrading(2), skip check diff and clean staging db
            staging_db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                                    settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['STAGING']['COL'])
            if staging_db.check_exist_one_by_name(device_fullinfo['name']):
                LOGGER.warning(f"Skip compare, clean staging db if existed, device_name: {device_fullinfo['name']}")
                staging_db.delete_one_by_name(device_fullinfo['name'])

        LOGGER.warning(f"Update device {device_fullinfo['name']} basic report in fullinfo db!")
        LOGGER.debug('Update device full info, content:')
        LOGGER.debug(device_fullinfo)
        filter_dict = {'name': device_fullinfo['name']}
        _ = update_db_data(db, filter_dict, device_fullinfo, "device full info")
    else:
        LOGGER.debug('Insert device full info, content:')
        LOGGER.debug(device_fullinfo)
        db.write_one(device_fullinfo)

    return


def check_stage_data_before_update_db(update_data: dict):
    """ Parsing and checking staging data """
    # Parsing data without None value
    send_data = {i: update_data[i] for i in update_data if update_data[i] is not None}

    # Check send_data when has port_forwarding key, assign 'tcp udp' when ui send 'tcp+udp'
    if 'port_forwarding' in send_data:
        if 'proto' in send_data["port_forwarding"]:
            if 'tcp+udp' in send_data["port_forwarding"]["proto"]:
                send_data["port_forwarding"]["proto"] = 'tcp udp'
    elif 'firewall' in send_data:
        if 'proto' in send_data["firewall"]:
            if 'tcp+udp' in send_data["firewall"]["proto"]:
                send_data["firewall"]["proto"] = 'tcp udp'

    LOGGER.warning('Update data after parsing stage data')
    LOGGER.warning(send_data)
    del send_data['name']
    del send_data['action']

    return send_data


def stage_data_validation(action, input_data):
    # Check input data key is in white list or not
    stage_method_white_list = {
        'POST': ['dhcp', 'firewall', 'port_forwarding', 'routes', 'l7_policy'],
        'PUT': ['wans', 'lans', 'dhcp', 'firewall', 'port_forwarding', 'model_name', 'l7_policy'],
        'DELETE': ['dhcp', 'firewall', 'port_forwarding', 'routes', 'l7_policy']
    }
    if action not in stage_method_white_list:
        LOGGER.error('Update Data action not in white list')
        LOGGER.error('Error data:')
        LOGGER.error(input_data)
        raise HTTPException(status_code=400, detail='Update Data action error')

    # parse stage input data before update db
    update_data_by_parse = check_stage_data_before_update_db(input_data)

    device_key = ""
    try:
        device_key = list(update_data_by_parse.keys())[0]
        LOGGER.warning(f"Update Data in key ({device_key})")
    except IndexError:
        LOGGER.error('Update Data key not in white list')
        LOGGER.error('Error data:')
        LOGGER.error(input_data)
        raise HTTPException(status_code=400, detail='Update Data key error')

    if device_key not in stage_method_white_list[action]:
        LOGGER.error('Update Data key not in white list')
        LOGGER.error('Error data:')
        LOGGER.error(input_data)
        raise HTTPException(status_code=400, detail='Update Data key error')
    return device_key, update_data_by_parse


def get_stage_data_in_db(device_name: str):
    """ Get the original staging data in db """
    staging_db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                            settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['STAGING']['COL'])
    fullinfo_db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                             settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['FULLINFO']['COL'])

    diff_data = {'old_data': {}, 'new_device_data': {}, 'new_gui_data': {}}
    if staging_db.check_exist_one_by_name(device_name):
        # get the old staging data from staging_db['new_gui_data']
        diff_data = staging_db.get_one_by_name(device_name)

    if staging_db.check_exist_one_by_name(device_name) and diff_data['new_gui_data']:
        original_stage_old_data = diff_data['old_data']
        original_stage_new_data = diff_data['new_gui_data']
    elif fullinfo_db.check_exist_one_by_name(device_name):
        # get the old staging data from fullinfo_db['device_config']
        device_data = fullinfo_db.get_one_by_name(device_name)
        original_stage_old_data = copy.deepcopy(device_data['device_config'])
        original_stage_new_data = copy.deepcopy(device_data['device_config'])
    else:
        LOGGER.error(f"Update Data devcie name not in both db, {device_name}.")
        raise HTTPException(status_code=400, detail=f"Input device name not found in both db, {device_name}")

    return original_stage_old_data, original_stage_new_data


def check_input_stage_data_and_assign_value(old_data, new_data, action, key):
    """
    Description: Parse the data and assign new data in old data
    Input:
    old_data: Device config template structure
    [refs]: https://hackmd.io/ussreznjSbWUcdLQ3Kp3xQ?view#Device-full-info-hermesvpndevicefullinfo
    new_data: Device config template update structure
    [refs]: https://hackmd.io/d3L8aTdeQHSZ13sviVv9Gw?view#POST-Add-staging-config-from-GUI--gt-devicemgr--gt-mongo
    action: POST, PUT, DELETE
    key: wans, lans, dhcp, firewall, port_forwarding, routes, controller, tunnel_gateway, model_name
    """
    LOGGER.debug("===============Before================")
    LOGGER.debug(old_data[key])
    LOGGER.debug("=====================================")
    if type(new_data[key]) is dict:
        # key = wans, lans, dhcp, firewall, port_forwarding, routes, l7_policy
        if key == 'dhcp':
            primary_key = 'lan_name'
        else:
            primary_key = 'name'
        if action == 'POST' or action == 'PUT':
            # Get matching dict in old data
            if type(old_data[key]) is list:
                d = next((item for item in old_data[key] if item[primary_key] == new_data[key][primary_key]), None)
            else:
                LOGGER.error(f"The original stage data error, data type: {type(old_data[key])}.")
                raise HTTPException(status_code=400, detail=f"The original stage data error, data type: {type(old_data[key])}")
            if action == 'POST' and d is None:
                old_data[key].append(new_data[key])
            elif action == 'PUT' and d is not None:
                d.update(new_data[key])
            else:
                LOGGER.error('Update stage data key error. You might post new key or put old key')
                LOGGER.error(f"Data in db, {old_data[key]}")
                LOGGER.error("=====================================")
                LOGGER.error(f"Data you input, {new_data[key]}")
                LOGGER.error("=====================================")
                raise HTTPException(status_code=400, detail='Update stage data key error.')
        elif action == 'DELETE':
            # Get delete name list from input data
            if 'stage_del_name_list' not in new_data[key]:
                LOGGER.error('Update stage data error, delete data is not correct. no key stage_del_name_list')
                LOGGER.error(f"Data you want to delete, {new_data[key]}")
                LOGGER.error("=====================================")
                raise HTTPException(status_code=400, detail='Delete data list input error.')
            delete_list = [item[primary_key] for item in list(new_data[key].values())[0]]
            # Update list
            old_len = len(old_data[key])
            old_data[key][:] = [item for item in old_data[key] if item[primary_key] not in delete_list]
            new_len = len(old_data[key])
            if new_len == old_len:
                LOGGER.error('Update stage data error, delete data is not existed in db.')
                LOGGER.error(f"Data in db, {old_data[key]}")
                LOGGER.error(f"Data you want to delete, {delete_list}")
                LOGGER.error("=====================================")
                raise HTTPException(status_code=400, detail='Delete data list input error.')
        else:
            LOGGER.critical("Strange status, suppose not in here!!!!")
            LOGGER.critical(new_data)
            raise HTTPException(status_code=400, detail='Action error or key Error')
    elif type(old_data[key]) is list and type(new_data[key]) is str:
        # key = controller, tunnel_gateway
        if action == 'POST':
            if len(set(old_data[key]).intersection(new_data[key])) > 0:
                LOGGER.error("Some data is existed in db, should not append again")
                LOGGER.error(f"Data in db: {old_data[key]}")
                LOGGER.error(f"Data you input: {new_data[key]}")
                raise HTTPException(status_code=400, detail='Input data error.')
            old_data[key] = old_data[key] + new_data[key]
        elif action == 'DELETE':
            if set(old_data[key]).intersection(new_data[key]) != set(new_data[key]):
                LOGGER.error("Some data is not existed in db, should not delete")
                LOGGER.error(f"Data in db: {old_data[key]}")
                LOGGER.error(f"Data you input: {new_data[key]}")
                raise HTTPException(status_code=400, detail='Input data error.')
        else:
            LOGGER.critical("Strange status, suppose not in here!!!!")
            LOGGER.critical(new_data)
            raise HTTPException(status_code=400, detail='Action error or key Error')
    elif type(old_data[key]) is str and type(new_data[key]) is str:
        # key = model_name
        if action == 'PUT':
            old_data[key] = new_data[key]
        else:
            LOGGER.critical("Strange status, suppose not in here!!!!")
            LOGGER.critical(new_data)
            raise HTTPException(status_code=400, detail='Action error or key Error')
    else:
        LOGGER.error(f"Update Data in ({key}) failed. Data type must be list, dict, str.")
        raise HTTPException(status_code=400, detail='Input value type is not supported: (list, dict, str)')

    LOGGER.debug("==============After==================")
    LOGGER.debug(old_data[key])
    LOGGER.debug("=====================================")
    return old_data


def update_device_stage_info(update_data: dict):
    """ Parsing and checking update staging data and save in staging db """
    device_name = update_data['name']
    device_action = update_data['action']
    LOGGER.warning('Update device stage info from GUI')
    LOGGER.warning(f"device name: {device_name}, action: {device_action}")

    # 1. Validate data first and get the device update key
    device_key, stage_data = stage_data_validation(device_action, update_data)

    # 2. Get the stage data (old and new) from db
    stage_old_data, stage_new_data = get_stage_data_in_db(device_name)

    # 3. Check original_data and stage_data and return new data
    new_data = check_input_stage_data_and_assign_value(stage_new_data, stage_data, device_action, device_key)

    # 4. Compare original data and new data, and write in staging db
    _ = compare_device_config(device_name, stage_old_data, new_data, 'gui')

    return new_data


def apply_device_stage_info(device_name, input_data):
    """
    Apply device staging from db to device:
    Input:
    device_name: SDWAN-xx-xx-xx-xx-xx-xx
    input_data:
    {
        "ip": "hermes deivce ip"
        "use_data": 'old_data' or 'new_data'
    }
    """
    device_ip = input_data['ip']
    LOGGER.warning(f"Apply device staging info to device, device name: {device_name}, device ip: {device_ip}")

    staging_db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                            settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['STAGING']['COL'])
    fullinfo_db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                             settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['FULLINFO']['COL'])

    if not staging_db.check_exist_one_by_name(device_name):
        LOGGER.error(f"Staging db can not find the device name, {device_name}")
        LOGGER.error(f"Input data from gui, {input_data}")
        raise HTTPException(status_code=400, detail='Input data error, please check device_name.')

    if not fullinfo_db.check_exist_one_by_name(device_name):
        LOGGER.error(f"Fullinfo db can not find the device name, {device_name}")
        LOGGER.error(f"Input data from gui, {input_data}")
        raise HTTPException(status_code=400, detail='Input data error, please check device_name.')

    if input_data['use_data'] == 'old_data':
        # Don't know need to apply old_data to device or not
        LOGGER.warning("User choose old staging data. Should not apply any configuration.")
    elif input_data['use_data'] == 'new_device_data' or input_data['use_data'] == 'new_gui_data':
        LOGGER.warning(f"User choose {input_data['use_data']}. Apply now!!")
        # 1. Get staging data from db
        staging_data = staging_db.get_one_by_name(device_name)

        # 2. Apply the new data to agent
        if input_data['use_data'] == 'new_device_data':
            send_data = staging_data['detail']['device_config']
            original_data = staging_data['new_device_data']
        else:
            send_data = staging_data['detail']['gui_config']
            original_data = staging_data['new_gui_data']
        LOGGER.warning('Sending update agent data:')
        LOGGER.warning(send_data)

        send_api = f"http://{device_ip}:9000/config/apply"
        res_data, res_code = send_restful(send_api, req_type='post', payload=send_data, time_out=8)

        LOGGER.debug(f"Response from agent res_code: {res_code}")
        LOGGER.debug(res_data)

        if res_code != 201:
            LOGGER.error(f"Update Data failed. Device id: {device_name}, sending url: {send_api}")
            LOGGER.error(f"res_code: {res_code}")
            LOGGER.error(f"res_data: {res_data}")
            LOGGER.error(f"sending data: {send_data}")
            raise HTTPException(status_code=400, detail=res_data)

        # 3. devicemgr put the new data which you choose from staging db in fullinfo db
        fullinfo_data = fullinfo_db.get_one_by_name(device_name)
        fullinfo_data['device_config'] = original_data
        LOGGER.warning("-----------------------")
        LOGGER.warning(f"original_data in devicemgr: {original_data}")
        LOGGER.warning("-----------------------")

        # 4. update data response from device, the res_data will be fullinfo data structure
        for key, value in res_data.items():
            if key == 'name':
                pass
            else:
                try:
                    LOGGER.warning("Data from device when apply -------")
                    LOGGER.warning(f"key: {key}")
                    LOGGER.warning(f"value: {value}")
                    LOGGER.warning("----------------------------------")
                    fullinfo_data[key] = value
                except KeyError:
                    LOGGER.error(f"Update Data failed. Device id: {device_name}. Response data from agent:")
                    LOGGER.error(res_data)
                    LOGGER.error(f"The key does not in fullinfo data model, key: {key}")
                    LOGGER.error(f"Original_data: {original_data}")
                    raise HTTPException(status_code=400, detail='Key error, please check!!!!!')
        filter_dict = {'name': device_name}
        _ = update_db_data(fullinfo_db, filter_dict, fullinfo_data, "device fullinfo")
    else:
        LOGGER.critical('In strange part, apply error!!!!')
        LOGGER.critical(f"Input data from gui, {input_data}")
        raise HTTPException(status_code=400, detail='Input data error, please check.')

    LOGGER.info(f"Delete device staging data in staging db, device name: {device_name}")
    staging_db.delete_one_by_name(device_name)
    return input_data
