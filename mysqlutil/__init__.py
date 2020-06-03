from datetime import datetime as _datetime

import timeutil

try:

    import pymysql as _mysql
    import pymysql.connections as _mysql_connections
    import pymysql.cursors as _mysql_cursors
    import pymysql.converters as _mysql_converters

except ImportError:
    import MySQLdb as _mysql
    import MySQLdb.connections as _mysql_connections
    import MySQLdb.cursors as _mysql_cursors
    import MySQLdb.converters as _mysql_converters


def from_datetime(dt, *_):
    return (dt.astimezone(timeutil.UTC) if dt.tzinfo else dt).strftime("""'%Y-%m-%d %H:%M:%S.%f'""")


_mysql_converters.conversions[_datetime] = from_datetime
_mysql_converters.conversions[_mysql.FIELD_TYPE.DATETIME] = timeutil.to_datetime


def connect(*, user: str = 'root', passwd: str = 'root', host: str = 'localhost', db: str = '',
            **kwargs) -> _mysql_connections.Connection:
    return _mysql.connect(user=user, passwd=passwd, host=host, db=db, **kwargs)


cursors = _mysql_cursors
Warning = _mysql.Warning
