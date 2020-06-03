import logging
import time
from pprint import pprint

from pyfx.chromedriver import ChromeDriver


def test_driver():
    logging.basicConfig(level=logging.DEBUG)
    driver = ChromeDriver.connect(('127.0.0.1', 11000), '.*main.html')
    driver.enable('DOM', 'Network', 'Page')
    driver.update_frame_ids()
    #        gevent.sleep(3.0)
    #        return

    #        r = conn.command('DOM.getDocument')
    #        pprint(r)
    #        root_id = r['result']['root']['nodeId']
    driver.current_node_id = None
    root_id = driver.get_root_node_id()
    r = driver.command('DOM.querySelectorAll', nodeId=root_id, selector='frame,iframe')
    pprint(r)
    time.sleep(10.0)

