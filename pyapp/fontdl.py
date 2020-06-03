import glob
import random
import sys

import chainer
import chainer.functions as F
import chainer.links as L
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from docopt import docopt

from dlearn import train_model


# Network definition
class MLP(chainer.Chain):
    def __init__(self, n_in, n_units, n_out):
        super(MLP, self).__init__(
            # the size of the inputs to each layer will be inferred
            l1=L.Linear(n_in, n_units),  # n_in -> n_units
            l2=L.Linear(n_units, n_units),  # n_units -> n_units
            l3=L.Linear(n_units, n_out),  # n_units -> n_out
        )

    def __call__(self, x):
        h1 = F.relu(self.l1(x))
        h2 = F.relu(self.l2(h1))
        return self.l3(h2)


class DataGenerator:
    def __init__(self, font_files, font_min, font_max, candidates='0123456789', number=10000,
                 displacement=1, noise=False):
        width = height = font_max
        self._size = (width, height)
        self._candidates = candidates
        self._displacement = displacement
        fonts = []
        for font_size in range(font_min, font_max + 1):
            fonts.extend([ImageFont.truetype(f, int(font_size)) for f in font_files])
        self._number = number

        def gen():
            bg, fg = 0, 255
            while True:
                bg, fg = fg, bg
                candidates = self._candidates
                font = fonts[random.randint(0, len(fonts) - 1)]
                x, y = random.randint(0, displacement * 2) - displacement, random.randint(0,
                                                                                          displacement * 2) - displacement
                for c in random.sample(candidates, len(candidates)):
                    i = candidates.index(c)
                    img = Image.new('L', (width, height), bg)
                    d = ImageDraw.Draw(img)
                    d.text((x, y), c, font=font, fill=fg)
                    if noise:
                        for _ in range(random.randint(0, 10)):
                            img.putpixel((random.randint(0, width - 1), random.randint(0, height - 1)),
                                         random.randint(0, 1) * 255)

                    yield (np.array(img, dtype=np.float32).flatten(), np.int32(i))

        self._gen = gen()

    def __iter__(self):
        return self._gen

    def get(self):
        return next(self._gen)

    def __len__(self):
        return self._number

    def __getitem__(self, item):
        assert isinstance(item, slice)
        start = item.start or 0
        stop = item.stop or len(self)
        step = item.step or 1

        x_list, y_list = [], []
        candidates = '0123456789'
        return [self.get() for _ in range(start, stop, step)]


def main():
    args = docopt("""
    Usage:
      {} [options]

    Options:
      --unit UNIT  [default: 100]
      --out-unit OUT_UNIT  [default: 10]
      --font FONT  [default: /usr/share/fonts/truetype/takao-gothic/TakaoExGothic.ttf]
      --batch-size BATCH_SIZE  [default: 100]
      --epoch EPOCH  [default: 20]
      --out OUT  [default: result]
      --resume RESUME
      --data-size DATA_SIZE  [default: 1000]
      --test DATA_SIZE  [default: 0]
    """.format(sys.argv[0]))

    unit = int(args['--unit'])
    out_unit = int(args['--out-unit'])
    batch_size = int(args['--batch-size'])
    epoch = int(args['--epoch'])
    out = args['--out']
    resume = args['--resume']
    data_size = int(args['--data-size'])
    test_size = int(args['--test'])

    fonts = list(glob.glob('C:\Windows\Fonts/meiryo.ttc'))
    test_fonts = list(glob.glob('C:\Windows\Fonts/meiryo.ttc'))

    font_min = 8
    font_max = 12
    # create dataset
    candidates = '0123456789.'#ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    print(candidates, len(candidates))
    out_unit = len(candidates)
    gen = DataGenerator(fonts, font_min, font_max, number=data_size,
                        candidates=candidates, displacement=1, noise=False)
    test_gen = DataGenerator(test_fonts, font_min, font_max, number=data_size,
                             candidates=candidates, displacement=1, noise=False)

    model = MLP(font_max ** 2, unit, out_unit)

    if test_size:
        chainer.serializers.load_npz('./model.npz', model)

        N = test_size
        hit = 0
        for x, y in [gen.get() for _ in range(N)]:
            v = model(np.array([x], dtype=np.float32))
            _y = np.argmax(v.data)
            print(y, _y, v.data)
            if y == _y:
                hit += 1
            img = Image.fromarray(np.int8(np.array([x], dtype=np.float32)).reshape((32, 32)))
            # img.show()
        print('HitRate: {}%'.format(hit / N * 100))

        return
    train_iter = chainer.iterators.SerialIterator(gen, batch_size, repeat=True, shuffle=False)
    test_iter = chainer.iterators.SerialIterator(test_gen, batch_size, repeat=False, shuffle=False)

    train_model(model, train_iter, test_iter, batch_size, epoch, -1, out, resume)
    chainer.serializers.save_npz('./model.npz', model)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
