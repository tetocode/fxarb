import itertools
import statistics
import sys
from datetime import timedelta, datetime

from docopt import docopt

import mysql
import timeutil


def main():
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --database DB  [default: ratedb]
      --instruments INSTRUMENTS  [default: eurjpy,gbpjpy]
      --services SERVICES  [default: ultra,ultra]
      --from FROM  [default: 2000-01-01]
      --to TO    [default: 2020-01-01]
      --len LEN  [default: 10]
      --sp SP    [default: 0.4]
    """.format(f=sys.argv[0]))
    db = args['--database']
    instruments = args['--instruments'].split(',')
    services = args['--services'].split(',')
    dt_from = timeutil.to_datetime(args['--from']).replace(tzinfo=timeutil.TOKYO)
    dt_to = timeutil.to_datetime(args['--to']).replace(tzinfo=timeutil.TOKYO)
    seq_len = int(args['--len'])
    sp_threshold = float(args['--sp'])

    def connect():
        return mysql.connect(db=db, cursorclass=mysql.cursors.SSDictCursor)

    def gen_data(dt_from: datetime, dt_to: datetime, instrument: str, a: str, b: str, sp_threshold: float):
        delta = timedelta(minutes=10)
        dt_from = dt_from.replace()
        dt_to = dt_to.replace()
        while dt_from < dt_to:
            print(dt_from)
            with connect() as c:
                c.execute('CREATE TEMPORARY TABLE a(time DATETIME(6) PRIMARY KEY, bid FLOAT, ask FLOAT) ENGINE=MEMORY')
                c.execute('CREATE TEMPORARY TABLE b(time DATETIME(6) PRIMARY KEY, bid FLOAT, ask FLOAT) ENGINE=MEMORY')
                q = ('INSERT INTO a SELECT time,bid,ask FROM rate' +
                    ' WHERE %s <= time AND time < %s AND instrument = %s AND service = %s')
                c.execute(q, (dt_from, dt_from + delta, instrument, a))
                q = ('INSERT INTO b SELECT time,bid,ask FROM rate' +
                    ' WHERE %s <= time AND time < %s AND instrument = %s AND service = %s')
                c.execute(q, (dt_from, dt_from + delta, instrument, b))
                q = ('SELECT a.time,a.bid,a.ask,b.bid,b.ask,(a.bid-b.ask)AS sp1,(b.bid-a.ask)AS sp2'+
                     ' FROM a INNER JOIN b ON a.time = b.time')
                c.execute(q, )#(sp_threshold, sp_threshold))
                for r in c.fetchall():
                    if r[0] < dt_to and (r[-2] >= sp_threshold or r[-1] >= sp_threshold):
                        yield r
            dt_from += delta

    tables = []
    with connect() as c:
        c.execute('SHOW TABLES')
        for r in c.fetchall():
            tables.append(list(r.values())[0])

    for instrument in sorted(instruments):
        if 'jpy' in instrument:
            multiply_rate = 100
        else:
            multiply_rate = 10000
        threshold = sp_threshold / multiply_rate

        for a, b in sorted(set(itertools.combinations(services, 2)), key=str):
            for r in gen_data(dt_from, dt_to, instrument, a, b, threshold):
                print(r)
            return
            continue
            ab_list = []
            ab_sp_list = []
            ba_list = []
            ba_sp_list = []
            results = [('#', a, b)]
            for r in r.fetchall():
                print(r)
                sp1 = float('{:.2f}'.format(r[5] * multiply_rate))
                sp2 = float('{:.2f}'.format(r[6] * multiply_rate))
                r = (timeutil.to_datetime(r[0]),) + r[1:5] + (sp1, sp2)
                if sp1 < 0:
                    if ab_list:
                        if r[0] - ab_list[-1][0] > timedelta(seconds=1):
                            ab_list = []
                            ab_sp_list = []
                    ab_list.append(r)
                    ab_sp_list.append(sp1)
                    if len(ab_list) >= seq_len:
                        median = float('{:.2f}'.format(statistics.median(ab_sp_list[-seq_len:])))
                        if results[-1][-2] != 'ab':
                            results.append(list(r[:5] + ('ab', median)))
                        elif results[-1][-2] == 'ab':
                            if median < results[-1][-1]:
                                results[-1][-1] = median
                else:
                    if ba_list:
                        if r[0] - ba_list[-1][0] > timedelta(seconds=1):
                            ba_list = []
                            ba_sp_list = []
                    ba_list.append(r)
                    ba_sp_list.append(sp2)
                    if len(ba_list) >= seq_len:
                        median = float('{:.2f}'.format(statistics.median(ba_sp_list[-seq_len:])))
                        if results[-1][-2] != 'ba':
                            results.append(list(r[:5] + ('ba', median)))
                        elif results[-1][-2] == 'ba':
                            if median < results[-1][-1]:
                                results[-1][-1] = median

            profit = 0
            rows = []
            for r in results[1:]:
                rows.append(', '.join(map(str, [r[0].strftime('%Y%m%d %H:%M:%S')] + r[1:])))
                profit += r[-1]
            all_results.append([a + b, profit, rows])
    return
    for r in sorted(all_results, key=lambda x: x[1]):
        print('#', r[0])
        for _ in r[2]:
            print(_)
        print(r[1])
        print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
