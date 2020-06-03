import logging
import sys

import time
from docopt import docopt

from pyfxnode.hubnode import HubNode


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --bind IP_PORT    [default: 0.0.0.0:10000]
    """.format(f=sys.argv[0]))

    l = args['--bind'].split(':')
    address = (l[0], int(l[1]))

    hub = HubNode('hub', address)
    try:
        hub.start()
        while hub.is_running():
            time.sleep(1)
    finally:
        hub.stop()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
