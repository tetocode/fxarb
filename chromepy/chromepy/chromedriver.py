import json
import logging
import os
import re
import shutil
import subprocess
from typing import Dict, Iterator, Sequence
from typing import List

import requests

from .connection import Connection


class ChromeDriver:
    TIMEOUT = 5.0

    def __init__(self, *,
                 logger: logging.Logger = None,
                 profile_dir: str = None,
                 remote_port: int = None,
                 connection_factory=None):
        self.profile_dir = profile_dir
        self.remote_port = remote_port
        self._connections = {}  # type: Dict[str, Connection]
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._connection_factory = connection_factory or Connection


    def _create_connection(self, id: str, *, url: str, connection_factory=None) -> Connection:
        connection_factory = connection_factory or self._connection_factory

        def gc_clients():
            for _id, _conn in list(self._connections.items()):
                if not _conn.is_connected():
                    self._connections.pop(_id)

        gc_clients()

        conn = self._connections.get(id)
        if not conn:
            ws_url = 'ws://127.0.0.1:{}/devtools/page/{}'.format(self.remote_port, id)
            conn = connection_factory(ws_url=ws_url, url=url, logger=self.logger)
            self._connections[id] = conn
        conn.url = url
        return conn

    def get_endpoints(self, *, types: Sequence[str] = None) -> List[dict]:
        types = types or ['page']
        r = requests.get('http://localhost:{}/json'.format(self.remote_port))
        return list(filter(lambda ep: ep['type'] in types, json.loads(r.text)))

    def connections(self, *, url_re: str = '', id: str = None) -> Iterator[Connection]:
        if not url_re and not id:
            url_re = '.*'
        search_func = re.compile(url_re).search
        for ep in self.get_endpoints():
            if id == ep['id'] or search_func(ep['url']):
                yield self._create_connection(id=ep['id'], url=ep['url'])

    def connection(self, *, url_re: str = None, id: str = None) -> Connection:
        for conn in self.connections(url_re=url_re, id=id):
            return conn
        return None

    @property
    def default_profile_dir(self):
        if os.name == 'posix':
            return '{}/.config/chromium'.format(os.environ['HOME'])
        elif os.name == 'nt':
            return '{}/AppData/Local/Google/Chrome/User Data'.format(os.environ['USERPROFILE'])
        else:
            raise Exception('unknown os.name {}'.format(os.name))

    def new_browser(self):
        assert self.profile_dir, 'specifty valid directory self.profile_dir:{}'.format(self.profile_dir)
        profile_dir = self.profile_dir
        if not os.path.exists(profile_dir):
            shutil.copytree(self.default_profile_dir, self.profile_dir)

        chrome_args = []
        chrome_args += ['--user-data-dir={}'.format(profile_dir)]
        chrome_args += ['--remote-debugging-port={}'.format(self.remote_port)]
        self.logger.info('launch new browser options:{}'.format(' '.join(chrome_args)))
        if os.name == 'posix':
            subprocess.call('chromium-browser {} &'.format(' '.join(chrome_args)), shell=True)
        elif os.name == 'nt':
            path = 'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
            subprocess.call('{} {}'.format(path, ' '.join(chrome_args)), shell=True)
        else:
            assert False, 'unknown os {}'.format(os.name)
