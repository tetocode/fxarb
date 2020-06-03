import os

import time

from pychrome import Driver
from pychrome.test_utils import new_browser, TEST_ADDR
import logging

logging.basicConfig(level=logging.DEBUG)


def test_connection():
    driver = Driver(TEST_ADDR)

    for conn in driver.connections('.*'):
        conn.enable('DOM')
        res = conn.navigate('file://' + os.path.join(os.getcwd(), 'test_main.html'))
        #        conn.get_html('iframe')
        conn.get_html_all('iframe')
        time.sleep(1.0)
        print(conn.frame_ids)
        print(res)
