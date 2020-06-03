import timeutil

from . import connect

def test_mysqlutil():
    conn = connect()
    with conn as c:
        try:
            c.execute('CREATE DATABASE testdb')
            c.execute('USE testdb')
            c.execute('CREATE TABLE t(time DATETIME(6) PRIMARY KEY)')
            dt = timeutil.jst_now()
            c.execute('INSERT INTO t SET time=%s', dt)
            c.execute('SELECT * FROM t')
            print(c.fetchall())
            print('#', dt)
        finally:
            c.execute('DROP DATABASE testdb')
