from collections import namedtuple
from datetime import datetime
from typing import Union, Tuple

import pytz

from .utils import parse_datetime, NamedTupleMixin


class Spread(NamedTupleMixin,
             namedtuple('Spread', ['pair', 'instrument', 'bid', 'ask', 'sp', 'time'])):
    __slots__ = ()

    @classmethod
    def _get_defaults(cls):
        return {
            'pair': (None, tuple),
            'bid': (None, float),
            'ask': (None, float),
            'time': (pytz.utc.localize(datetime.utcnow()), parse_datetime),
        }

    def __init__(self, pair: Tuple[str, str], instrument: str,
                 bid: Union[float, str], ask: Union[float, str],
                 sp: Union[float, str] = None,
                 time: Union[datetime, str] = None):
        if False:
            # for type hint and suppress warning in PyCharm
            super().__init__('', [])
            self.pair = pair
            self.instrument = instrument
            self.bid = float(bid)
            self.ask = float(ask)
            self.sp = float(sp)
            self.time = parse_datetime(time)

    def __new__(cls, *args, **kwargs):
        fields = getattr(cls, '_fields')
        new_kwargs = dict(tuple(zip(fields, args)))
        new_kwargs.update(**kwargs)

        if 'bid' in new_kwargs and 'ask' in new_kwargs and 'sp' not in new_kwargs:
            new_kwargs['sp'] = float(new_kwargs['ask']) - float(new_kwargs['bid'])

        return super().__new__(cls, **new_kwargs)
