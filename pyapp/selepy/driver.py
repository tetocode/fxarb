# -*- coding:utf-8 -*-
from __future__ import division, print_function, absolute_import, unicode_literals

import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException
from .mapper import Mapper


def _get_elements(find_method,
                  is_displayed=None,
                  is_enabled=None,
                  is_selected=None,
                  is_clickable=None, # is_displayed & is_enabled
                  text=None,
                  **params):
    if is_clickable is not None:
        is_displayed = is_clickable
        is_enabled = is_clickable
    elements = None
    attributes = {}
    for k, v in params.items():
        by = getattr(By, k.upper(), None)
        if by:
            l = find_method(by, v)
            if elements is None:
                elements = l
            else:
                s = set(elements).difference(l)
                elements = list(sorted(s, key=elements.index))
        else:
            attributes[k] = v

    elements = elements or list()

    def f(x):
        if is_displayed is not None and x.is_displayed() != is_displayed:
            return False
        if is_enabled is not None and x.is_enabled() != is_enabled:
            return False
        if is_selected is not None and x.is_selected() != is_selected:
            return False
        if text and not re.search(text, x.text):
            return False
        for k, v in attributes.items():
            attr = x.get_attribute(k)
            if attr is None or not re.search(v, attr):
                return False
        return True

    return Mapper(map(_modify_element, filter(f, elements)))


def _modify_element(x):
    assert isinstance(x, webdriver.remote.webelement.WebElement)

    def wrapper(*args, **kwargs):
        try:
            return [x.find_element(*args, **kwargs)]
        except NoSuchElementException:
            return []

    x.get_elements = lambda *args, **kwargs: _get_elements(x.find_elements, *args, **kwargs)
    x.get_element = lambda *args, **kwargs: _get_elements(wrapper, *args, **kwargs)
    x.press = x.send_keys
    return x


class Driver:
    def __init__(self, driver, with_quit=True, timeout_callback=lambda: None):
        self._driver = driver
        self._with_quit = with_quit
        self._timeout_callback = timeout_callback

    def __getattr__(self, item):
        return getattr(self._driver, item)

    def get_elements(self, *args, **kwargs):
        return _get_elements(self._driver.find_elements, *args, **kwargs)

    def get_element(self, *args, **kwargs):
        def wrapper(*args, **kwargs):
            try:
                return [self._driver.find_element(*args, **kwargs)]
            except NoSuchElementException:
                return []

        return _get_elements(wrapper, *args, **kwargs)[0]

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        if self._with_quit:
            self.quit()

    def action_chains(self):
        return webdriver.common.action_chains.ActionChains(self._driver)

    def click(self, element=None, x=None, y=None):
        ac = self.action_chains()
        if element is None:
            element = self.get_elements(tag_name='html')[0]
        if x is None or y is None:
            ac = ac.move_to_element(to_element=element)
        else:
            ac = ac.move_to_element_with_offset(to_element=element,
                                                xoffset=x,
                                                yoffset=y)
        ac.click(element).perform()

    def press(self, keys):
        ac = self.action_chains()
        specials = ''
        notspecials = ''
        for key in keys:
            if ord(Keys.NULL) <= ord(key) <= ord(Keys.COMMAND):
                specials += key
            else:
                notspecials += key
        for key in specials:
            ac = ac.key_down(key)
        if notspecials:
            ac = ac.send_keys(notspecials)
        for key in reversed(specials):
            ac = ac.key_up(key)
        ac.perform()

    def wait(self, condition=lambda: False, timeout=30, interval=1):
        remaining_time = timeout
        while not condition():
            time.sleep(interval)
            remaining_time -= interval
            if remaining_time <= 0:
                self._timeout_callback()
                return False
        return True

    def wait_elements(self, timeout=30, interval=1, **kwargs):
        remaining_time = timeout
        while True:
            elements = self.get_elements(**kwargs)
            if elements:
                return elements
            time.sleep(interval)
            remaining_time -= interval
            if remaining_time <= 0:
                break
        self._timeout_callback()
        return elements

    def wait_element(self, timeout=30, interval=1, **kwargs):
        remaining_time = timeout
        while True:
            element = self.get_element(**kwargs)
            if element:
                return element
            time.sleep(interval)
            remaining_time -= interval
            if remaining_time <= 0:
                break
        self._timeout_callback()
        return element
