import logging
import os
import shlex
import shutil
import subprocess
import sys
from typing import List

from docopt import docopt

import env


def copy_profile(name: str) -> str:
    home_dir = env.get_home_dir()
    if env.is_posix():
        default_profile_dir = '{}/.config/chromium'.format(home_dir)
    elif env.is_windows():
        default_profile_dir = '{}/AppData/Local/Google/Chrome/User Data'.format(home_dir)
    else:
        raise Exception('unknown os.name {}'.format(os.name))

    profile_dir = os.path.join(env.get_desktop_dir(), 'chrome_profiles', name)
    if not os.path.exists(profile_dir):
        shutil.copytree(default_profile_dir, profile_dir)
    return profile_dir


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options] NAME

    Options:
      --port PORT  [default: 11111]
    """.format(f=sys.argv[0]))

    name = args['NAME']
    port = int(args['--port'])

    assert os.name == 'nt'
    
    path = 'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
    processes = []  # type: List[subprocess.Popen]
    profile_dir = copy_profile(name)
    chrome_args = []
    chrome_args += ['--user-data-dir="{}"'.format(profile_dir)]
    chrome_args += ['--remote-debugging-port={}'.format(port)]
    logging.info('Chrome:{}, port:{}, profile:{}'.format(name, port, profile_dir))
    processes.append(
        subprocess.Popen(args=shlex.split('\'{}\' {}'.format(path, ' '.join(chrome_args)))))

    for p in processes:
        p.wait()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
