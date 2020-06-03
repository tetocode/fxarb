import hashlib
import logging
import os
import pickle
import sys
from pprint import pprint
from typing import Iterator

import chainer
import chainer.functions as F
import chainer.links as L
import numpy as np
from PIL import Image
from docopt import docopt

import env
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

        if a[0][-1] >= mean:
            a = np.ones(a.shape) * 255 - a
            assert mean <= 255
            mean = 255 - mean
        # bg = a < mean  # greater equal
        # fg = a >= mean  # less than
        a[a < mean] = self.BG
        a[a < a.max() / 2] = self.BG
        a[a > self.BG] = self.FG
        return self.trim_margin(a)

    def _filter2(self, img: Image):
        if img.mode != 'L':
            img = img.convert('L')

        a = np.asarray(img, dtype=np.float32)
        a.flags.writeable = True
        mean = a.mean()

        if a[0][-1] >= mean:
            a = np.ones(a.shape) * 255 - a
            assert mean <= 255
            mean = 255 - mean
        # bg = a < mean  # greater equal
        # fg = a >= mean  # less than
        a[a < mean] = self.BG
        a[a < a.max() * 0.6] = self.BG
        a[a > self.BG] = self.FG
        return self.trim_margin(a)

    def _filter3(self, img: Image):
        if img.mode != 'L':
            img = img.convert('L')

        a = np.asarray(img, dtype=np.float32)
        a.flags.writeable = True
        mean = np.mean(a)
        lt = a < mean  # less than
        ge = a >= mean  # greater equal

        if a[0][-1] < mean:
            a[lt] = self.BG
            a[ge] = self.FG
        else:
            a[lt] = self.FG
            a[ge] = self.BG
        return self.trim_margin(a)

    def filter(self, img):
        if self.mode == 0:
            return self._filter0(img)
        elif self.mode == 1:
            return self._filter1(img)
        elif self.mode == 2:
            return self._filter2(img)
        elif self.mode == 3:
            return self._filter3(img)
        else:
            raise Exception('unknown mode {}'.format(self.mode))


class RecognitionError(Exception):
    def __init__(self, s, img):
        super().__init__(s)
        self.img = img


class Recognizer:
    class ListNetwork(TrainableMixin, chainer.ChainList):
        def __init__(self, n_in, n_units, n_out):
            super().__init__(
                L.Linear(n_in, n_units),
                L.Linear(n_units, n_units),
                L.Linear(n_units, n_out),
            )
            self.cache = {}

        def __call__(self, x):
            for i in range(len(self) - 1):
                x = F.relu(self[i](x))
            return self[-1](x)

        def calc(self, arr: np.ndarray) -> np.int32:
            md5 = hashlib.md5(arr).hexdigest()
            value = self.cache.get(md5)
            if value is None:
                value = np.argmax(self(arr).data)
                self.cache[md5] = value
            return value

    class NameNetwork(TrainableMixin, chainer.Chain):
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

    Network = NameNetwork

    def __init__(self, *, name=None, in_width: int, in_height: int, n_units: int, n_out: int, filter_mode: int = 0,
                 chrome: bool = False):
        self.name = name
        self.logger = logging.getLogger(name or self.__class__.__name__)
        self.in_width = in_width
        self.in_height = in_height
        n_in = in_width * in_height
        self.width_recognizer = Recognizer.Network(n_in, n_units, n_out)
        self.char_recognizer = Recognizer.Network(n_in, n_units, n_out)
        self.train_data = {}
        self.image_filter = ImageFilter(mode=filter_mode)
        self.chrome = chrome
        print('#', self.dir_path)

    @property
    def dir_path(self):
        if self.chrome:
            path = self.name + '_chrome'
        else:
            path = self.name
        path = os.path.join(env.get_desktop_dir(), 'model_data', path)
        os.makedirs(path, exist_ok=True)
        return path

    def load_train_data(self, f_name=None):
        f_name = os.path.join(self.dir_path, f_name or 'train_data.pickle')
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

    def save_train_data(self, f_name=None):
        f_name = os.path.join(self.dir_path, f_name or 'train_data.pickle')
        with open(f_name, 'wb') as f:
            pickle.dump(self.train_data, f)
            self.logger.info('train_data saved to {}'.format(f_name))
        f_name += timeutil.jst_now().strftime('.%Y%m%dT%H%M%S')
        with open(f_name, 'wb') as f:
            pickle.dump(self.train_data, f)
            self.logger.info('train_data saved to {}'.format(f_name))

    def serialize(self, serializer):
        self.char_recognizer.serialize(serializer)
        self.width_recognizer.serialize(serializer)

    def load_model(self, f_name=None):
        f_name = os.path.join(self.dir_path, f_name or 'model')

        def load(model, f):
            try:
                chainer.serializers.load_npz(f, model)
                self.logger.info('model loaded from {}'.format(f))
            except FileNotFoundError:
                self.logger.warn('!!!model not loaded from {}'.format(f))

        load(self.char_recognizer, f_name + '.char.npz')
        load(self.width_recognizer, f_name + '.width.npz')

    def save_model(self, f_name=None):
        f_name = os.path.join(self.dir_path, f_name or 'model')

        def save(model, f):
            try:
                chainer.serializers.save_npz(f, model)
                self.logger.info('model saved to {}'.format(f))
            except FileNotFoundError:
                self.logger.warn('!!!model not loaded from {}'.format(f))

        save(self.char_recognizer, f_name + '.char.npz')
        save(self.width_recognizer, f_name + '.width.npz')
        timestamp = timeutil.jst_now().strftime('%Y%m%dT%H%M%S')
        save(self.char_recognizer, f_name + '.char.npz' + '.' + timestamp)
        save(self.width_recognizer, f_name + '.width.npz' + '.' + timestamp)

    def adjust_image(self, img: Image) -> Image:
        orig_img = img
        arr = self.image_filter.filter(img)
        img = Image.fromarray(arr)
        # arr = ImageFilter().filter(img)
        # img = Image.fromarray(arr)
        width, height = img.size
        if height > self.in_height:
            width, height = int(width * self.in_height / height), self.in_height
            img = img.resize((width, height))
        elif height < self.in_height:
            canvas = Image.new('L', (width, self.in_height), ImageFilter.BG)
            try:
                canvas.paste(img, img.getbbox())
            except:
                raise
            img = canvas
        return img

    def crop_first(self, arr: np.ndarray) -> np.ndarray:
        arr = arr[:self.in_height, :self.in_width]
        a = np.zeros((self.in_height, self.in_width), dtype=np.float32)
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
            s += chr(int(c_index))
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
            cache_mode = 'on'
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
                        def use_cache():
                            print('#cache len: {}'.format(len(cache)))
                            for right in range(a.shape[1] - 1, 0, -1):
                                _a = np.array(a)
                                _a[:, right:] = ImageFilter.BG
                                md5 = hashlib.md5(_a).hexdigest()
                                tup = cache.get(md5)
                                if tup:
                                    c, width = tup
                                    width = np.int32(width)
                                    return c, width
                            return None, None

                        cache_unused = True
                        # if len(cache) > 100 and cache_mode:
                        if cache_mode:
                            c, width = use_cache()
                            if c is not None:
                                self.print_data(a, arr)
                                ret = input('char width: {} {} : '.format(c, width))
                                if ret == 'show':
                                    img.show()
                                    continue
                                if ret == 'exit':
                                    return
                                if ret:
                                    c, width = ret.split()
                                    width = np.int32(width)
                                cache_unused = False
                        if cache_unused:
                            while True:
                                try:
                                    self.print_data(a, arr)
                                    if not show:
                                        # orig_img.show()
                                        show = True
                                    input_s = input('INPUT char width(exit to finish) # ')
                                    if input_s == 'exit':
                                        return
                                    if input_s == 'show':
                                        img.show()
                                        continue
                                    if input_s == 'cache':
                                        c, width = use_cache()
                                        print('c: {}, width: {}'.format(c, width))
                                        continue
                                    if input_s == 'cache on':
                                        cache_mode = True
                                        print('cache-mode on')
                                        continue
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

    def train(self, *, data_multiple=1, epoch=10):
        char_data = []
        width_data = []
        for arr, c, width in self.train_data.values():
            char_data.append((arr, np.int32(ord(c))))
            width_data.append((arr, width))
        pprint('width_data len {}, char_data len {}'.format(len(width_data), len(char_data)))
        self.width_recognizer.train_classifier(width_data * data_multiple, width_data[:], epoch=epoch)
        self.char_recognizer.train_classifier(char_data * data_multiple, char_data[:], epoch=epoch)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --in-units IN  [default: 256]
      --n-units N  [default: 100]
      --out-units OUT  [default: 64]
      --load-train-data FILE
      --save-train-data FILE
      --load-model FILE
      --save-model FILE
    """.format(f=sys.argv[0]))
    in_units = args['--in-units']
    n_units = args['--n-units']
    out_units = args['--out-units']
    load_train_data = args['--load-train-data']
    save_train_data = args['--save-train-data']
    load_model = args['--load-model']
    save_model = args['--save-model']


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
