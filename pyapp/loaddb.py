import sqlite3
import sys
from datetime import datetime

from docopt import docopt

import mysql
import timeutil


def main():
    args = docopt("""
    Usage:
      {f} [options] FILES...

    Options:
      --database DB  mysql database[default: ratedb]
      --limit LIMIT  [default: 1000]
    """.format(f=sys.argv[0]))
    files = args['FILES']
    db = args['--database']
    limit = int(args['--limit'])

    conn = mysql.connect(user='root', passwd='root')  # , cursorclass=mysql.cursors.SSCursor)

    for f_i, f_name in enumerate(files):
        sqlite_conn = sqlite3.connect(f_name)
        r = sqlite_conn.execute('SELECT name FROM sqlite_master WHERE type="table"')
        tables = list(sorted(set([x[0].lower() for x in r.fetchall()])))

        for t_i, table in enumerate(sorted(tables)):

            with conn as c:
                c.execute('CREATE DATABASE IF NOT EXISTS {}'.format(db))
                c.execute('USE {}'.format(db))
                c.execute("""CREATE TABLE IF NOT EXISTS {}(
                    time DATETIME(6) PRIMARY KEY,
                    bid FLOAT,
                    ask FLOAT
                    )""".format(table))

            def gen_data(table):
                dt_from = datetime.min
                while True:
                    r = sqlite_conn.execute(
                        'SELECT time, bid, ask FROM {} WHERE ? < time ORDER BY time ASC LIMIT {}'.format(table, limit),
                        (dt_from,))
                    results = r.fetchall()
                    if not results:
                        break
                    yield results
                    dt_from = results[-1][0]

            with conn as c:
                c.execute('SET sql_log_bin=OFF')
                i = 0
                for results in gen_data(table):
                    N = len(results)

                    def dt_convert(x):
                        dt = timeutil.to_datetime(x[0])
                        if not dt.tzinfo:
                            dt = dt.replace(tzinfo=timeutil.TOKYO)
                        return (dt,) + x[1:]

                    flatten_results = [flatten for inner in results for flatten in dt_convert(inner)]
                    c.execute('INSERT IGNORE INTO {} VALUES {}'.format(table, ','.join(['(%s,%s,%s)'] * N)),
                              flatten_results)
                    i += N
                    print('# {}/{} {}/{} #{}'.format(f_i + 1, len(files), t_i + 1, len(tables), i), f_name, table,
                          flatten_results[-3:])
                    conn.commit()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
