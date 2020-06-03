import json
import logging
import re

import requests
from typing import Dict, Iterator, Sequence, Tuple, Optional

from .connection import Connection


class Driver:
    TIMEOUT = 5.0

    def __init__(self, address: Tuple[str, int],
                 *,
                 logger: logging.Logger = None,
                 connection_factory=None):
        self.address = address
        self._connections = {}  # type: Dict[str, Connection]
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._connection_factory = connection_factory or Connection

    def get_endpoints(self, *, types: Sequence[str] = None) -> Dict[str, dict]:
        types = types or ['page']
        r = requests.get('http://{0}:{1}/json'.format(*self.address))
        return {ep['id']: ep for ep in filter(lambda ep: ep['type'] in types, json.loads(r.text))}

    def _create_connection(self, page_id: str, connection_factory=None) -> Connection:
        connection_factory = connection_factory or self._connection_factory

        def gc_clients():
            for _id, _conn in list(self._connections.items()):
                if not _conn.is_connected():
                    self._connections.pop(_id)

        gc_clients()

        conn = self._connections.get(page_id)
        if not conn:
            ws_url = 'ws://{0}:{1}/devtools/page/{2}'.format(*self.address, page_id)
            conn = connection_factory(ws_url=ws_url, logger=self.logger)
            self._connections[page_id] = conn
        return conn

    def connections(self, url_re: str = None) -> Iterator[Connection]:
        url_re = url_re or '.*'
        if not url_re and not id:
            url_re = '.*'
        search_func = re.compile(url_re).search
        for page_id, ep in self.get_endpoints().items():
            if search_func(ep['url']):
                yield self._create_connection(page_id=ep['id'])

    def connection(self, url_re: str = None) -> Optional[Connection]:
        for conn in self.connections(url_re):
            return conn
        return None
