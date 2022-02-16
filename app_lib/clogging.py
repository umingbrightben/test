
"""
Usage:
    Same as logging.basicConfig().
    Call clogging.basicConfig() will change the default Formatter
    of all root handlers.

Example:

    import clogging
    import logging

    clogging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    logger.info('something')

Compatibility:
    This module is compatible with python2 and python3.
"""

import os
import json
import logging
import logging.config

_COLOR = {
    'CRITICAL': '\033[1;31m',
    'ERROR':    '\033[1;35m',
    'WARNING':  '\033[1;33m',
    'INFO':     '\033[1;32m',
    'DEBUG':    '\033[1;36m',
    'END':      '\033[m',
}

DEFAULT_FORMAT = '%(levelname)-8s %(asctime)s %(filename)s:%(lineno)d| %(message)s'


class ColorfulFormatter(logging.Formatter):
    def format(self, record):
        s = super(ColorfulFormatter, self).format(record)
        if record.levelname in _COLOR:
            s = _COLOR[record.levelname] + s + _COLOR['END']
        return s


def logConfig(logConfPath=None, logLevel='INFO', **kwargs):
    """ If logConfPath doesn't exist, the log will be output to stdout.  """
    config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'hermes': {
                '()': ColorfulFormatter,
                'format': DEFAULT_FORMAT
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': logLevel,
                'formatter': 'hermes',
                'stream': 'ext://sys.stdout'
            }
        },
        'root': {
            'level': logLevel,
            'handlers': ['console']
        }
    }

    if logConfPath is not None and os.path.exists(logConfPath):
        with open(logConfPath, 'rt') as f:
            config = json.load(f)

    logging.config.dictConfig(config)
