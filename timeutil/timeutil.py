from datetime import datetime, date
from typing import Union

from dateutil import parser
from dateutil.relativedelta import relativedelta

import pytz

NY = pytz.timezone('America/New_York')
LONDON = pytz.timezone('Europe/London')
TOKYO = pytz.timezone('Asia/Tokyo')
UTC = pytz.timezone('UTC')


def to_datetime(obj: Union[str, datetime, date]) -> datetime:
    if isinstance(obj, str):
        dt = parser.parse(obj)
    elif isinstance(obj, datetime):
        dt = obj
    elif isinstance(obj, date):
        dt = datetime(obj.year, obj.month, obj.day)
    else:
        raise TypeError('not supported type type:{0} {1}'.format(type(obj), obj))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def utc_now() -> datetime:
    return UTC.localize(datetime.utcnow())


def jst_now() -> datetime:
    return utc_now().astimezone(TOKYO)


class MarketTime:
    def __init__(self, dt):
        dt = to_datetime(dt)
        self.time = dt
        ny_close = dt.astimezone(NY).replace(hour=17, minute=0, microsecond=0)
        if ny_close < dt:
            naive_ny_close = ny_close.replace(tzinfo=None) + relativedelta(days=1)
        else:
            naive_ny_close = ny_close.replace(tzinfo=None)
        self.fx_open = (NY.localize(naive_ny_close - relativedelta(days=1))
                        ).astimezone(UTC)
        self.fx_close = NY.localize(naive_ny_close).astimezone(UTC)
        ymd = naive_ny_close.replace(hour=0, minute=0)
        self.tokyo_stock_open = TOKYO.localize(ymd.replace(hour=9))
        self.tokyo_fix = TOKYO.localize(ymd.replace(hour=9, minute=55))
        self.tokyo_stock_close = TOKYO.localize(ymd.replace(hour=15))
        self.london_stock_open = LONDON.localize(ymd.replace(hour=8))
        self.london_fix = LONDON.localize(ymd.replace(hour=16))
        self.london_stock_close = LONDON.localize(ymd.replace(hour=16, minute=30))
        self.ny_stock_open = NY.localize(ymd.replace(hour=9, minute=30))
        self.ny_cutoff = NY.localize(ymd.replace(hour=10))
        self.ny_stock_close = NY.localize(ymd.replace(hour=16))

    def __str__(self):
        return '{0}'.format(self.__dict__)
