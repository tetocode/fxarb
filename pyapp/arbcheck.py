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
      --log-file FILE  [default: ./signal_log.txt]
      --disabled SERVICES  [default: pfx]
      --from DATETIME
      --to DATETIME
      --rank RANK  [default: 20]
    """.format(f=sys.argv[0]))
    log_file = args['--log-file']
    disabled = set(args['--disabled'].split(','))
    from_dt = timeutil.to_datetime(args['--from']) if args['--from'] else (timeutil.jst_now() - timedelta(days=1))
    to_dt = timeutil.to_datetime(args['--to']) if args['--to'] else timeutil.jst_now()
    rank = int(args['--rank'])

    signals = []  # type: List[dict]
    # time,bidder,asker,bid,ask,sp
    with open(log_file, 'r') as f:
        labels = ['time', 'instrument', 'bidder', 'asker', 'bid', 'ask', 'sp']
        for i, row in enumerate(csv.reader(f)):
            try:
                d = dict(zip(labels, row))
                d['time'] = timeutil.to_datetime(d['time'])
                d['bid'] = float(d['bid'])
                d['ask'] = float(d['ask'])
                d['sp'] = float(d['sp'])
                d['key'] = (d['instrument'], min(d['bidder'], d['asker']), max(d['bidder'], d['asker']))
                d['direction'] = (d['bidder'], d['asker'])
                if d['sp'] > 2:
                    continue
                if d['bidder'] in disabled or d['asker'] in disabled:
                    continue
                if not (from_dt <= d['time'] < to_dt):
                    continue
                signals.append(d)
            except Exception as e:
                logging.exception('#{} {}'.format(i + 1, str(e)))
                raise

    records = defaultdict(lambda: dict(direction=(), profit=0, n=0, history=[]))

    def pip_scale(instrument: str):
        if 'JPY' in instrument.upper():
            return 100
        return 10000

    for signal in signals:
        record = records[signal['key']]
        record['key'] = signal['key']
        if record['direction'] != signal['direction']:
            if record['profit'] > 0:
                record['profit'] += signal['sp'] * 2  # / (signal['bid'] * pip_scale(signal['instrument']) / 10000)
            else:
                record['profit'] += signal['sp']  # / (signal['bid'] * pip_scale(signal['instrument']) / 10000)
            record['direction'] = signal['direction']
            record['n'] += 1
            # record['history'].append(signal)

    # records.sort(key=lambda x: str(x['key']))
    l = list(records.values())
    l.sort(key=lambda x: -x['profit'])
    pprint(l[:rank])

    l = list(records.values())
    l.sort(key=lambda x: -x['n'])
    pprint(l[:rank])


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
