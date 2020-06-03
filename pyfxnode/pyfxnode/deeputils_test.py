import contextlib
import random
import time

import keras
import numpy as np

from pyfxnode import deeputils


def test_classifier():
    stt = time.time()
    train_x = []
    train_y = []
    for i in range(100):
        a, b = random.randint(0, 9), random.randint(0, 9)
        train_x.append([a, b])
        train_y.append((a + b) % 2)
    test_x = []
    test_y = []
    for i in range(100):
        a, b = random.randint(0, 9), random.randint(0, 9)
        test_x.append([a, b])
        test_y.append((a + b) % 2)

    train_x = np.array(train_x)
    train_y = keras.utils.to_categorical(train_y, 2)
    test_x = np.array(test_x)
    test_y = keras.utils.to_categorical(test_y, 2)

    for i in range(10):
        n_units = [
            2, 100, 100, 2
        ]
        try:
            model = deeputils.Classifier.load('/tmp/model.h5')
        except FileNotFoundError:
            model = deeputils.Classifier(*n_units, use_cache=False)
        model.train(train_x, train_y, test_x, test_y, epoch=100)
        model.save('/tmp/model.h5')
    print('#', time.time() - stt)
