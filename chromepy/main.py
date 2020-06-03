import logging
import sys
import time
from pprint import pprint

import gevent
from docopt import docopt

from chromepy import ChromeDriver
from chromepy import Connection


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options] [-- OPTION...]

    Options:
      --new-browser   launch new browser.
      --remote-port PORT  [default: 11000]
      --profile PROFILE_DIR  [default: ./chrome_profile]
    """.format(f=sys.argv[0]))
    new_browser = args['--new-browser']
    remote_port = int(args['--remote-port'])
    profile_dir = args['--profile']

    class CustomConnection(Connection):
        def on_event(self, data: dict):
            url = None
            params = data['params']
            if 'url' in params:
                url = params['url']
            for k, v in params.items():
                if isinstance(v, dict) and 'url' in v:
                    url = v['url']
                    break
            #print(data['method'], url, params)
            pass

    driver = ChromeDriver(profile_dir=profile_dir, remote_port=remote_port, connection_factory=CustomConnection)
    start_time = time.time()
    N = 1
    for i in range(N):
        for conn in driver.connections():
            pass
    elapsed = time.time() - start_time
    print(elapsed / N)

    start_time = time.time()
    N = 1
    for i in range(N):
        for conn in driver.connections():
            print(conn.url)
    elapsed = time.time() - start_time
    print(elapsed / N)

    with driver.connection() as conn:
        conn.enable('Page', 'Network', 'DOM')  # 'DOM', 'Network')
        url = 'file:///home/mate/main.html'
        #conn.navigate(url)
        conn.update_frame_ids()
        while True:
            gevent.sleep(1)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
