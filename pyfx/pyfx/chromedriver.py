import base64
import json
import logging
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pprint import pformat
from queue import Queue, Empty
from typing import Dict, List, Optional
from typing import Tuple, Pattern, Iterable

import requests
from websocket import WebSocketApp


class ChromeDriver:
    TIMEOUT = 5.0

    def __init__(self, address: Tuple[str, int], connection_id: str):
        self._address = address
        self._connection_id = connection_id
        self._ws_app = None  # type: WebSocketApp
        self.logger = logging.getLogger('{}.{}'.format(self.__class__.__name__, connection_id))
        self._seq_no = 0
        self._response_queues = {}  # type: Dict[int, Queue]
        self._current_node_id = None
        self.frame_ids = {}  # type: Dict[tuple, int]
        self._executor = ThreadPoolExecutor(max_workers=4)

        self._ws_app = WebSocketApp(url=self.ws_url,
                                    on_open=self.on_open,
                                    on_close=self.on_close,
                                    on_message=self.on_message,
                                    on_error=self.on_error)
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()
        self.wait_connected()

    def close(self):
        self._ws_app.close()

    def run(self):
        try:
            self._ws_app.run_forever()
        except Exception as e:
            self.logger.exception(str(e))
        self.logger.info('run_forever finished.')

    @classmethod
    def get_endpoints(cls, address: Tuple[str, int]) -> Iterable[dict]:
        r = requests.get('http://{}:{}/json'.format(address[0], address[1]))
        return tuple(filter(lambda x: x['type'] == 'page', json.loads(r.text)))

    @classmethod
    def connect(cls, address: Tuple[str, int], url_pattern: Pattern):
        endpoints = cls.get_endpoints(address)
        for endpoint in filter(lambda x: x.get('webSocketDebuggerUrl'), endpoints):
            if re.search(url_pattern, endpoint['url']):
                return ChromeDriver(address, endpoint['id'])
        raise Exception('No matched url. endoints={}'.format(endpoints))

    @property
    def ws_url(self) -> str:
        return 'ws://{}:{}/devtools/page/{}'.format(self._address[0], self._address[1], self._connection_id)

    def get_url(self) -> str:
        for endpoint in self.get_endpoints(self._address):
            if endpoint['id'] == self._connection_id:
                return endpoint['url']
        return ''

    def is_connected(self):
        return self._ws_app.sock and self._ws_app.sock.connected

    def wait_connected(self, timeout: float = 10.0) -> bool:
        start = time.time()
        while True:
            if self.is_connected():
                return True
            if time.time() - start >= timeout:
                break
            time.sleep(1e-3)  # 1 msec
        return False

    def command(self, method: str, **params) -> dict:
        self.logger.debug('#command={} params={}'.format(method, params))
        self._seq_no += 1
        seq_no = self._seq_no
        data = dict(id=seq_no, method=method, params=params)

        q = Queue()
        self._response_queues[seq_no] = q
        try:
            self._ws_app.send(json.dumps(data))
            return q.get(timeout=self.TIMEOUT)
        except Empty as e:
            if self.is_connected():
                self.logger.exception('method={} params={}\n{}'.format(method, params, str(e)))
                raise
            return dict(error='response timeout by disconnection')
        except Exception as e:
            self.logger.exception('method={} params={}\n{}'.format(method, params, str(e)))
            raise
        finally:
            del self._response_queues[seq_no]

    def enable(self, *domains):
        for domain in domains:
            self.command('{}.enable'.format(domain))

    def disable(self, *domains):
        for domain in domains:
            self.command('{}.disable'.format(domain))

    def on_open(self, ws):
        self.logger.info('#on_open')

    def on_close(self, ws):
        self.logger.info('#on_close')

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            method = data.get('method')  # type: str
            if method:
                if method.startswith('DOM.'):
                    self._executor.submit(lambda: self.on_dom(data))
                elif method.startswith('Network'):
                    self._executor.submit(lambda: self.on_network(data))
                elif method.startswith('Page'):
                    self._executor.submit(lambda: self.on_page(data))
            elif data.get('id'):
                try:
                    q = self._response_queues[data['id']]
                    q.put(data)
                except KeyError:
                    pass
        except Exception as e:
            self.logger.exception(str(e))

    def on_error(self, ws, error):
        self.logger.info('#on_error {}'.format(error))

    # DOM, Input, Network, Page
    def on_dom(self, data: dict):
        method = data['method']
        params = data['params']
        if method == 'DOM.documentUpdated':
            self.current_node_id = None
            self.frame_ids.clear()
            self.logger.info('document updated. frame_ids.clear')
            self.get_node_id_all(css_selector='frame,iframe')
        elif method == 'DOM.setChildNodes':
            self.update_frame_ids(params['nodes'])
        elif method == 'DOM.childNodeInserted':
            nodes = [params['node']]
            self.update_frame_ids(nodes)
        elif method == 'DOM.childNodeRemoved':
            node_id = params['nodeId']
            for k, v in list(self.frame_ids.items()):
                if v == node_id:
                    del self.frame_ids[k]

    def update_frame_ids(self, nodes: List[dict] = None):
        if nodes is None:
            self.current_node_id = None
            self.get_node_id_all(css_selector='frame,iframe')
            return
        for node in nodes:
            if node['localName'] in ('frame', 'iframe'):
                attributes = node['attributes']
                kv_list = list(zip(attributes[::2], attributes[1::2]))
                content_document = node['contentDocument']
                node_id = content_document['nodeId']
                for kv in kv_list:
                    self.frame_ids[kv] = node_id
                self.logger.info('ADD frame node_id={} kv_list={}'.format(node_id, kv_list))
                self.logger.info('CURRENT frame_ids=\n{}'.format(pformat(self.frame_ids)))
                self.get_node_id_all(css_selector='frame,iframe', node_id=node_id)
            self.update_frame_ids(node.get('children', []))

    def get_root_node_id(self) -> Optional[int]:
        res = self.command('DOM.getDocument')  # , traverseFrames=True)
        if 'result' not in res:
            return None
        return res['result']['root']['nodeId']

    @property
    def current_node_id(self):
        if not self._current_node_id:
            self._current_node_id = self.get_root_node_id()
        return self._current_node_id

    @current_node_id.setter
    def current_node_id(self, value):
        self._current_node_id = value

    def get_node_id(self, css_selector: str, *, node_id: int = None) -> Optional[int]:
        node_id = node_id or self.current_node_id
        res = self.command('DOM.querySelector', nodeId=node_id, selector=css_selector)
        if 'result' not in res:
            return None
        return res['result']['nodeId']

    def get_node_id_all(self, css_selector: str, *, node_id: int = None) -> List[int]:
        node_id = node_id or self.current_node_id
        res = self.command('DOM.querySelectorAll', nodeId=node_id, selector=css_selector)
        if 'result' not in res:
            return []
        return res['result']['nodeIds']

    def _get_html(self, node_id: int) -> str:
        res = self.command('DOM.getOuterHTML', nodeId=node_id)
        if 'result' not in res:
            return ''
        return res['result']['outerHTML']

    def get_html(self, css_selector: str, *, node_id: int = None) -> str:
        node_id = node_id or self.current_node_id
        node_id = self.get_node_id(css_selector=css_selector, node_id=node_id)
        return self._get_html(node_id=node_id)

    def get_html_all(self, css_selector: str, *, node_id: int = None) -> List[str]:
        node_id = node_id or self.current_node_id
        htmls = []
        for node_id in self.get_node_id_all(css_selector=css_selector, node_id=node_id):
            htmls.append(self._get_html(node_id=node_id))
        return htmls

    def get_attributes(self, css_selector: str = None, *, node_id: int = None) -> Dict[str, str]:
        node_id = node_id or self.current_node_id
        node_id = self.get_node_id(css_selector=css_selector, node_id=node_id)
        res = self.command('DOM.getAttributes', nodeId=node_id)
        if 'result' not in res:
            return {}
        l = res['result']['attributes']
        it = iter(l)
        return {k: v for k, v in zip(it, it)}

    def _get_box(self, node_id: int) -> Optional[Tuple[int, int, int, int]]:
        res = self.command('DOM.getBoxModel', nodeId=node_id)
        if 'result' not in res:
            return None
        l = res['result']['model']['content']
        return tuple(map(int, (l[0], l[1], l[2], l[-1])))

    def get_box(self, css_selector: str = None, *, node_id: int = None) -> Tuple[int, int, int, int]:
        node_id = node_id or self.current_node_id
        node_id = self.get_node_id(css_selector=css_selector, node_id=node_id)
        return self._get_box(node_id=node_id)

    def get_box_all(self, css_selector: str, *, node_id: int = None) -> List[Tuple[int, int, int, int]]:
        node_id = node_id or self.current_node_id
        boxes = []
        for node_id in self.get_node_id_all(css_selector=css_selector, node_id=node_id):
            boxes.append(self._get_box(node_id=node_id))
        return boxes

    def press(self, css_selector: str, text: str, *, node_id: int = None):
        node_id = node_id or self.current_node_id
        node_id = self.get_node_id(css_selector=css_selector, node_id=node_id)
        self.command('DOM.focus', nodeId=node_id)
        self.command('Input.dispatchKeyEvent', type='keyDown', text=text)

    def click(self, css_selector: str, *, node_id: int = None,
              offset_x: int = 0, offset_y: int = 0,
              random_pos: bool = False,
              button: str = 'left'):
        node_id = node_id or self.current_node_id
        dom_node_id = self.get_node_id(css_selector=css_selector, node_id=node_id)
        box = self.get_box(css_selector=css_selector, node_id=node_id)
        if not dom_node_id or not box:
            self.logger.warn('no such dom. css_selector:{}, box:{}'.format(css_selector, box))
            return False
        self.command('DOM.focus', nodeId=dom_node_id)
        x, y = box[0] + offset_x, box[1] + offset_y
        width, height = box[2] - box[0], box[3] - box[1]
        assert width > 0 and height > 0
        assert box[2] > box[0] and box[3] > box[1]
        if random_pos:
            x = random.randint(box[0] + width // 4, box[2] - 1 - width // 4)
            y = random.randint(box[1] + height // 4, box[3] - 1 - height // 4)
        self.command('Input.dispatchMouseEvent',
                     type='mouseMoved',
                     x=x, y=y)
        self.command('Input.dispatchMouseEvent',
                     type='mousePressed',
                     x=x, y=y,
                     button=button,
                     clickCount=1)
        self.command('Input.dispatchMouseEvent',
                     type='mouseReleased',
                     x=x, y=y,
                     button=button,
                     clickCount=1)
        return True

    def on_network(self, data: dict):
        pass

    def get_response_body(self, request_id: str):
        res = self.command('Network.getResponseBody', requestId=request_id)
        if 'error' in res:
            self.logger.info('{}'.format(res))
            return None
        body = res['result']['body']
        if res['result']['base64Encoded']:
            body = base64.b64decode(body)
        return body

    def on_page(self, data: dict):
        if data['method'] == 'Page.frameNavigated':
            self.logger.debug('navigated to {}'.format(self.get_url()))

    def navigate(self, url: str):
        res = self.command('Page.navigate', url=url)
        if 'result' not in res:
            self.logger.error('{}'.format(res))
            return
        return res['result']['frameId']

    def capture(self):
        res = self.command('Page.captureScreenshot')
        if 'result' not in res:
            self.logger.error('{}'.format(res))
            return None
        return base64.b64decode(res['result']['data'])
