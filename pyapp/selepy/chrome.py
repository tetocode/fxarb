# -*- coding:utf-8 -*-
from __future__ import division, print_function, absolute_import, unicode_literals

import os

from selenium.webdriver.chrome.options import Options

from .driver import Driver
from .remote import RemoteWebDriver


class Chrome(Driver):
    def __init__(self,
                 with_quit=True,
                 timeout_callback=lambda: None, args=None, port: int = 0):
        chrome_options = Options()
        for arg in args or []:
            chrome_options.add_argument(arg)
        if os.name == 'posix':
            path = '/usr/lib/chromium-browser/chromedriver'
        elif os.name == 'nt':
            path = os.path.join('C:/Users/xps/Desktop/chromedriver.exe')
        else:
            raise Exception('no chromedriver')

        if port != 0:
            capabilities = {}
            capabilities.update(chrome_options.to_capabilities())
            driver = RemoteWebDriver(command_executor='http://127.0.0.1:{}'.format(port),
                                     desired_capabilities=capabilities)
        else:
            driver = ChromeWebDriver(path, chrome_options=chrome_options, port=port)

        Driver.__init__(self, driver,
                        with_quit=with_quit,
                        timeout_callback=timeout_callback)


from selenium.webdriver.remote.webdriver import WebDriver as _RemoteWebDriver
from selenium.webdriver.chrome.remote_connection import ChromeRemoteConnection
from selenium.webdriver.chrome.webdriver import WebDriver as ChromeWebDriver
from selenium.webdriver.chrome.service import Service as _Service

