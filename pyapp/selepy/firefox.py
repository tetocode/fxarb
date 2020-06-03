# -*- coding:utf-8 -*-
from __future__ import division, print_function, absolute_import, unicode_literals

import os
from selenium import webdriver
from .driver import Driver

from .remote import RemoteWebDriver

class Firefox(Driver):
    def __init__(self,
                 profile_dirname=None,
                 preferences=None,
                 ff=None,
                 with_quit=True,
                 timeout_callback=lambda: None,
                 port:int=0):
        if port != 0:
            capabilities = {}
            #capabilities.update(chrome_options.to_capabilities())
            driver = RemoteWebDriver(command_executor='http://127.0.0.1:{}'.format(port),
                                     desired_capabilities=capabilities)
        else:
            if ff is None:
                ff_dir = os.path.join(os.environ['HOME'], '.mozilla', 'firefox')
                profile = webdriver.FirefoxProfile(os.path.join(
                    ff_dir, profile_dirname))
                for k, v in (preferences or {}).items():
                    profile.set_preference(k, v)
                ff = webdriver.Firefox(profile)
                print(ff.command_executor._url)
            Driver.__init__(self, ff,
                         with_quit=with_quit,
                         timeout_callback=timeout_callback)


def test_ff():
    from selenium.webdriver.common.keys import Keys

    with Firefox('selenium') as ff:
        path = 'file://' + os.path.join(os.getcwd(), 'test.html')
        ff.press(Keys.CONTROL + 't')
        ff.wait(timeout=1)
        ff.press(Keys.CONTROL + 'w')
        ff.get(path)

        assert ff.get_element(name='button1').tag_name == 'button'
        assert ff.wait_element(name='button1').tag_name == 'button'
        assert ff.get_elements(name='button1', is_clickable=True)
        assert not ff.get_elements(is_enabled=False,
                                   is_displayed=True,
                                   name='button1')
        assert not ff.get_elements(is_enabled=True,
                                   is_displayed=False,
                                   name='button1')

        assert ff.title == 'Test'
        ff.get_elements(name='button1').click()
        assert ff.title == 'test1'
        ff.get_elements(name='button2').click()
        assert ff.title == 'test2'
        elements = ff.get_elements(tag_name='body')
        elements = elements[0].get_elements(tag_name='button')
        assert len(elements) == 2
        ff.get_elements(name='text').press('abcdefg')
        assert ff.get_elements(
            name='text')[0].get_attribute('value') == 'abcdefg'

        assert ff.wait(timeout=0,
                       condition=lambda: ff.title == 'test1') is False
        ff.get_elements(name='button1').click()
        assert ff.wait(condition=lambda: ff.title == 'test1') is True

        assert bool(ff.get_elements()[0]) is False
