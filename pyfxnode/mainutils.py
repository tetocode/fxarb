import logging
import socket
import sys
import time
from typing import Type

from docopt import docopt

from pyfxnode.webnode import WebNode


def web_node_main(name: str, node_type: Type[WebNode]):
    try:
        _web_node_main(name, node_type)
    except KeyboardInterrupt:
        pass


def _web_node_main(name: str, node_type: Type[WebNode]):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')

    address = socket.gethostbyname(socket.gethostname())
    args = docopt("""
        Usage:
          {f} [options]

        Options:
          --bind IP_PORT  [default: 0.0.0.0:11000]
          --proxy IP_PORT  [default: 0.0.0.0:8080]
          --chrome IP_PORT  [default: win2016:11004]
          --hub IP_PORT  [default: hub:10000]
        """.format(f=sys.argv[0], a='{}:{}'.format(*address)))

    l = args['--bind'].split(':')
    address = (socket.gethostbyname(l[0]), int(l[1]))

    l = args['--proxy'].split(':')
    proxy_address = (socket.gethostbyname(l[0]), int(l[1]))

    l = args['--chrome'].split(':')
    chrome_address = (l[0], int(l[1]))

    hub_addresses = [(hub_address.split(':')[0], int(hub_address.split(':')[1])) for hub_address in
                     args['--hub'].split(',')]

    node = node_type(name, address,
                     proxy_address=proxy_address,
                     chrome_address=chrome_address,
                     hub_addresses=hub_addresses)
    try:
        node.start()
        while node.is_running():
            time.sleep(1)
    finally:
        node.stop()


if __name__ == '__main__':
    try:
        web_node_main()
    except KeyboardInterrupt:
        pass
