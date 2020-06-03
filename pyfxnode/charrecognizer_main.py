import logging
import os
import re
import sys
from time import sleep

from docopt import docopt

from pyfxnode.charrecognizer import CharRecognizer
from pyfxnode.utils import jst_now_aware
from pyfxnode.window import Window


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f}
      {f} [options] capture TITLE DIR
      {f} [options] make_data NAME DIR
      {f} [options] train DIR
      
    Options:
      --epoch EPOCH  [default: 10]
      --capture-interval SEC  [default: 5]
    """.format(f=sys.argv[0]))

    name = args['NAME']
    title = args['TITLE']
    dir_name = args['DIR']
    os.makedirs(dir_name, exist_ok=True)
    os.chdir(dir_name)
    if args['capture']:
        windows = tuple(filter(lambda x: re.search(title, x.get_title()), Window.iter_window()))
        while True:
            for window in windows:
                window.get_screen_shot().save('{}.png'.format(jst_now_aware().strftime('%Y%m%dT%H%M%S')))
                sleep(float(args['--capture-interval']))
    if args['make_data']:
        recognizer = CharRecognizer('.')
        recognizer.make_train_data(name)
    if args['train']:
        epoch = int(args['--epoch'])
        recognizer = CharRecognizer('.')
        recognizer.train(epoch)
        recognizer.save()

    for w in Window.iter_window():
        print(w.get_title())

    return


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
