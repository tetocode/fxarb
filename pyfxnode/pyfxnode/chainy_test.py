import random
import time

import numpy as np
import pytest


@pytest.mark.skip
def test_chainy_classifier():
    from pyfxnode.chainy import Chainy
    stt = time.time()
    train_data = []
    for i in range(100):
        a, b = random.randint(0, 9), random.randint(0, 9)
        c = (a + b)
        train_data.append((np.array([a, b], dtype=np.float32), np.int32(c % 2)))
    test_data = []
    for i in range(100):
        a, b = random.randint(0, 9), random.randint(0, 9)
        c = (a + b)
        test_data.append((np.array([a, b], dtype=np.float32), np.int32(c % 2)))

    n_units = [
        2, 100, 100, 2,
    ]
    chain = Chainy(*n_units, use_cache=False)
    chain.train_classifier(train_data=train_data, test_data=test_data, batch_size=100, epoch=1000)
    print('#', time.time() - stt)
