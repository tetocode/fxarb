import hashlib
import logging

if False:
    import chainer
    import numpy as np
    from chainer import training
    from chainer.training import extensions

    from .utils import jst_now_aware


    class Chainy(chainer.ChainList):
        def __init__(self, *n_units, use_cache: bool = True):
            links = []
            for i in range(len(n_units) - 1):
                n1, n2 = n_units[i:i + 2]
                links.append(chainer.links.Linear(n1, n2))
            super().__init__(*links)
            self._use_cache = use_cache
            self._classify_cache = {}
            self._calculate_cache = {}

        def __call__(self, x):
            for i in range(len(self) - 1):
                x = chainer.functions.relu(self[i](x))
            return self[-1](x)

        def classify(self, arr: np.ndarray, *, use_cache: bool = None) -> np.int32:
            use_cache = use_cache if use_cache is not None else self._use_cache
            if not use_cache:
                return np.argmax(self.calculate(arr, use_cache=use_cache).data)

            md5 = hashlib.md5(arr).hexdigest()
            value = self._classify_cache.get(md5)
            if value is None:
                value = np.argmax(self.calculate(arr, use_cache=use_cache, md5=md5).data)
                self._classify_cache[md5] = value
            return value

        def calculate(self, arr: np.ndarray, *, use_cache: bool = None, md5: str = None):
            use_cache = use_cache if use_cache is not None else self._use_cache
            if not use_cache:
                return self(arr)

            md5 = md5 or hashlib.md5(arr).hexdigest()
            value = self._calculate_cache.get(md5)
            if value is None:
                value = self(arr)
                self._calculate_cache[md5] = value
            return value

        def save(self, f_name: str):

            def save(model, f):
                try:
                    chainer.serializers.save_npz(f, model)
                    logging.info('model saved to {}'.format(f))
                except FileNotFoundError:
                    logging.exception('!!!model not saved to {}'.format(f))

            save(self, f_name)
            timestamp = jst_now_aware().strftime('%Y%m%dT%H%M%S')
            save(self, f_name + '.' + timestamp)

        def load(self, f_name: str):

            def load(model, f):
                try:
                    chainer.serializers.load_npz(f, model)
                    logging.info('model loaded from {}'.format(f))
                except FileNotFoundError:
                    logging.exception('!!!model not loaded from {}'.format(f))

            load(self, f_name)

        def _train(self, model, train_data, test_data, batch_size: int = 100, epoch: int = 10):
            assert isinstance(self, (chainer.Chain, chainer.ChainList))
            gpu = -1
            out = 'result'
            resume = ''
            # Set up a neural network to train
            # Classifier reports softmax cross entropy loss and accuracy at every
            # iteration, which will be used by the PrintReport extension below.
            if gpu >= 0:
                chainer.cuda.get_device_from_id(gpu).use()  # Make a specified GPU current
                model.to_gpu()  # Copy the model to the GPU

            # Setup an optimizer
            optimizer = chainer.optimizers.Adam()
            optimizer.setup(model)

            train_iter = chainer.iterators.SerialIterator(train_data, batch_size)
            test_iter = chainer.iterators.SerialIterator(test_data, batch_size, repeat=False, shuffle=False)
            # Set up a trainer
            updater = training.StandardUpdater(train_iter, optimizer, device=gpu)
            trainer = training.Trainer(updater, (epoch, 'epoch'), out=out)

            # Evaluate the model with the test dataset for each epoch
            trainer.extend(extensions.Evaluator(test_iter, model, device=gpu))

            # Dump a computational graph from 'loss' variable at the first iteration
            # The "main" refers to the target link of the "main" optimizer.
            # trainer.extend(extensions.dump_graph('main/loss'))

            # Take a snapshot at each epoch
            trainer.extend(extensions.snapshot(), trigger=(epoch, 'epoch'))

            # Write a log of evaluation statistics for each epoch
            trainer.extend(extensions.LogReport())

            # Print selected entries of the log to stdout
            # Here "main" refers to the target link of the "main" optimizer again, and
            # "validation" refers to the default name of the Evaluator extension.
            # Entries other than 'epoch' are reported by the Classifier link, called by
            # either the updater or the evaluator.
            trainer.extend(extensions.PrintReport(
                ['epoch', 'main/loss', 'validation/main/loss',
                 'main/accuracy', 'validation/main/accuracy']))

            # Print a progress bar to stdout
            trainer.extend(extensions.ProgressBar())

            if resume:
                # Resume from a snapshot
                chainer.serializers.load_npz(resume, trainer)

            # Run the training
            trainer.run()

        def train_classifier(self, train_data, test_data, batch_size: int = 100, epoch: int = 20):
            return self._train(chainer.links.Classifier(self), train_data, test_data, batch_size, epoch)

        def train_calculator(self, train_data, test_data, batch_size: int = 100, epoch: int = 20):
            model = chainer.links.Classifier(self, lossfun=chainer.functions.mean_squared_error)
            model.compute_accuracy = False
            return self._train(model, train_data, test_data, batch_size, epoch)
