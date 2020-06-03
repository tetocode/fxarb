import glob
import hashlib
import logging
import os
import pickle
import random
from typing import Tuple, List

import keras
import numpy as np
from PIL import Image

from pyfxnode.utils import jst_now_aware
from .deeputils import Classifier


class CharRecognizer:
    CHAR_FILE = 'char.h5'
    WIDTH_FILE = 'width.h5'
    TRAIN_FILE = 'train.pickle'
    C_WIDTH = 16
    C_HEIGHT = 16
    C_NUM = 128

    def __init__(self, dir_path: str):
        self.dir_path = dir_path
        try:
            self.char = Classifier.load(os.path.join(dir_path, self.CHAR_FILE))
        except FileNotFoundError:
            self.char = Classifier(self.C_WIDTH * self.C_HEIGHT, 100, 100, self.C_NUM)
        try:
            self.width = Classifier.load(os.path.join(dir_path, self.WIDTH_FILE))
        except FileNotFoundError:
            self.width = Classifier(self.C_WIDTH * self.C_HEIGHT, 100, 100, self.C_WIDTH + 1)

    def classify(self, arr: np.ndarray) -> Tuple[str, int]:
        char = chr(self.char.classify_one(arr))
        width = self.char.classify_one(arr)
        return char, width

    def save(self):
        os.makedirs(self.dir_path, exist_ok=True)
        now = jst_now_aware()
        self.char.save(os.path.join(self.dir_path, self.CHAR_FILE))
        self.char.save(os.path.join(self.dir_path, '{}.{}'.format(self.CHAR_FILE, now.strftime('%Y%m%dT%H%M%S'))))
        self.width.save(os.path.join(self.dir_path, self.WIDTH_FILE))
        self.width.save(os.path.join(self.dir_path, '{}.{}'.format(self.WIDTH_FILE, now.strftime('%Y%m%dT%H%M%S'))))

    @classmethod
    def get_boxes(cls, name: str):
        if name == 'gaitamecom':
            return []
        elif name == 'lionfx':
            return []
        elif name == 'matrixtrader':
            return []
        elif name == 'ultrafx':
            bid = (800, 130, 845, 140)
            height = 10
            n = 1
            boxes = bid,
        elif name == 'test':
            base_boxes = {
                'instrument': (1010, 275, 1065, 288),
                'bid': (1095, 275, 1145, 288),
                'ask': (1165, 275, 1212, 288),
            }
            height = 18
            n = 1
            boxes = []
            for i in range(n):
                k_boxes = {}
                for k, box in base_boxes.items():
                    k_boxes[k] = (box[0], box[1] + i * height, box[2], box[3] + i * height)
                boxes.append(k_boxes)
            return tuple(boxes)
        else:
            assert False, name

    @classmethod
    def gen_arrays(cls, name: str, img: Image.Image, box: Tuple[int, int, int, int], verbose: bool = False):
        def filter_avg(_img: Image.Image):
            colors = _img.getcolors()
            colors.sort(key=lambda x: x[1])
            px_count = _img.size[0] * _img.size[1]
            total = 0
            for count, color in reversed(colors):
                total += count * color
            avg = total / px_count
            bg = _img.getpixel((0, 0))
            if bg <= avg:
                _img = _img.point(lambda px: 0 if px <= avg else 255)
            else:
                _img = _img.point(lambda px: 0 if px > avg else 255)
            return _img

        image_filter = filter_avg

        img = img.crop(box).convert('L')
        img = image_filter(img)
        if verbose:
            cls.print_image(img)
        img = img.crop(img.getbbox())
        if img.size[1] > cls.C_HEIGHT:
            img.thumbnail((img.size[0], cls.C_HEIGHT))
        while True:
            bbox = img.getbbox()
            if bbox is None:
                break
            cropped = img.crop((bbox[0], 0, bbox[0] + cls.C_WIDTH, cls.C_HEIGHT))
            arr = np.asarray(cropped, dtype=np.float32)
            arr.flags.writeable = True
            col_sums = arr.sum(axis=0).flatten()
            for j, col_sum in enumerate(col_sums):
                if not col_sum:
                    arr[:, j:] = 0
                    break
            shift_width = yield arr
            assert shift_width, img
            img = img.crop((bbox[0] + shift_width, 0, img.size[0], img.size[1]))

    @classmethod
    def print_image(cls, img: Image.Image):
        img = img.crop(img.getbbox())
        header = ''.join([str((j + 1) % 10) for j in range(img.size[0])])
        print(header)
        print()
        for y in range(img.size[1]):
            line = ''
            for x in range(img.size[0]):
                if img.getpixel((x, y)) == 0:
                    line += ' '
                else:
                    line += '#'
            print(line)
        print()
        print(header)

    @classmethod
    def make_train_data(cls, name: str):
        train_data = {}
        try:
            with open(cls.TRAIN_FILE, 'rb') as f:
                train_data = pickle.load(f)
                logging.info('load train_data from {}'.format(cls.TRAIN_FILE))
        except FileNotFoundError:
            pass
        to_exit = False
        boxes = cls.get_boxes(name)
        for png_path in glob.glob(os.path.join('.', '*.png')):
            orig_img = Image.open(png_path)
            for k_boxes in boxes:
                for k, box in k_boxes.items():
                    arr_generator = cls.gen_arrays(name, orig_img, box, verbose=True)
                    try:
                        arr = arr_generator.send(None)
                        while True:
                            flatten = arr.flatten()
                            md5 = hashlib.md5(arr).hexdigest()
                            if md5 not in train_data:
                                img = Image.fromarray(np.uint8(arr))
                                ret = input('char width: ')
                                if ret == 'show':
                                    img.show()
                                    continue
                                if ret == 'exit':
                                    to_exit = True
                                    break
                                if not ret:
                                    continue
                                c, shift_width = ret.split()
                                shift_width = int(shift_width)
                                train_data[md5] = (flatten, c, shift_width)
                            else:
                                _, _, shift_width = train_data[md5]
                            arr = arr_generator.send(int(shift_width))
                    except StopIteration:
                        pass
            if to_exit:
                break
        with open(cls.TRAIN_FILE, 'wb') as f:
            pickle.dump(train_data, f)
            logging.info('dump train_data to {}'.format(cls.TRAIN_FILE))

    def train(self, epoch: int = 10):
        with open(self.TRAIN_FILE, 'rb') as f:
            train_data = pickle.load(f)
        n = len(train_data)

        x = []
        char_y = []
        width_y = []
        for md5, (arr, c, shift_width) in random.sample(tuple(train_data.items()), n):
            x.append(arr)
            char_y.append(ord(c))
            width_y.append(shift_width)
        x = np.array(x)
        char_y = keras.utils.to_categorical(char_y, self.C_NUM)
        width_y = keras.utils.to_categorical(width_y, self.C_WIDTH + 1)

        train_n = n * 9 // 10
        test_n = n - train_n

        train_x = x[:train_n]
        train_char_y = char_y[:train_n]
        train_width_y = width_y[:train_n]
        test_x = x[-test_n:]
        test_char_y = char_y[-test_n:]
        test_width_y = width_y[-test_n:]

        self.char.train(train_x, train_char_y, test_x, test_char_y, epoch=epoch)
        self.width.train(train_x, train_width_y, test_x, test_width_y, epoch=epoch)

    def recognize(self, name: str, img: Image.Image) -> List[dict]:
        dict_list = []
        boxes = self.get_boxes(name)
        for k_boxes in boxes:
            d = {}
            for k, box in k_boxes.items():
                arr_generator = self.gen_arrays(name, img, box)
                s = ''
                try:
                    arr = arr_generator.send(None)
                    while True:
                        x = arr.flatten()
                        ord_c = self.char.classify_one(x)
                        s += chr(ord_c)
                        shift_width = int(self.width.classify_one(x))
                        arr = arr_generator.send(shift_width)
                except StopIteration:
                    pass
                d[k] = s
            dict_list.append(d)
        return dict_list
