import glob
import logging
import os
import random
import re
import sys
import time
import zlib
from collections import OrderedDict
from datetime import datetime
from pprint import pprint

import numpy as np
import pytz
from PIL import Image
from docopt import docopt

TOKYO = pytz.timezone('Asia/Tokyo')
UTC = pytz.timezone('UTC')


def snap_ultra(img):
    MAP = {
        0x9fe09b89: 'U',
        0xdb19d921: 'S',
        0x80f74f32: 'D',
        0xe3af90eb: '/J',
        0x0f21319e: 'P',
        0xc24e3188: 'Y',
        0x4245605b: '1',
        0xc22c5921: '0',
        0x95bc1186: '3',
        0xcb0bfb23: '.',
        0x4ebe405d: '9',
        0x77c1238d: '2',
        0x3a5081e7: '4',
        0xf6d57dfa: '5',
        0x7030f5f2: '7',
        0x0f59fc09: '6',
        0x29275291: 'E',
        0x929d9211: 'R',
        0x8277c019: '8',
        0xe7fce3d9: '/',
        0xf65c10df: 'G',
        0x38641042: 'B',
        0x8b3c4151: 'C',
        0x8c776560: 'A',
        0x6ce3dfcf: 'H',
        0x084f3e1e: 'F',
    }
    x_rects = [(25, 83, 87, 102), (102, 83, 165, 102), (180, 83, 243, 102), (258, 83, 321, 102)]
    y_adjust = 21
    return snap(img, MAP, x_rects, y_adjust)


def snap_lion(img):
    MAP = {
        0x21a71c7d: '6',
        0xd0fadf7d: '9',

        0xe1b5555e: 'U',
        0xa1d15f37: 'S',
        0xab56e0fe: 'D',
        0x93c71b0b: '/',
        0x1ed51344: 'J',
        0xfa92ef6c: 'P',
        0xac444b0b: 'Y',
        0xf15ecc5c: '1',
        0x81f08558: '0',
        0xc585d5fa: '3',
        0x160fa31f: '.',
        0xcc57f6a8: '4',
        0xe43c6c89: '6',
        0xe7eb0d2b: 'E',
        0xe80d4e3a: 'R',
        0xc4991c22: '5',
        0x77a8dbf5: '9',
        0xb90d38f2: '2',
        0x6d08bd09: '8',
        0x8e87a1ba: 'G',
        0x98897d11: 'B',
        0x08a48697: '7',
        0x2b04a961: 'A',
        0xf938b8c0: 'N',
        0x8b02effa: 'Z',
        0x8db0defd: 'C',
        0x14c48d49: 'H',
        0x7864befb: 'F',
        0x77e68a1e: 'T',
    }
    x_rects = [(36, 90, 114, 107), (165, 90, 233, 107), (265, 90, 333, 107)]
    y_adjust = 27
    return snap(img, MAP, x_rects, y_adjust)


def snap_gaitame(img):
    MAP = {
        0x3b0702ce: 'U',
        0xa8e81c24: 'S',
        0x0f45a8c8: 'D',
        0x368afaa4: '/',
        0x90544fbe: 'J',
        0xf5d37e0d: 'P',
        0xda9e67bf: 'Y',
        0xcbd16cc5: '1',
        0x618f0919: '0',
        0x9519d1ed: '3',
        0xcb0bfb23: '.',
        0x8dbfbffa: '4',
        0x94eb3c7d: '7',
        0x793c4070: '9',
        0x91a56d6b: '8',
        0x0ff3f547: 'E',
        0xb69236d8: 'R',
        0xc694ff73: '5',
        0x147a1277: 'A',
        0x28191570: '6',
        0xe3f77a29: '2',
        0xe5c5af83: 'G',
        0x09d5f4b7: 'B',
        0x29fda62a: 'N',
        0x3ee6b808: 'Z',
        0xebbdb5ac: 'C',
        0x3fb774b4: 'C',
        0xd148d5a4: 'H',
        0x59bab900: 'K',
    }

    x_rects = [(22, 90, 80, 105), (94, 90, 138, 105), (151, 90, 193, 105)]
    y_adjust = 22
    return snap(img, MAP, x_rects, y_adjust)


def snap_raku(img):
    MAP = {
        0x11102114: '1',
        0xa4c85c3c: '0',
        0x647c789c: '3',
        0xd16ebb6e: '.',
        0x845d22df: '6',
        0xcf61c373: '2',
        0xab4d0c3d: '1',
        0xf266629f: '0',
        0x85b9573a: '3',
        0x5dac7a89: '.',
        0x3e32ac80: '6',
        0x71e3dedf: '2',
        0x8205a3dc: '8',

        0x9e5af24b: '',
        0x2c2e64a5: '',
        0x7c973401: '',
        0x5dac7a89: '',
        0x42cc4ff9: '',
        0x1947a58b: '',
        0x7c973401: '',

        0xab4d0c3d: '',
        0xf266629f: '',
        0x250f7ce7: '',
        0xd16ebb6e: '',
        0xa0f0c195: '',
        0x43ed781b: '',
        0x35628188: '',
    }
    x_rects = [(79, 135, 142, 153), (162, 135, 216, 153), (235, 135, 290, 153)]
    x_rects = [(66, 87, 146, 104), (157, 87, 222, 104), (232, 87, 298, 104)]
    x_rects = x_rects[1:]
    y_adjust = 33
    return snap(img, MAP, x_rects, y_adjust, 80)


def snap_sbi(img):
    MAP = {
    }
    x_rects = [(36, 180, 92, 194), (100, 180, 157, 194), (180, 180, 238, 194)]
    y_adjust = 26
    return snap(img, MAP, x_rects[1:], y_adjust, threshold=-1)


def snap(img, map, x_rects, y_adjust, threshold=20):
    results = OrderedDict()
    for y in range(9):
        line = []
        for x_rect in x_rects:
            rect = list(x_rect)
            rect[1] += y_adjust * y
            rect[3] += y_adjust * y
            part = img.crop(rect)
            arr = filter_image(part, threshold=threshold)
            rects = split_chars(arr)
            word = []
            crc_list = []
            not_found_crc_list = []
            for (left, top, right, bottom) in rects:
                a = arr[top:bottom + 1, left:right + 1]
                crc = zlib.crc32(a.flatten())
                crc_list.append(crc)
                if crc not in map:
                    not_found_crc_list.append(crc)
                c = map.get(crc)
                word.append(c)
            if not_found_crc_list:
                for crc in crc_list:
                    print("  0x{:08x}: '',  ".format(crc))
                part.show()
                raise Exception('not found crc')
            word = ''.join(word)
            line.append(word)
        d = OrderedDict()
        name = line[0]
        d['bid'] = bid = float(line[1])
        d['ask'] = ask = float(line[2])
        if 'JPY' in name:
            sp = float('{:.4f}'.format((ask - bid) * 100))
        else:
            sp = float('{:.4f}'.format((ask - bid) * 10000))
        d['sp'] = sp
        results[name] = d

    return results


def filter_image(img, threshold):
    arr = np.asarray(img)
    arr.flags.writeable = True
    if threshold > 0:
        max = np.max(arr)
        min = np.min(arr)
        b = arr <= min + threshold
        b2 = arr >= max - threshold
        left_top = arr[0][0]
        arr[:] = 0
        if abs(left_top - min) < abs(max - left_top):
            arr[b] = 0
            arr[b2] = 255
        elif abs(left_top - min) > abs(max - left_top):
            arr[b] = 255
            arr[b2] = 0
        else:
            print(left_top, min, max)
            Image.fromarray(arr).save('./x.png')
            assert False
    else:
        avg = np.mean(arr)
        b = arr < avg
        b2 = arr >= avg
        left_top = arr[0][0]
        if left_top < avg:
            arr[b] = 0
            arr[b2] = 255
        else:
            arr[b] = 255
            arr[b2] = 0

    Image.fromarray(arr).save('./x.png')

    return arr


def split_chars(arr: np.ndarray):
    height, width = arr.shape
    fg = []
    bg = set()
    for x in range(width):
        px = arr[0][x]
        for y in range(height):
            if arr[y][x] != px:
                fg.append(x)
                break
        else:
            bg.add(x)
            #    assert len(fg) >= 3
    texts = []
    for x in fg:
        if (x - 1) in bg:
            texts.append(x)
        if (x + 1) in bg:
            texts.append(x)
    if len(texts) % 2 != 0:
        Image.fromarray(arr).save('./x.png')
    assert len(texts) % 2 == 0

    h_positions = []
    for i, row in enumerate(arr):
        if np.max(row) != 0:
            h_positions.append(i)
    if not h_positions:
        Image.fromarray(arr).show()
        raise Exception('h_position invaid')
    rects = []
    top = min(h_positions)
    bottom = max(h_positions)
    for a, b in zip(texts[::2], texts[1::2]):
        rect = (a, top, b, bottom)
        rects.append(rect)
    return rects


class Snapper:
    def __init__(self, title_re):
        self.title_re = title_re
        self.hwnd = None
        self.img = None

    def snap(self):
        try:
            from win32 import win32gui
        except ImportError:
            dir = self.__class__.__name__
            f_list = glob.glob(os.path.join('.', dir, '*.png'))
            f_name = f_list[random.randint(0, len(f_list) - 1)]
            self.img = Image.open(f_name)
            return self

        def find_window(title_re):
            title_match = re.compile(title_re)
            hwnd_list = []

            def callback(hwnd, *_):
                title = win32gui.GetWindowText(hwnd)
                if title_match.match(title):
                    hwnd_list.append(hwnd)

            win32gui.EnumWindows(callback, None)
            return hwnd_list

        if not self.hwnd:
            hwnd_list = find_window(self.title_re)
            if not hwnd_list or len(hwnd_list) > 1:
                raise Exception('title_re {} matches {}'.format(self.title_re, len(hwnd_list)))
            self.hwnd = hwnd_list[0]
        self.img = screengrab(self.hwnd)
        return self

    def show(self):
        if self.img:
            self.img.show()

    def save(self, fname=None):
        if not fname:
            dir = self.__class__.__name__
            os.makedirs(dir, exist_ok=True)
            fname = os.path.join('.', dir,
                                 UTC.localize(datetime.utcnow()).astimezone(TOKYO).strftime('%Y%m%dT%H%M%S.png'))
        self.img.save(fname)
        return self


class Ultra(Snapper):
    def __init__(self):
        super().__init__('プライス一覧')

    def get(self, i, j):
        x_rects = [(25, 83, 87, 102), (102, 83, 165, 102), (180, 83, 243, 102)]
        y_adjust = 21
        rect = list(x_rects[j])
        rect[1] += y_adjust * i
        rect[3] += y_adjust * i
        return self.img.crop(rect)

    def get_data(self):
        img = self.img
        col_n = 3
        row_n = 9

        results = OrderedDict()
        for row in range(row_n):
            line = []
            for col in range(col_n):
                self.get(row, col).save('./{}.png'.format(col))
            return
            for x_i, x_rect in enumerate(x_rects):
                rect = list(x_rect)
                rect[1] += y_adjust * y
                rect[3] += y_adjust * y
                part = img.crop(rect)
                arr = filter_image(part, threshold=threshold)
                rects = split_chars(arr)
                word = []
                crc_list = []
                not_found_crc_list = []
                for (left, top, right, bottom) in rects:
                    a = arr[top:bottom + 1, left:right + 1]
                    crc = zlib.crc32(a.flatten())
                    crc_list.append(crc)
                    if crc not in map:
                        not_found_crc_list.append(crc)
                    c = map.get(crc)
                    word.append(c)
                if not_found_crc_list:
                    for crc in crc_list:
                        print("  0x{:08x}: '',  ".format(crc))
                    part.show()
                    raise Exception('not found crc')
                word = ''.join(word)
                line.append(word)
            d = OrderedDict()
            name = line[0]
            d['bid'] = bid = float(line[1])
            d['ask'] = ask = float(line[2])
            if 'JPY' in name:
                sp = float('{:.4f}'.format((ask - bid) * 100))
            else:
                sp = float('{:.4f}'.format((ask - bid) * 10000))
            d['sp'] = sp
            results[name] = d

        return results
        return snap(img, MAP, x_rects, y_adjust)


class Click(Snapper):
    def __init__(self):
        super().__init__('はっちゅう君FXPlus.[0-9]')


class Sbi(Snapper):
    def __init__(self):
        super().__init__('SBI FXTRADE.*レート一覧')


class Raku(Snapper):
    def __init__(self):
        super().__init__('レート一覧$')


class Lion(Snapper):
    def __init__(self):
        super().__init__('レート一覧：通常注文')


class Gaitame(Snapper):
    def __init__(self):
        super().__init__('レート一覧 : スピード注文')


class Try(Snapper):
    def __init__(self):
        super().__init__('レート - Mozilla Firefox')


class Nano(Snapper):
    def __init__(self):
        super().__init__('パートナーズFX')


def main():
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --size SIZE  [default: 640x600]
      --config CONFIG  [default: config.yaml]

    """.format(f=sys.argv[0]))
    width, height = args['--size'].split('x')
    width, height = int(width), int(height)
    conf_file = args['--config']

    services = OrderedDict([
        ('ultra', Ultra()),
        ('click', Click()),
        ('sbi', Sbi()),
        ('raku', Raku()),
        ('lion', Lion()),
        ('gaitame', Gaitame()),
        ('try', Try()),
        ('nano', Nano()),
    ])
    services['ultra'].snap().show()
    return
    for i in range(300):
        print('#{} {}'.format(i + 1, UTC.localize(datetime.utcnow()).astimezone(TOKYO)))
        for name, service in services.items():
            try:
                service.snap()
                service.save()
            except Exception as e:
                logging.exception('{}'.format(e))
        time.sleep(60)
    return
    windows = {}

    def callback(handle, *args, **kwargs):
        title = win32gui.GetWindowText(handle)
        windows[handle] = title

    win32gui.EnumWindows(callback, None)

    service_titles = {
        'click': 'はっちゅう君FXPlus.[0-9]',
        'sbi': 'SBI FXTRADE.*レート一覧',
        'ultra': 'プライス一覧',
        'raku': 'レート一覧$',
        'lion': 'レート一覧：通常注文',
        'gaitame': 'レート一覧 : スピード注文',
        'try': 'レート - Mozilla Firefox',
        'nano': 'パートナーズFX',
    }
    services = {}
    for hwnd, title in windows.items():
        title = windows[hwnd]
        for s, t in service_titles.items():
            if re.match(t, title):
                services[s] = hwnd

    img = screengrab(services['ultra'])
    pprint(snap_ultra(img))
    img = screengrab(services['lion'])
    pprint(snap_lion(img))
    img = screengrab(services['gaitame'])
    pprint(snap_gaitame(img))
    img = screengrab(services['raku'])
    pprint(snap_raku(img))


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
