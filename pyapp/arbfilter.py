import csv
import logging
import sys
from collections import defaultdict
from datetime import timedelta
from pprint import pprint

from docopt import docopt

import timeutil


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --log-file FILE  [default: ./pyapp.csv]
      --disabled SERVICES  [default: pfx]
      --from DATETIME
      --to DATETIME
    """.format(f=sys.argv[0]))
    log_file = args['--log-file']
    disabled = set(args['--disabled'].split(','))
    from_dt = timeutil.to_datetime(args['--from']) if args['--from'] else (timeutil.jst_now() - timedelta(days=1))
    to_dt = timeutil.to_datetime(args['--to']) if args['--to'] else timeutil.jst_now()

    signals = []  # type: List[dict]
    # time,bidder,asker,bid,ask,sp
    with open(log_file, 'r') as f:
        labels = ('time', 'instrument', 'bidder', 'asker', 'bid', 'ask', 'sp')
        dt = timeutil.to_datetime('20161022T050000+0900')
        for i, row in enumerate(csv.reader(f), 1):
            try:
                d = dict(zip(labels, row))
                d['time'] = timeutil.to_datetime(d['time'])
                if d['time'] >= dt:
                    continue
                print(','.join(map(str, [d[k] for k in labels])))
            except Exception as e:
                logging.exception('#{}\n{}'.format(i, str(e)))
                raise

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
