# -*- coding:utf-8 -*-
from __future__ import division, print_function, absolute_import, unicode_literals

from datetime import datetime

import MySQLdb.cursors
from MySQLdb import converters
from MySQLdb.connections import Connection as _Connection

import timeutil


def from_datetime(dt, *_):
    return (dt.astimezone(timeutil.UTC) if dt.tzinfo else dt).strftime("""'%Y-%m-%d %H:%M:%S.%f'""")


converters.conversions[datetime] = from_datetime
converters.conversions[MySQLdb.FIELD_TYPE.DATETIME] = timeutil.to_datetime


def connect(user='root', passwd='root', *args, **kwargs):
    return MySQLdb.connect(user=user, passwd=passwd, *args, **kwargs)


cursors = MySQLdb.cursors


class Connection(_Connection):
    pass
