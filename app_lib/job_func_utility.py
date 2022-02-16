import time
import logging

from dynaconf import settings

from app_lib.func_utility import send_device_notification, update_db_data
from app_lib.mongo_utility import DataLoader

# Setting Logger
LOGGER = logging.getLogger(__name__)


def checking_device_procedure():
    """
    Description: Checking device health
    """
    # Step 1. Get fullinfo from db
    fullinfo_db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                             settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['FULLINFO']['COL'])

    monitor_db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'],
                            settings['MONGO']['DEVICE']['DB'], settings['MONGO']['DEVICE']['MONITOR']['COL'])
    device_fullinfo_list = fullinfo_db.get_all_elements()
    device_health_old = False
    device_health_new = False
    for device_dict in device_fullinfo_list:
        LOGGER.debug(device_dict)
        device_name = device_dict['name']
        # Check device health now
        timestamp_basic_report = device_dict['timestamp']
        timestamp_now = time.time()
        if abs(timestamp_basic_report - timestamp_now) < 90:
            device_health_new = True
        else:
            device_health_new = False

        monitor_data = monitor_db.get_one_by_name(device_name)
        if monitor_data:
            # There is a record in monitor db
            device_health_old = monitor_data['up']
            if device_health_old == device_health_new:
                # Status not change
                pass
            elif device_health_old and not device_health_new:
                # Status changed, old status = True, new status = False
                # Send api for device down, update db
                LOGGER.critical(f"Device down event, name: {device_name}, update db and send email.")
                subject = f"Device {device_name} down"
                detail_msg = f"Device {device_name} getting offline. Please check device power status or device network status."
                send_device_notification(device_name, subject, "CRITICAL", detail_msg, timestamp_now)
                monitor_data['up'] = device_health_new
                filter_dict = {'name': device_name}
                _ = update_db_data(monitor_db, filter_dict, monitor_data, "device monitor data")
            elif not device_health_old and device_health_new:
                # Status changed, old status = False, new status = True
                # Send api for device up, update db
                LOGGER.warning(f"Device up event, name: {device_name}, update db and send email.")
                subject = f"Device {device_name} up"
                detail_msg = f"Device {device_name} getting online."
                send_device_notification(device_name, subject, "CRITICAL", detail_msg, timestamp_now)
                monitor_data['up'] = device_health_new
                filter_dict = {'name': device_name}
                _ = update_db_data(monitor_db, filter_dict, monitor_data, "device monitor data")
        else:
            # No data in monitor db
            tmp_data = {}
            tmp_data['name'] = device_name
            if device_health_new:
                # New device online, send api for Device UP, Write db
                LOGGER.warning(f"Device up event, name: {device_name}, new device, insert db and send email.")
                subject = f"Device {device_name} up"
                detail_msg = f"Device {device_name} getting online."
                send_device_notification(device_name, subject, "CRITICAL", detail_msg, timestamp_now)
                tmp_data['up'] = True
                monitor_db.write_one(tmp_data)
            else:
                # New device, but not online, Wait next time check and write db
                LOGGER.warning(f"Device up event, name: {device_name}, new device but down now, insert db.")
                tmp_data['up'] = False
                monitor_db.write_one(tmp_data)

    return
