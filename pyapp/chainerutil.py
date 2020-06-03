import chainer
import chainer.links as L
from chainer import training
from chainer.training import extensions


class TrainableMixin:

    def train_classifier(self, train_data, test_data, batch_size=100, epoch=10):
        assert isinstance(self, (chainer.Chain, chainer.ChainList))
        gpu = -1
        out = 'result'
        resume = ''
        # Set up a neural network to train
        # Classifier reports softmax cross entropy loss and accuracy at every
        # iteration, which will be used by the PrintReport extension below.
        model = L.Classifier(self)
        if gpu >= 0:
            chainer.cuda.get_device(gpu).use()  # Make a specified GPU current
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
        trainer.extend(extensions.dump_graph('main/loss'))

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
