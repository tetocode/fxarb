from collections import defaultdict
from collections import deque
from datetime import datetime
from typing import Union

from dateutil import parser

from .datahandler import DataHandler


class Price:
    def __init__(self, name: str, instrument: str, time: Union[datetime, str], bid: float, ask: float):
        self.name = name
        self.instrument = instrument
        self.time = time if isinstance(time, datetime) else parser.parse(time)
        self.bid = bid
        self.ask = ask

    def to_dict(self) -> dict:
        time = self.time  # self.time.isoformat('T')
        return dict(name=self.name, instrument=self.instrument, time=time, bid=self.bid, ask=self.ask)

    def update(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __eq__(self, other: 'Price'):
        return self.to_dict() == other.to_dict()

    def __ne__(self, other):
        return not self.__eq__(other)


class PriceHandler(DataHandler):
    PRICE_MAX_RECORD = 200

    def __init__(self):
        self.prices = defaultdict(lambda: defaultdict(lambda: deque(maxlen=self.PRICE_MAX_RECORD)))

    def handle(self, **data):
        for price in data.get('prices', ()):
            self.prices[price.name][price.instrument].append(price)
