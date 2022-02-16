import logging
import signal
import sys

from dynaconf import settings

from app_lib import clogging
from app_lib.rest_utility import send_restful
from app_lib.unbuffered_io import UnbufferedIO

# Setting Logger
LOGGER = logging.getLogger(__name__)


def signal_handler(signum, frame):
    """ Signal Handler """
    # ignore additional signals to prevent shutdown from being interrupted
    signal.signal(signum, signal.SIG_IGN)
    sig_map = {
        2: 'SIGINT',
        15: 'SIGTERM',
    }
    if signum in sig_map:
        sig_str = sig_map[signum]
    else:
        sig_str = str(signum)
    LOGGER.info('Receive signal %s', sig_str)
    sys.exit(0)


def get_microsoft_data(endpoint: str, key: str):
    send_url = f"https://eastasia.api.cognitive.microsoft.com/speechtotext/v3.0/endpoints/{endpoint}/files/logs"
    headers = {'Ocp-Apim-Subscription-Key': key}
    res_data, res_code = send_restful(send_url, req_type='get', header=headers)
    LOGGER.debug(f"Response code: {res_code}")
    LOGGER.debug(f"Response data: {res_data}")

    return res_data


def main():
    """ Device Manager main function """

    # Log part, default log will be INFO mode
    clogging.logConfig()
    # Add stderr in IO for container using
    sys.stderr = UnbufferedIO(sys.stderr)

    signal.signal(signal.SIGINT, signal_handler)  # ctrl-c
    signal.signal(signal.SIGTERM, signal_handler)  # k8s delete pod

    LOGGER.debug(settings.keys())
    # Start curl
    data = get_microsoft_data('d08dc735-0c7d-47b0-9b1d-c2f32c166415', 'bafe9cd09a7e4577b9618621110fc031')
    LOGGER.info(data)


if __name__ == '__main__':
    main()
