import base64
import random
from pprint import pformat

from typing import List, Dict, Tuple


class DOM:
    TIMEOUT = 3.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._current_node_id = None
        self.frame_ids = {}  # type: Dict[tuple, int]

    def on_dom(self, data: dict):
        method = data['method']
        params = data['params']
        if method == 'DOM.documentUpdated':
            self.current_node_id = None
            self.frame_ids.clear()
            self.logger.info('document updated. frame_ids.clear')
            for node_id in self.get_node_id_all(css_selector='frame,iframe'):
                self.command('DOM.requestChildNodes', nodeId=node_id, depth=-1)
        if method == 'DOM.setChildNodes':
            for node in params['nodes']:
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
        elif method == 'DOM.childNodeInserted':
            self.command('DOM.requestChildNodes', nodeId=params['node']['nodeId'], depth=-1)
        elif method == 'DOM.childNodeRemoved':
            node_id = params['nodeId']
            for k, v in list(self.frame_ids.items()):
                if v == node_id:
                    del self.frame_ids[k]

    def get_root_node_id(self) -> int:
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

    def get_node_id(self, css_selector: str, *, node_id: int = None) -> int:
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

    def _get_box(self, node_id: int) -> Tuple[int, int, int, int]:
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


class Input(DOM):
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


class Network:
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


class Page:
    def on_page(self, data: dict):
        if data['method'] == 'Page.frameNavigated':
            self.logger.debug('navigated to {}'.format(self.url))

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
