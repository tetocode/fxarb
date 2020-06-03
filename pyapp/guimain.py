import logging
import sys
from typing import Tuple

import gevent
from docopt import docopt
from gsocketpool import Pool

from rpcserver import Slave, PoolClient


class Frontend(Slave):
    def __init__(self, *, bind_address: Tuple[str, int], master_address: Tuple[str, int]):
        super().__init__(name='guimain', master_address=master_address, bind_address=bind_address)
        gevent.spawn(self.run_subscribe)

    def put_data(self, data: dict):
        self.logger.info('# {}'.format(data))

    def run_subscribe(self):
        while not self.stopped:
            try:
                pool = Pool(PoolClient, dict(name=self.name, server_address=self.master_address))
                while True:
                    with pool.connection() as client:
                        client.subscribe(self.name, self.bound_address)
                    gevent.sleep(1.0)
            except Exception as e:
                self.logger.exception(str(e))
            gevent.sleep(1.0)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --master IP_PORT    [default: 127.0.0.1:10000]
      --bind IP_PORT    [default: 127.0.0.1:0]
    """.format(f=sys.argv[0]))

    l = args['--master'].split(':')
    master_address = (l[0], int(l[1]))
    l = args['--bind'].split(':')
    bind_address = (l[0], int(l[1]))

    node = Frontend(bind_address=bind_address, master_address=master_address)
    spawns = [gevent.spawn(node.start)]
    gevent.joinall(spawns)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
