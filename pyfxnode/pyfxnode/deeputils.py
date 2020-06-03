import logging
import os

import keras
import numpy as np
from keras.layers.core import Dense
from keras.models import Sequential


class Classifier:
    def __init__(self, *n_units, sequential: Sequential = None, use_cache: bool = True, loss_func=None, optimizer=None):
        self._use_cache = use_cache
        self._cache = {}
        if sequential:
            self._sequential = sequential
            return
        self._sequential = Sequential()
        for i in range(len(n_units) - 2):
            n1, n2 = n_units[i:i + 2]
            self._sequential.add(Dense(units=n2, input_dim=n1, activation='relu'))
        self._sequential.add(Dense(units=n_units[-1], activation='softmax'))
        self._sequential.compile(loss=loss_func or 'categorical_crossentropy',
                                 optimizer=optimizer or 'adam',
                                 metrics=['accuracy'])

    def __getattr__(self, item):
        return getattr(self._sequential, item)

    def save(self, file_path: str):
        self._sequential.save(file_path)
        logging.info('model saved to {}'.format(os.path.abspath(file_path)))

    @classmethod
    def load(cls, file_path: str) -> 'Classifier':
        try:
            model = Classifier(sequential=keras.models.load_model(file_path))
            logging.info('model loaded from {}'.format(os.path.abspath(file_path)))
            return model
        except OSError:
            raise FileNotFoundError

    def classify(self, x: np.ndarray):
        return self._sequential.predict_classes(x)

    def classify_one(self, x: np.ndarray):
        return self._sequential.predict_classes(np.array([x]))[0]

    def train(self, train_x, train_y, test_x, test_y, batch_size: int = 128, epoch: int = 10):
        self._sequential.fit(train_x, train_y, batch_size=batch_size, epochs=epoch, verbose=1,
                             validation_data=(test_x, test_y))
        return self._sequential.evaluate(test_x, test_y, verbose=0)
