import logging
import sys

import pyautogui
import time
from docopt import docopt


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options] X Y

    Options:
      --start-fast
      --end-fast
      --in-bounce
      --in-elastic
    """.format(f=sys.argv[0]))

    # >>> pyautogui.moveTo(100, 100, 2, pyautogui.easeInQuad)     # start slow, end fast
    # >>> pyautogui.moveTo(100, 100, 2, pyautogui.easeOutQuad)    # start fast, end slow
    # >>> pyautogui.moveTo(100, 100, 2, pyautogui.easeInOutQuad)  # start and end fast, slow in middle
    # >>> pyautogui.moveTo(100, 100, 2, pyautogui.easeInBounce)   # bounce at the end
    # >>> pyautogui.moveTo(100, 100, 2, pyautogui.easeInElastic)  # rubber band at the end
    print(pyautogui.position())
    if args['--start-fast']:
        pyautogui.moveTo(int(args['X']), int(args['Y']), 1, pyautogui.easeOutQuad)
    elif args['--end-fast']:
        pyautogui.moveTo(int(args['X']), int(args['Y']), 1, pyautogui.easeInQuad)
    elif args['--in-bounce']:
        pyautogui.moveTo(int(args['X']), int(args['Y']), 1, pyautogui.easeInBounce)
    elif args['--in-elastic']:
        pyautogui.moveTo(int(args['X']), int(args['Y']), 1, pyautogui.easeInElastic)
    else:
        pyautogui.moveTo(int(args['X']), int(args['Y']), 1)
    print(pyautogui.position())
    time.sleep(10)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
