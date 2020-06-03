import logging
import os
import shlex
import subprocess
import sys
from typing import List

from docopt import docopt


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    all_capture = ['gaitame', 'lion', 'sbi']
    all_browse = ['click', 'pfxnano', 'try', 'yjfx']
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --capture SERVICES  {all_capture} [default: ]
      --browse SERVICES  {all_browse} [default: ]
      --driver-n N  [default: 0]
      --driver PORT  [default: 9101]
    """.format(f=sys.argv[0], all_capture=','.join(all_capture), all_browse=','.join(all_browse)))

    capture_services = list(filter(str, args['--capture'].split(',')))
    browse_services = list(filter(str, args['--browse'].split(',')))
    driver_n = int(args['--driver-n'])
    driver_port = int(args['--driver'])

    processes = []  # type: List[subprocess.Popen]
    for service in capture_services:
        logging.info('CAPTURE {}'.format(service))
        path = os.path.join('captureserver.py')
        processes.append(subprocess.Popen(args=shlex.split('python {} {}'.format(path, service))))

    # driver
    for i in range(driver_n):
        logging.info('DRIVER-PORT {}'.format(driver_port + i))
        path = os.path.join('chromedriver.exe')
        processes.append(subprocess.Popen(args=shlex.split('{} --port={}'.format(path, driver_port + i))))

    for i, service in enumerate(browse_services):
        logging.info('BROWSER {} DRIVER-PORT {}'.format(service, driver_port + i))
        path = os.path.join('browseserver.py')
        processes.append(
            subprocess.Popen(args=shlex.split('python {} {} --driver={}'.format(path, service, driver_port + i))))

    for p in processes:
        p.wait()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
