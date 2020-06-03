import glob
import hashlib
import logging
import os
import pickle
import random
import re
import sys
import time
from collections import OrderedDict
from pprint import pprint
from typing import List, Iterator, Dict
from typing import Tuple

import chainer
import chainer.functions as F
import chainer.links as L
import lxml.html
import numpy as np
from PIL import Image
from docopt import docopt

import selepy
import timeutil
from chainerutil import TrainableMixin


def open_file(*paths, mode='rb'):
    path = os.path.join(*paths)
    dir_name = os.path.dirname(path)
    os.makedirs(dir_name, exist_ok=True)
    return open(path, mode=mode)


class ImageFilter:
    FG = 255
    BG = 0

    def __init__(self, *, mode=0):
        self.mode = mode

    @classmethod
    def trim_margin(cls, a: np.ndarray, left=True, right=True, up=True, down=True):
        _left, top, _right, bottom = 0, 0, a.shape[1], a.shape[0]
        if left or right:
            cols = a.sum(axis=0).flatten()
            if left:
                for i, col in enumerate(cols):
                    if col:
                        _left = i
                        break
            if right:
                for i, col in enumerate(reversed(cols)):
                    if col:
                        _right = len(cols) - i
                        break
        if up or down:
            rows = a.sum(axis=1).flatten()
            if up:
                for i, row in enumerate(rows):
                    if row:
                        top = i
                        break
            if down:
                for i, row in enumerate(reversed(rows)):
                    if row:
                        bottom = len(rows) - i
                        break
        return a[top:bottom, _left:_right]

    def _filter0(self, img: Image):
        if img.mode != 'L':
            img = img.convert('L')

        a = np.asarray(img, dtype=np.float32)
        a.flags.writeable = True
        mean = a.mean()
        lt = a < mean  # less than
        ge = a >= mean  # greater equal

        if a[0][-1] < mean:
            a[lt] = self.BG
            a[ge] = self.FG
        else:
            a[lt] = self.FG
            a[ge] = self.BG
        return self.trim_margin(a)

    def _filter1(self, img: Image):
        if img.mode != 'L':
            img = img.convert('L')

        a = np.asarray(img, dtype=np.float32)
        a.flags.writeable = True
        mean = a.mean()
        lt = a < mean  # less than
        ge = a >= mean  # greater equal

        if a[0][-1] < mean:
            a[lt] = self.BG
        else:
            a[ge] = self.BG
        a[a < a.max() / 2] = self.BG
        a[a > self.BG] = self.FG
        return self.trim_margin(a)

    def filter(self, img):
        if self.mode == 0:
            return self._filter0(img)
        elif self.mode == 1:
            return self._filter1(img)
        else:
            raise Exception('unknown mode {}'.format(self.mode))


class RecognitionError(Exception):
    def __init__(self, s, img):
        super().__init__(s)
        self.img = img


class Recognizer:
    class Network(TrainableMixin, chainer.Chain):
        def __init__(self, n_in, n_units, n_out):
            super().__init__(
                l1=L.Linear(n_in, n_units),
                l2=L.Linear(n_units, n_units),
                l3=L.Linear(n_units, n_out),
            )
            self.cache = {}

        def __call__(self, x):
            h1 = F.relu(self.l1(x))
            h2 = F.relu(self.l2(h1))
            return self.l3(h2)

        def calc(self, arr: np.ndarray) -> np.int32:
            md5 = hashlib.md5(arr).hexdigest()
            value = self.cache.get(md5)
            if value is None:
                value = np.argmax(self(arr).data)
                self.cache[md5] = value
            return value

    HEIGHT = WIDTH = 14
    N_UNITS = 100

    def __init__(self, *, name=None, n_units: int = None, chars: str = None):
        self.name = name
        self.logger = logging.getLogger(name or self.__class__.__name__)
        n_in = self.HEIGHT * self.WIDTH
        n_out = self.WIDTH
        n_units = n_units or self.N_UNITS
        self.width_recognizer = Recognizer.Network(n_in, n_units, n_out)
        self._chars = chars = chars or '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ./-+'
        self.char_recognizer = Recognizer.Network(n_in, n_units, len(chars))
        self.train_data = {}

    def load_train_data(self, f_name=None):
        f_name = f_name or os.path.join(self.name, 'train_data.pickle')
        train_data = {}
        try:
            with open(f_name, 'rb') as f:
                train_data = pickle.load(f)
                if isinstance(train_data, tuple):
                    # version 0 format
                    width_data, char_data = train_data
                    train_data = {}
                    assert set(width_data.keys()) == set(char_data.keys())
                    for k, (arr, width) in width_data.items():
                        c = char_data[k][1]
                        train_data[k] = (arr, c, width)
                    self.logger.warn('version 0 format')
                else:
                    self.logger.info('version 1 format')
            self.logger.info('train_data loaded from {}'.format(f_name))
        except FileNotFoundError:
            self.logger.info('no train_data {}'.format(f_name))
        self.train_data = train_data
        return self

    def save_train_data(self, f_name):
        with open(f_name, 'wb') as f:
            pickle.dump(self.train_data, f)
            self.logger.info('train_data saved to {}'.format(f_name))
        f_name += timeutil.jst_now().strftime('.%Y%m%dT%H%M%S')
        with open(f_name, 'wb') as f:
            pickle.dump(self.train_data, f)
            self.logger.info('train_data saved to {}'.format(f_name))

    def load_model(self, f_name):
        try:
            with open(f_name, 'rb') as f:
                self.char_recognizer, self.width_recognizer = pickle.load(f)
                self.logger.info('model loaded from {}'.format(f_name))
        except FileNotFoundError:
            self.logger.warn('!!!model not loaded from {}'.format(f_name))

    def save_model(self, f_name):
        with open(f_name, 'wb') as f:
            pickle.dump((self.char_recognizer, self.width_recognizer), f)
            self.logger.info('model saved to {}'.format(f_name))

    def adjust_image(self, img: Image) -> Image:
        # arr = ImageFilter().filter(img)
        # img = Image.fromarray(arr)
        width, height = img.size
        if height > self.HEIGHT:
            width, height = int(width * self.HEIGHT / height), self.HEIGHT
            img = img.resize((width, height))
        elif height < self.HEIGHT:
            canvas = Image.new('L', (width, self.HEIGHT), ImageFilter.BG)
            canvas.paste(img, img.getbbox())
            img = canvas
        return img

    def crop_first(self, arr: np.ndarray) -> np.ndarray:
        arr = arr[:self.HEIGHT, :self.WIDTH]
        a = np.zeros((self.HEIGHT, self.WIDTH), dtype=np.float32)
        a[:arr.shape[0], :arr.shape[1]] = arr
        col_sums = a.sum(axis=0).flatten()
        for j, col_sum in enumerate(col_sums):
            if not col_sum:
                a[:, j:] = ImageFilter.BG
                break
        return a

    def recognize(self, img: Image) -> str:
        img = self.adjust_image(img)
        arr = np.asarray(img, dtype=np.float32)
        s = ''
        while arr.shape[1] > 2:
            a = self.crop_first(arr)
            width = self.width_recognizer.calc(a.reshape(1, -1))
            if not width:
                raise RecognitionError('Recoginition Error', img)
            c_index = self.char_recognizer.calc(a.reshape(1, -1))
            s += self._chars[c_index]
            arr = ImageFilter().trim_margin(arr[:, width:], up=False, right=False, down=False)
        return s

    def print_data(self, a, arr):
        a = np.array(a)
        a = ImageFilter.trim_margin(a, left=False, up=False, down=False)
        a2 = np.concatenate((a, np.zeros((a.shape[0], 5)), arr), axis=1)
        header = ''.join([str((j + 1) % 10) for j in range(a.shape[1])])
        header += '  |  '
        header += ''.join([str((j + 1) % 10) for j in range(arr.shape[1])])
        print(header)
        for line in a2:
            if np.sum(line) > 0:
                s = ''
                for c in line:
                    if c == ImageFilter.FG:
                        s += '#'
                    elif c > 180:
                        s += '+'
                    elif c > 100:
                        s += '-'
                    elif c > 0:
                        s += '.'
                    else:
                        s += ' '
                print(s)
        print(header)

    def make_train_data(self, data_iter: Iterator):
        train_data = self.train_data
        # make cache
        cache = {}
        for md5, (a, c, width) in train_data.items():
            a = np.array(a)
            a[:, width:] = ImageFilter.BG
            cache[hashlib.md5(a).hexdigest()] = (c, width)
        print('#cache len: ', len(cache))
        try:
            for img in data_iter:
                orig_img = img
                show = False
                img = self.adjust_image(img)
                arr = np.asarray(img, dtype=np.float32)
                while arr.shape[1] > 2:
                    a = self.crop_first(arr)
                    tup = train_data.get(hashlib.md5(a).hexdigest())
                    if tup:
                        c, width = tup[1:]
                    else:
                        if len(cache) > 100:
                            for right in range(a.shape[1] - 1, 5, -1):
                                _a = np.array(a)
                                _a[:, right:] = ImageFilter.BG
                                md5 = hashlib.md5(_a).hexdigest()
                                tup = cache.get(md5)
                                if tup:
                                    c, width = tup
                                    self.print_data(a, arr)
                                    print('autoset char: {}, width: {}'.format(c, width))
                                    break
                        else:
                            while True:
                                try:
                                    self.print_data(a, arr)
                                    if not show:
                                        # orig_img.show()
                                        show = True
                                    input_s = input('INPUT char width(exit to finish) # ')
                                    if input_s == 'exit':
                                        return
                                    c, width = input_s.split()
                                    assert len(c) == 1
                                    width = np.int32(width)
                                    break
                                except Exception as e:
                                    logging.exception('{}'.format(e))
                                    import time
                                    time.sleep(0.5)
                                    print('retry')
                        # a[:, width:] = ImageFilter.BG
                        train_data[hashlib.md5(a).hexdigest()] = (a, c, width)
                        _a = np.array(a)
                        _a[:, width:] = ImageFilter.BG
                        cache[hashlib.md5(_a).hexdigest()] = (c, width)

                    arr = arr[:, width:]
                    arr = ImageFilter().trim_margin(arr, up=False, right=False, down=False)
        finally:
            self.train_data = train_data

    def train(self, *, data_multiple=100, epoch=10):
        char_data = []
        width_data = []
        for arr, c, width in self.train_data.values():
            char_data.append((arr, np.int32(self._chars.index(c))))
            width_data.append((arr, width))
        pprint('width_data len {}'.format(len(width_data)))
        self.width_recognizer.train_classifier(width_data * data_multiple, width_data[:], epoch=epoch)
        pprint('char_data len {}'.format(len(char_data)))
        self.char_recognizer.train_classifier(char_data * data_multiple, char_data[:], epoch=epoch)


class Snapper:
    def __init__(self, title_re, rect_matrix: List[List[Tuple]] = None, labels: List[str] = None, chars='0123456789',
                 image_filter=None, n_units=None):
        self.title_re = title_re
        self.hwnd = None
        self.img = None
        self.orig_img = None
        self.rect_matrix = rect_matrix or [[]]
        self.labels = labels or []
        self.recognizer = Recognizer(name=self.__class__.__name__, chars=chars, n_units=n_units)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.row_labels = []
        self.image_filter = image_filter or ImageFilter()

    def load_file(self, f_name=None):
        if not f_name:
            f_list = self.saved_file_names()
            f_name = f_list[random.randint(0, len(f_list) - 1)]
        self.img = Image.open(f_name)
        self.logger.info('load_file {}'.format(f_name))
        return self

    def dir_name(self):
        return self.__class__.__name__

    def saved_file_names(self):
        return glob.glob(os.path.join('.', self.dir_name(), '*.png'))

    def train(self, make_data=False, save_train_data=True, epoch=10):
        train_data_file = os.path.join(self.__class__.__name__, 'train_data.pickle')
        recognizer = self.recognizer

        def gen_img():
            for f_name in self.saved_file_names():
                self.load_file(f_name)
                for row in self.rect_matrix:
                    d = OrderedDict()
                    for label, rect in zip(self.labels, row):
                        _img = Image.fromarray(self.image_filter.filter(self.img.crop(rect)))
                        yield _img

        recognizer.load_train_data(train_data_file)
        if make_data:
            recognizer.make_train_data(gen_img())
        recognizer.train(epoch=epoch)
        if save_train_data:
            recognizer.save_train_data(train_data_file)

    def load_model(self):
        f_name = os.path.join(self.dir_name(), 'model.pickle')
        self.recognizer.load_model(f_name)

    def save_model(self):
        f_name = os.path.join(self.dir_name(), 'model.pickle')
        self.recognizer.save_model(f_name)

    def recognize(self):
        if not self.img:
            return {}
        try:
            results = []
            for i, row in enumerate(self.rect_matrix):
                d = OrderedDict()
                if self.row_labels:
                    d['instrument'] = self.row_labels[i]
                for label, rect in zip(self.labels, row):
                    img = Image.fromarray(self.image_filter.filter(self.img.crop(rect)))
                    d[label] = self.recognizer.recognize(img)
                results.append(d)
        except RecognitionError as e:
            self.logger.exception('{}'.format(e.img))
        return {d['instrument']: d for d in results}

    def find_window(self):
        try:
            from win32 import win32gui
        except ImportError:
            return False

        def find(title_re):
            match_windows = {}

            title_match = re.compile(title_re)

            def callback(hwnd, *_):
                title = win32gui.GetWindowText(hwnd)
                if title_match.match(title):
                    match_windows[hwnd] = title

            win32gui.EnumWindows(callback, None)
            return match_windows

        windows = find(self.title_re)
        if len(windows) != 1:
            self.logger.error('title_re {} matches {}'.format(self.title_re, windows))
            return False
        self.hwnd = windows.popitem()[0]
        return True


    def snap(self):
        try:
            from win32 import win32gui
        except ImportError:
            return self.load_file()

        try:
            if not self.hwnd:
                self.hwnd = self.find_window()
            self.orig_img = screengrab(self.hwnd)
            self.img = self.orig_img.convert('L')
        except Exception as e:
            logging.exception('{}'.format(str(e)))
            self.hwnd = None
            self.img = None
        return self

    def show(self):
        if self.orig_img:
            self.orig_img.show()
        return self

    def save(self, f_name=None, mode='RGB'):
        if self.orig_img:
            if not f_name:
                dir_name = self.dir_name()
                os.makedirs(dir_name, exist_ok=True)
                f_name = os.path.join('.', dir_name,
                                      timeutil.jst_now().strftime('%Y%m%dT%H%M%S.png'))
            self.orig_img.convert(mode=mode).save(f_name)
        return self


class Scraper(Snapper):
    driver = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.window_handle = None

    def find_window(self):
        pass

    def load_model(self):
        return None

    def save_model(self):
        return None

    def snap(self):
        pass

    def init_driver(self):
        if self.driver:
            return
        if os.name == 'posix':
            Scraper.driver = selepy.Chrome(args=['--user-data-dir=/home/mate/.config/chromium'])
        elif os.name == 'nt':
            Scraper.driver = selepy.Chrome(args=['--user-data-dir=C:/Users/xps/AppData/Local/Google/Chrome/User Data'])
        else:
            raise Exception('unknown os.name {}'.format(os.name))
        Scraper.driver.get('https://www.google.com')

    def _recognize(self):
        raise NotImplementedError()

    def recognize(self):
        results = {}
        try:
            self.init_driver()
            results = self._recognize()
        except Exception as e:
            logging.exception('{}'.format(str(e)))
            self.window_handle = None
            time.sleep(1)
        return results


class Click(Snapper):
    def __init__(self):
        rect_matrix = []
        left_rights = [(28, 86), (93, 151), (154, 212)]
        top, bottom = 164, 178
        y_adjust = 16
        row_n = 18
        for i in range(row_n):
            rect_matrix.append(
                [(left, top + y_adjust * i, right, bottom + y_adjust * i) for left, right in left_rights])
        labels = ['instrument', 'bid', 'ask']
        candidates = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ./'
        super().__init__('はっちゅう君FXPlus.[0-9]', rect_matrix=rect_matrix, labels=labels, chars=candidates)
        self.row_n = row_n


class Gaitame(Snapper):
    def __init__(self):
        rect_matrix = []
        left_rights = [(20, 77), (94, 136), (150, 192)]
        top, bottom = 90, 105
        y_adjust = 22
        row_n = 20
        for i in range(row_n):
            rect_matrix.append(
                [(left, top + y_adjust * i, right, bottom + y_adjust * i) for left, right in left_rights])
        labels = ['instrument', 'bid', 'ask']
        candidates = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ./'
        super().__init__('レート一覧 : スピード注文', rect_matrix=rect_matrix, labels=labels, chars=candidates)


class Lion(Snapper):
    def __init__(self):
        rect_matrix = []
        left_rights = [(33, 115), (162, 235), (263, 334)]
        top, bottom = 90, 108
        y_adjust = 27
        row_n = 12
        for i in range(row_n):
            rect_matrix.append(
                [(left, top + y_adjust * i, right, bottom + y_adjust * i) for left, right in left_rights])
        labels = ['instrument', 'bid', 'ask']
        candidates = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ./'
        super().__init__('レート一覧：通常注文', rect_matrix=rect_matrix, labels=labels, chars=candidates)


class MNP(Scraper):
    def __init__(self):
        rect_matrix = []
        left_rights = [(12, 74), (145, 195), (264, 314)]
        top, bottom = 280, 293
        y_adjust = 18
        row_n = 10
        for i in range(row_n):
            rect_matrix.append(
                [(left, top + y_adjust * i, right, bottom + y_adjust * i) for left, right in left_rights])
        labels = ['instrument', 'bid', 'ask']
        candidates = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ./'
        super().__init__('パートナーズFX -', rect_matrix=rect_matrix, labels=labels, chars=candidates)

    def _recognize(self):
        driver = self.driver
        if not self.window_handle:
            for handle in self.driver.window_handles:
                driver.switch_to_window(handle)
                if driver.title == 'パートナーズFX':
                    self.window_handle = handle
                    break
            return {}
        driver.switch_to_window(self.window_handle)
        driver.switch_to_frame('rate')
        instruments = [
            'USD/JPY', 'EUR/USD', 'AUD/JPY',
            'NZD/JPY', 'GBP/JPY', 'EUR/JPY',
            'CHF/JPY', 'CAD/JPY', 'GBP/USD',
            'ZAR/JPY',
        ]
        bid_str = '#bidCurrencyPrice{}'
        ask_str = '#askCurrencyPrice{}'
        results = {}
        e = driver.get_element(id='PriceList')
        dom = lxml.html.fromstring(e.get_attribute('innerHTML'))
        for i, instrument in enumerate(instruments):
            i += 1
            bid = float(dom.cssselect(bid_str.format(i))[0].text_content())
            ask = float(dom.cssselect(ask_str.format(i))[0].text_content())
            results[instrument] = dict(instrument=instrument, bid=bid, ask=ask)
        return results


class Nano(Scraper):
    def __init__(self):
        rect_matrix = []
        left_rights = [(12, 74), (145, 195), (264, 314)]
        top, bottom = 280, 293
        y_adjust = 18
        row_n = 8
        for i in range(row_n):
            rect_matrix.append(
                [(left, top + y_adjust * i, right, bottom + y_adjust * i) for left, right in left_rights])
        labels = ['instrument', 'bid', 'ask']
        candidates = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ./'
        image_filter = ImageFilter(mode=1)
        super().__init__('パートナーズFX nano', rect_matrix=rect_matrix, labels=labels, chars=candidates)

    def _recognize(self):
        driver = self.driver
        if not self.window_handle:
            for handle in self.driver.window_handles:
                driver.switch_to_window(handle)
                if driver.title == 'パートナーズFX nano':
                    self.window_handle = handle
                    break
            return {}
        driver.switch_to_window(self.window_handle)
        driver.switch_to_frame('rate')
        instruments = [
            'USD/JPY', 'EUR/JPY', 'AUD/JPY',
            'EUR/USD', 'GBP/JPY', 'NZD/JPY',
            'ZAR/JPY', 'CHF/JPY',
        ]
        bid_str = '#bidCurrencyPrice{}'
        ask_str = '#askCurrencyPrice{}'
        results = {}
        e = driver.get_element(id='PriceList')
        dom = lxml.html.fromstring(e.get_attribute('innerHTML'))
        for i, instrument in enumerate(instruments):
            i += 1
            bid = float(dom.cssselect(bid_str.format(i))[0].text_content())
            ask = float(dom.cssselect(ask_str.format(i))[0].text_content())
            results[instrument] = dict(instrument=instrument, bid=bid, ask=ask)
        return results


class Raku(Snapper):
    def __init__(self):
        rect_matrix = []
        left_rights = [(65, 155), (160, 224), (234, 297)]
        left_rights = left_rights[1:]
        labels = ['instrument', 'bid', 'ask']
        labels = labels[1:]
        top, bottom = 85, 105
        y_adjust = 26
        row_labels = [
            'USD/JPY', 'EUR/JPY', 'GBP/JPY',
            'AUD/JPY', 'NZD/JPY', 'ZAR/JPY',
            'CAD/JPY', 'CHF/JPY',
            'EUR/USD', 'GBP/USD', 'AUD/USD',
            'NZD/USD', 'USD/CHF',
            'GBP/CHF', 'EUR/GBP', 'EUR/CHF',
            'AUD/CHF', 'NZD/CHF', 'AUD/NZD',
            'NOK/JPY', 'TRY/JPY', 'CNH/JPY',
        ]
        row_labels = row_labels[:11]
        for i in range(len(row_labels)):
            rect_matrix.append(
                [(left, top + y_adjust * i, right, bottom + y_adjust * i) for left, right in left_rights])
        candidates = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ./ドル円ユーロポンド豪ランドカナダスイス香港クローネトルコリラ人民元'
        image_filter = ImageFilter(mode=1)
        super().__init__('レート一覧$', rect_matrix=rect_matrix, labels=labels, chars=candidates, image_filter=image_filter)
        self.row_labels = row_labels


class Sbi(Snapper):
    def __init__(self):
        rect_matrix = []
        left_rights = [(100, 160), (180, 240)]
        top, bottom = 180, 195
        y_adjust = 20
        row_labels = [
            'USD/JPY', 'EUR/JPY', 'GBP/JPY',
            'AUD/JPY', 'NZD/JPY', 'CAD/JPY', 'CHF/JPY', 'ZAR/JPY', 'CNH/JPY',
            'EUR/USD', 'GBP/USD', 'AUD/USD',
        ]
        for i in range(len(row_labels)):
            rect_matrix.append(
                [(left, top + y_adjust * i, right, bottom + y_adjust * i) for left, right in left_rights])
        labels = ['bid', 'ask']
        candidates = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ./'
        super().__init__('SBI FXTRADE.*レート一覧', rect_matrix=rect_matrix, labels=labels, chars=candidates)
        self.row_labels = row_labels


class Try(Scraper):
    def __init__(self):
        rect_matrix = []
        left_rights = [(154, 220), (230, 293)]
        top, bottom = 137, 150
        y_adjust = 33
        row_labels = [
            'USD/JPY', 'EUR/JPY', 'GBP/JPY', 'AUD/JPY', 'TRY/JPY',
            'EUR/USD', 'GBP/USD', 'AUD/USD',
            'USD/CHF', 'EUR/GBP', 'NZD/USD', 'CAD/JPY',
            'EUR/AUD', 'NZD/JPY', 'CHF/JPY',
            'AUD/NZD', 'ZAR/JPY',
        ]
        for i in range(len(row_labels)):
            rect_matrix.append(
                [(left, top + y_adjust * i, right, bottom + y_adjust * i) for left, right in left_rights])
        labels = ['bid', 'ask']
        candidates = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ./+'
        image_filter = ImageFilter(mode=1)
        title = 'レート - Mozilla Firefox'
        title = 'レート - Google'
        super().__init__(title, rect_matrix=rect_matrix, labels=labels, chars=candidates,
                         image_filter=image_filter)
        self.row_labels = row_labels

    def _recognize(self):
        driver = self.driver
        if not self.window_handle:
            for handle in self.driver.window_handles:
                driver.switch_to_window(handle)
                if driver.title == 'レート':
                    self.window_handle = handle
                    break
            return {}
        driver.switch_to_window(self.window_handle)
        e = driver.get_element(id='rateList2')
        dom = lxml.html.fromstring(e.get_attribute('innerHTML'))
        results = {}
        for e in dom.cssselect('.currencyPair'):
            instrument = e.cssselect('td')[0].text_content()
            instrument = re.sub('[^A-Z/]', '', instrument)
            bid = e.cssselect('td.bid')[0].text_content()
            ask = e.cssselect('td.ask')[0].text_content()
            bid, ask = float(bid), float(ask)
            results[instrument] = dict(instrument=instrument, bid=bid, ask=ask)
        return results


class Ultra(Snapper):
    def __init__(self):
        rect_matrix = []
        left_rights = [(28, 85), (106, 161), (182, 237)]
        top, bottom = 87, 100
        y_adjust = 21
        row_n = 9
        for i in range(row_n):
            rect_matrix.append(
                [(left, top + y_adjust * i, right, bottom + y_adjust * i) for left, right in left_rights])
        labels = ['instrument', 'bid', 'ask']
        candidates = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ./'
        super().__init__('プライス一覧', rect_matrix=rect_matrix, labels=labels, chars=candidates)
        self.row_n = row_n


def get_services() -> Dict[str, Snapper]:
    return OrderedDict([
        ('click', Click()),
        ('gaitame', Gaitame()),
        ('lion', Lion()),
        ('mnp', MNP()),
        ('nano', Nano()),
        ('raku', Raku()),
        ('sbi', Sbi()),
        ('try', Try()),
        ('ultra', Ultra()),
    ])


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --size SIZE  [default: 640x600]
      --config CONFIG  [default: config.yaml]
      --snap SNAP_N  [default: 0]
      --service SERVICE  [default: ultra]
      --make-data

    """.format(f=sys.argv[0]))
    width, height = args['--size'].split('x')
    width, height = int(width), int(height)
    conf_file = args['--config']
    snap_n = int(args['--snap'])
    service = args['--service']
    make_data = args['--make-data']

    services = get_services()
    service = services[service]
    if snap_n:
        for i in range(snap_n):
            print('#snap', i + 1)
            service.snap()
            service.save()
            time.sleep(0.5)

    if make_data:
        service.train(make_data=True)
        service.load_file()
        last = time.time()
        pprint(service.recognize())
        print((time.time() - last))
        last = time.time()
        N = 100
        for _ in range(N):
            service.recognize()
        print((time.time() - last) / N)


def get_hwnd_from_string(hwnd_string):
    import win32gui
    hwnd = win32gui.FindWindowEx(None, 0, None, hwnd_string)
    return hwnd


def screengrab(hwnd):
    import win32gui
    import win32ui
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width, height = right - left, bottom - top
    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()
    saveDC.SetWindowOrg((0, 0))  # 13, 151))
    saveBitMap = win32ui.CreateBitmap()

    saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)  # 287, 76)
    saveDC.SelectObject(saveBitMap)
    #    result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 0)
    import win32con
    win32gui.BitBlt(saveDC.GetSafeHdc(), 0, 0, width, height, hwndDC, 0, 0, win32con.SRCCOPY)

    bmpinfo = saveBitMap.GetInfo()
    bmpstr = saveBitMap.GetBitmapBits(True)
    im = Image.frombuffer(
        'RGB',
        (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
        bmpstr, 'raw', 'BGRX', 0, 1)

    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)
    return im


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
