import glob
import logging
import os
import random
import re
import sys
import time
from typing import List, Tuple, Dict, Iterator

from PIL import Image
from docopt import docopt
from gevent.threading import Lock

import env
import timeutil
from rpcserver import Slave

try:
    import win32gui
    import win32ui
    import win32con
except ImportError:
    pass

from recognizer import Recognizer


class CaptureServer(Slave):
    def __init__(self, name, bind_address, *, title_re: str, instruments: List[str] = (),
                 capture_rects: List[Dict[str, Tuple]], filter_mode: int = 0,
                 chrome: bool = False,
                 master_address):
        super().__init__(name, bind_address, master_address=master_address)
        self.service = name
        self.title_re = title_re
        self.instruments = instruments or ([''] * len(capture_rects))
        self.capture_rects = capture_rects
        self.last_handle = None
        self.chrome = chrome
        self.recognizer = Recognizer(name=name, in_width=16, in_height=16, n_units=100, n_out=128,
                                     filter_mode=filter_mode,
                                     chrome=chrome)
        self._lock = Lock()

    def __getattr__(self, item):
        return getattr(self.recognizer, item)

    @property
    def dir_path(self):
        if self.chrome:
            path = self.name + '_chrome'
        else:
            path = self.name
        path = os.path.join(env.get_desktop_dir(), 'capture_data', path)
        os.makedirs(path, exist_ok=True)
        return path

    def gen_images(self, *, crop: bool, n: int = None) -> Iterator:
        def gen():
            nonlocal n
            files = glob.glob(os.path.join('.', self.dir_path, '*.png'))
            n = min(n or len(files), len(files))
            for f in sorted(random.sample(files, n)):
                img = Image.open(f)
                self.logger.info('Image loaded from {}'.format(f))
                if crop:
                    for rect_d in self.capture_rects:
                        for rect in rect_d.values():
                            yield img.crop(rect)
                else:
                    yield img

        return gen()

    def find_window(self, title_re: str):
        for handle in self.iter_windows(title_re=title_re):
            return handle
        return None

    @classmethod
    def iter_windows(cls, title_re: str):

        title_match = re.compile(title_re)

        handles = []

        def callback(hwnd, *_):
            title = win32gui.GetWindowText(hwnd)
            if title_match.match(title):
                handles.append(hwnd)

        win32gui.EnumWindows(callback, None)
        for handle in handles:
            yield handle

    @classmethod
    def get_window_title(cls, handle):
        return win32gui.GetWindowText(handle)

    def capture(self):
        if os.name == 'nt':
            return self.capture_window(self.last_handle)
        if os.name == 'posix':
            try:
                files = glob.glob(os.path.join(self.dir_path, '*.png'))
                return Image.open(random.choice(files))
            except Exception as e:
                self.logger.exception(str(e))
                self.last_handle = None
        assert False

    @classmethod
    def capture_window(cls, handle):
        assert env.is_windows()
        left, top, right, bottom = win32gui.GetWindowRect(handle)
        width, height = right - left, bottom - top
        hwnd_dc = win32gui.GetWindowDC(handle)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        save_dc.SetWindowOrg((0, 0))  # 13, 151))
        save_bit_map = win32ui.CreateBitmap()

        save_bit_map.CreateCompatibleBitmap(mfc_dc, width, height)  # 287, 76)
        save_dc.SelectObject(save_bit_map)
        #    result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 0)
        win32gui.BitBlt(save_dc.GetSafeHdc(), 0, 0, width, height, hwnd_dc, 0, 0, win32con.SRCCOPY)

        bmp_info = save_bit_map.GetInfo()
        bmp_str = save_bit_map.GetBitmapBits(True)
        im = Image.frombuffer(
            'RGB',
            (bmp_info['bmWidth'], bmp_info['bmHeight']),
            bmp_str, 'raw', 'BGRX', 0, 1)

        win32gui.DeleteObject(save_bit_map.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(handle, hwnd_dc)
        return im

    def get_prices(self) -> List[dict]:
        if not self.last_handle:
            self.last_handle = self.find_window(self.title_re)
        if not self.last_handle:
            return []
        img = self.capture()
        results = []
        for instrument, rect_d in zip(self.instruments, self.capture_rects):
            d = {}
            for label, rect in rect_d.items():
                d[label] = self.recognize(img.crop(rect))
            results.append(dict(service=self.service, instrument=instrument or d['instrument'],
                                bid=float(d['bid']), ask=float(d['ask'])))
        return results

    def get_accounts(self, do_refresh: bool = False) -> List[dict]:
        return []


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options] NAME

    Options:
      --master IP_PORT  [default: 127.0.0.1:10000]
      --bind IP_PORT    [default: 127.0.0.1:0]
      --make-train-data N  [default: 0]
      --train EPOCH  [default: 0]
      --snap N  [default: 0]
      --snap-interval SEC  [default: 1]
      --chrome
      --title TITLE_RE
    """.format(f=sys.argv[0]))
    name = args['NAME']
    l = args['--master'].split(':')
    master_address = (l[0], int(l[1]))
    l = args['--bind'].split(':')
    bind_address = (l[0], int(l[1]))
    train_data_n = int(args['--make-train-data'])
    epoch = int(args['--train'])
    snap_n = int(args['--snap'])
    snap_interval = float(args['--snap-interval'])
    chrome = args['--chrome']

    if args['--title']:
        title_re = args['--title']
        for i in range(snap_n):
            for handle in CaptureServer.iter_windows(title_re):
                title = CaptureServer.get_window_title(handle)
                save_dir = os.path.join(env.get_desktop_dir(), 'market_snap', name, title)
                os.makedirs(save_dir, exist_ok=True)
                img = CaptureServer.capture_window(handle)
                f_name = os.path.join(save_dir, '{}.png'.format(timeutil.jst_now().strftime('%Y%m%dT%H%M%S')))
                img.save(f_name)
                print('#{}/{} {}'.format(i + 1, snap_n, f_name))
                time.sleep(snap_interval)
        return

    server = CaptureServer(name, bind_address, master_address=master_address, chrome=chrome,
                           **server_options(name, chrome=chrome))
    if snap_n > 0:
        server.last_handle = server.find_window(server.title_re)
        for i in range(snap_n):
            img = server.capture()
            f = os.path.join(server.dir_path, timeutil.jst_now().strftime('%Y%m%dT%H%M%S.png'))
            img.save(f)
            print('#SNAP {}/{} file:{}'.format(i + 1, snap_n, f))
            time.sleep(snap_interval)
        return
    if not epoch and train_data_n <= 0:
        server.load_model()
        server.start()
        return

    server.load_model()
    server.load_train_data()
    if train_data_n:
        server.make_train_data(server.gen_images(crop=True, n=train_data_n))
        server.save_train_data()
    if epoch:
        server.train(epoch=epoch)
        server.save_model()


def server_options(name: str, *, chrome: bool = False) -> dict:
    service = name.split('.')[0]

    def gen_rects(row_n, row_h, base_top, base_bottom, **left_rights):
        rects = []
        for row in range(row_n):
            top = base_top + row * row_h
            bottom = base_bottom + row * row_h
            rects.append({label: (left, top, right, bottom) for label, (left, right) in left_rights.items()})
        return rects

    if service == 'click':
        return dict(title_re='はっちゅう君FXPlus.[0-9]',
                    capture_rects=gen_rects(18, 16, 164, 178, instrument=(28, 86), bid=(93, 151), ask=(154, 212)),
                    filter_mode=2)
    if service == 'gaitame':
        base_top = 95
        base_bottom = 109
        return dict(title_re='レート一覧 : スピード注文',
                    capture_rects=gen_rects(20, 24, base_top, base_bottom, instrument=(20, 77), bid=(94, 146), ask=(160, 212)),
                    filter_mode=1)
    if service == 'lion.net':
        return dict(title_re='レート一覧：通常注文',
                    #                    capture_rects=gen_rects(12, 27, 90, 108, instrument=(33, 115), bid=(162, 235), ask=(263, 334)),
                    capture_rects=gen_rects(10, 22, 85, 99, instrument=(25, 90), bid=(120, 167), ask=(190, 237)),
                    filter_mode=1)
    if service == 'lion':
        return dict(title_re='レート一覧 : 通常注文',
                    #                    capture_rects=gen_rects(12, 27, 90, 108, instrument=(33, 115), bid=(162, 235), ask=(263, 334)),
                    capture_rects=gen_rects(10, 27, 95, 110, instrument=(20, 100), bid=(110, 172), ask=(182, 245)),
                    filter_mode=1)
    if service == 'raku':
        instruments = [
            'USD/JPY', 'EUR/JPY', 'GBP/JPY', 'AUD/JPY', 'NZD/JPY', 'ZAR/JPY', 'CAD/JPY', 'CHF/JPY',
            'EUR/USD', 'GBP/USD', 'AUD/USD',
            # 'NZD/USD', 'USD/CHF',
            # 'GBP/CHF', 'EUR/GBP', 'EUR/CHF', 'AUD/CHF', 'NZD/CHF', 'AUD/NZD',
            # 'NOK/JPY', 'TRY/JPY', 'CNH/JPY',
        ]
        return dict(title_re='レート一覧$',
                    instruments=instruments,
                    capture_rects=gen_rects(len(instruments), 26, 85, 105, bid=(160, 224), ask=(234, 297)),
                    filter_mode=1)
    if service == 'sbi':
        instruments = [
            'USD/JPY', 'EUR/JPY', 'GBP/JPY',
            'AUD/JPY', 'NZD/JPY', 'CAD/JPY', 'CHF/JPY', 'ZAR/JPY', 'CNH/JPY',
            'EUR/USD', 'GBP/USD', 'AUD/USD',
        ]
        return dict(title_re='SBI FXTRADE.*レート一覧',
                    instruments=instruments,
                    capture_rects=gen_rects(len(instruments), 20, 180, 195, bid=(100, 160), ask=(180, 240)))
    if service == 'ultra':
        instruments = [
            'USD/JPY', 'EUR/JPY', 'EUR/USD', 'GBP/JPY', 'GBP/USD',
            'CAD/JPY', 'AUD/JPY', 'AUD/USD', 'CHF/JPY',
        ]
        return dict(title_re='プライス一覧',
                    instruments=instruments,
                    capture_rects=gen_rects(9, 21, 87, 100,
                                            # instrument=(28, 85),
                                            bid=(106, 161), ask=(182, 237)),
                    filter_mode=3)
    #
    # browser base
    #
    if service == 'nano':
        instruments = [
            'USD/JPY', 'EUR/JPY', 'AUD/JPY', 'EUR/USD', 'GBP/JPY', 'NZD/JPY',
            'ZAR/JPY', 'CHF/JPY',
        ]
        title_re = 'パートナーズFX nano - G' if chrome else 'パートナーズFX nano - M'
        top, bottom = (280, 293) if chrome else (300, 313)
        return dict(title_re=title_re,
                    instruments=instruments,
                    capture_rects=gen_rects(len(instruments), 18, top, bottom,
                                            # instrument=(22, 100),
                                            bid=(160, 215), ask=(280, 335)))
    if service == 'pfx':
        instruments = [
            'USD/JPY', 'EUR/USD', 'AUD/JPY', 'NZD/JPY', 'GBP/JPY', 'EUR/JPY',
            'CHF/JPY', 'CAD/JPY', 'GBP/USD', 'ZAR/JPY',
        ]
        title_re = 'パートナーズFX - G' if chrome else 'パートナーズFX - M'
        top, bottom = (280, 293) if chrome else (300, 313)
        return dict(title_re=title_re,
                    instruments=instruments,
                    capture_rects=gen_rects(len(instruments), 18, top, bottom,
                                            # instrument=(22, 100),
                                            bid=(160, 215), ask=(280, 335)))
    if service == 'try':
        instruments = [
            'USD/JPY', 'EUR/JPY', 'GBP/JPY', 'AUD/JPY', 'TRY/JPY',
            'EUR/USD', 'GBP/USD', 'AUD/USD',
            'USD/CHF', 'EUR/GBP', 'NZD/USD', 'CAD/JPY',
            'EUR/AUD', 'NZD/JPY', 'CHF/JPY',
            'AUD/NZD', 'ZAR/JPY',
        ]
        title_re = 'レート - G' if chrome else 'レート - M'
        top, bottom = (136, 150) if chrome else (137, 150)
        return dict(title_re=title_re,
                    instruments=instruments,
                    capture_rects=gen_rects(len(instruments), 33, top, bottom, bid=(148, 218), ask=(220, 290)),
                    filter_mode=1)
    if service == 'yjfx':
        instruments = [
            'USD/JPY', 'EUR/JPY', 'EUR/USD',
            'AUD/JPY', 'NZD/JPY', 'GBP/JPY', 'CHF/JPY', 'CAD/JPY',
            'GBP/USD', 'ZAR/JPY', 'AUD/USD', 'NZD/USD',
        ]
        title_re = 'If00301 - G' if chrome else 'If00301 - M'
        return dict(title_re=title_re,
                    instruments=instruments,
                    capture_rects=gen_rects(len(instruments), 26, 88, 100, bid=(154, 210), ask=(240, 300)),
                    filter_mode=2)
    return {}


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
