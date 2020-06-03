from collections import namedtuple
from datetime import datetime
from typing import Dict, Union

from .utils import parse_datetime, NamedTupleMixin, utc_now_aware


class Account(NamedTupleMixin,
              namedtuple('Account', ['name', 'equity', 'profit_loss', 'used_margin', 'positions', 'time'])):
    __slots__ = ()

    @classmethod
    def _get_defaults(cls):
        return {
            'equity': (0, float),
            'profit_loss': (0, float),
            'used_margin': (0, float),
            'positions': ({}, dict),
            'time': (utc_now_aware, parse_datetime),
        }

    def __init__(self, name: str,
                 equity: Union[float, str] = None,
                 profit_loss: Union[float, str] = None,
                 used_margin: Union[float, str] = None,
                 positions: Dict[str, int] = None,
                 time: Union[datetime, str] = None):
        if False:
            # for type hint and suppress warning in PyCharm
            super().__init__('', [])
            self.name = name
            self.equity = float(equity)
            self.profit_loss = float(profit_loss)
            self.used_margin = float(used_margin)
            self.positions = dict(positions)
            self.time = parse_datetime(time)

    @property
    def balance(self) -> float:
        return self.equity - self.profit_loss

    @property
    def available_margin(self) -> float:
        return self.equity - self.used_margin
