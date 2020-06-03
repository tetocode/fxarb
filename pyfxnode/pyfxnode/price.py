from collections import namedtuple
from datetime import datetime
from typing import Union

from .utils import parse_datetime, NamedTupleMixin, utc_now_aware


class Price(NamedTupleMixin,
            namedtuple('Price', ['name', 'instrument', 'bid', 'ask', 'time'])):
    __slots__ = ()

    @classmethod
    def _get_defaults(cls):
        return {
            'bid': (None, float),
            'ask': (None, float),
            'time': (utc_now_aware, parse_datetime),
        }

    def __init__(self, name: str, instrument: str,
                 bid: Union[float, str], ask: Union[float, str],
                 time: Union[datetime, str] = None):
        if False:
            # for type hint and suppress warning in PyCharm
            super().__init__('', [])
            self.name = name
            self.instrument = instrument
            self.bid = float(bid)
            self.ask = float(ask)
            self.time = parse_datetime(time)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2
