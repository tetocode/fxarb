from datetime import datetime
from typing import Dict

import pytz

from .datahandler import DataHandler


class Account:
    def __init__(self, name: str, equity: float = None, profit_loss: float = None, used_margin: float = None,
                 positions: Dict[str, int] = None, online: bool = None):
        self.name = name
        self.equity = equity or .0
        self.profit_loss = profit_loss or .0
        self.used_margin = used_margin or .0
        self.positions = positions or {}
        self.online = False if online is None else online
        self.time = datetime.utcnow().replace(tzinfo=pytz.utc)

    @property
    def balance(self) -> float:
        return self.equity - self.profit_loss

    @property
    def available_margin(self) -> float:
        return self.equity - self.used_margin

    def update(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self) -> dict:
        return dict(name=self.name, equity=self.equity, profit_loss=self.profit_loss,
                    used_margin=self.used_margin, online=self.online,
                    positions=self.positions, time=self.time)

    def __eq__(self, other: 'Account'):
        return (self.name == other.name
                and self.equity == other.equity
                and self.profit_loss == other.profit_loss
                and self.used_margin == other.used_margin
                and self.online == other.online
                and self.positions == other.positions
                and self.time == other.time)


class AccountHandler(DataHandler):
    def __init__(self):
        self.accounts = {}  # type: Dict[str, dict]:

    def handle(self, **data):
        for k, v in data.items():
            if k == 'accounts':
                self.accounts.update({account.name: account for account in v})
