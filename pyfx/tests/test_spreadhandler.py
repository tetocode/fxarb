import copy
from collections import deque
from datetime import datetime, timedelta

import gevent
import pytest
import pytz

from pyfx.pricehandler import PriceHandler, Price
from pyfx.spreadhandler import SpreadHandler, Spread



def test_spread_handler():
    h = SpreadHandler(PriceHandler())
    assert h.prices == {}
    now = datetime.utcnow().replace(tzinfo=pytz.utc)
    now2 = now + timedelta(minutes=1, seconds=1)
    prices = [Price('xxx', 'USD/JPY', now, 0.01, 0.02)]
    h.handle(prices=copy.deepcopy(prices))
    assert h.prices == {'xxx': {'USD/JPY': deque(prices)}}
    expected = {
        ('xxx', 'xxx'): {
            'USD/JPY': deque([
                Spread(('xxx', 'xxx'), 'USD/JPY', now, 0.01, 0.02)
            ])
        }
    }
    assert h.spreads == expected

    prices = [
        Price('xxx', 'USD/JPY', now2, 0.01, 0.03),
        Price('xxx', 'EUR/JPY', now, 0.03, 0.05),
        Price('yyy', 'EUR/JPY', now2, 0.06, 0.08),
    ]
    h.handle(prices=copy.deepcopy(prices))
    expected = {
        ('xxx', 'xxx'): {
            'USD/JPY': deque([
                Spread(('xxx', 'xxx'), 'USD/JPY', now, 0.01, 0.02),
                Spread(('xxx', 'xxx'), 'USD/JPY', now2, 0.01, 0.03)
            ]),
            'EUR/JPY': deque([
                Spread(('xxx', 'xxx'), 'EUR/JPY', now, 0.03, 0.05),
            ])
        },
        ('xxx', 'yyy'): {
            'EUR/JPY': deque([
                Spread(('xxx', 'yyy'), 'EUR/JPY', now2, 0.03, 0.08)
            ])
        },
        ('yyy', 'xxx'): {
            'EUR/JPY': deque([
                Spread(('yyy', 'xxx'), 'EUR/JPY', now2, 0.06, 0.05)
            ])
        },
        ('yyy', 'yyy'): {
            'EUR/JPY': deque([
                Spread(('yyy', 'yyy'), 'EUR/JPY', now2, 0.06, 0.08)
            ])
        }
    }
    assert h.spreads == expected
