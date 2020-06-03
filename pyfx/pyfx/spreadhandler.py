from collections import defaultdict
from collections import deque
from contextlib import suppress
from datetime import datetime
from typing import Dict, Tuple, Optional

from .pricehandler import PriceHandler


class Spread:
    def __init__(self, pair: Tuple[str, str], instrument: str, time: datetime, bid: float, ask: float):
        self.pair = pair
        self.instrument = instrument
        self.time = time
        self.bid = bid
        self.ask = ask

    @property
    def sp(self) -> float:
        return self.bid - self.ask

    def update(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __eq__(self, other: 'Spread'):
        return (self.pair == other.pair
                and self.instrument == other.instrument
                and self.time == other.time
                and self.bid == other.bid
                and self.ask == other.ask)


class SpreadHandler:
    SPREAD_MAX_RECORD = 1000

    def __init__(self, price_handler: PriceHandler):
        self.price_handler = price_handler
        self.spreads = defaultdict(lambda: defaultdict(lambda: deque(maxlen=self.SPREAD_MAX_RECORD)))

    @property
    def prices(self) -> Dict[str, Dict[str, dict]]:
        return self.price_handler.prices

    def get_spread(self, pair: Tuple[str, str], instrument: str) -> Optional[Spread]:
        try:
            return self.spreads[pair][instrument][-1]
        except (KeyError, IndexError):
            pass
        return None

    def add_spread(self, spread: Spread):
        self.spreads[spread.pair][spread.instrument].append(spread)

    def handle(self, **data):
        self.price_handler.handle(**data)
        self.update_spreads()

    def update_spreads(self):
        for a, a_instrument_prices in self.price_handler.prices.items():
            for b, b_instrument_prices in self.price_handler.prices.items():
                for instrument, a_prices in a_instrument_prices.items():
                    with suppress(KeyError, IndexError):
                        pair = (a, b)
                        a_price = a_prices[-1]
                        b_prices = b_instrument_prices[instrument]
                        b_price = b_prices[-1]
                        new_sp_time = max(a_price.time, b_price.time)
                        sp = self.get_spread(pair, instrument)
                        if not sp or sp.time < new_sp_time:
                            new_sp = Spread(pair, instrument, new_sp_time, a_price.bid, b_price.ask)
                            self.add_spread(new_sp)
