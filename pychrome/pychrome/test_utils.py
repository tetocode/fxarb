import logging
import os
import subprocess
import time

from typing import Tuple


def default_profile_dir():
    if os.name == 'posix':
        return '{}/.config/chromium'.format(os.environ['HOME'])
    elif os.name == 'nt':
        return '{}/AppData/Local/Google/Chrome/User Data'.format(os.environ['USERPROFILE'])
    else:
        raise Exception('unknown os.name {}'.format(os.name))

TEST_ADDR = ('127.0.0.1', 9999)

def new_browser():
    port = TEST_ADDR[1]
    profile_dir = os.path.join('/tmp', 'chrome.profile')
    chrome_args = []
    chrome_args += ['--user-data-dir={}'.format(profile_dir)]
    chrome_args += ['--remote-debugging-port={}'.format(port)]
    logging.debug('launch new browser options:{}'.format(' '.join(chrome_args)))
    if os.name == 'posix':
        subprocess.call('chromium-browser {} &'.format(' '.join(chrome_args)), shell=True)
    elif os.name == 'nt':
        path = 'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
        subprocess.call('{} {}'.format(path, ' '.join(chrome_args)), shell=True)
    else:
        assert False, 'unknown os {}'.format(os.name)
