import logging
import ipaddress

from app_lib.mongo_utility import DataLoader
from core.ipqueue_config import (CONFIG, MONGO_CONF, IP_Queue)

# Setting Logger
LOGGER = logging.getLogger(__name__)


def setup_ip_queue(subnet):
    """ Setup ip queue """
    LOGGER.warning('Setup ip queue. Wait a moment...')
    db = DataLoader(MONGO_CONF['ip'], MONGO_CONF['port'], MONGO_CONF['db'], CONFIG['ipqueue']['col'])

    start_ip = 1
    end_ip = 251
    net = ipaddress.ip_network(subnet)
    _ = db.get_all_elements
    for ip in net:
        tail = int(str(ip).split('.')[-1])
        if tail > start_ip and tail < end_ip and tail % 2 == 0:
            if not db.check_exist_one({'ip': str(ip)}):
                IP_Queue.put(str(ip))
    LOGGER.warning('Setup ip queue Complete')
