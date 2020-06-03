import copy
from collections import deque
from datetime import datetime

import gevent
import pytz

from pyfx.pricehandler import PriceHandler, Price


def test_price_handler():
    h = PriceHandler()
    assert h.prices == {}
    now = datetime.utcnow().replace(tzinfo=pytz.utc)
    prices = [Price('xxx', 'USD/JPY', now, 0.01, 0.02)]
    h.handle(prices=copy.deepcopy(prices))
    assert h.prices == {'xxx': {'USD/JPY': deque(prices)}}
    prices2 = [
        Price('xxx', 'USD/JPY', now, 0.01, 0.03),
        Price('xxx', 'EUR/JPY', now, 0.01, 0.02),
        Price('yyy', 'EUR/JPY', now, 0.01, 0.02),
    ]
    h.handle(prices=copy.deepcopy(prices2))
    expected = {
        'xxx': {
            'USD/JPY': deque(prices + [prices2[0]]),
            'EUR/JPY': deque([prices2[1]]),
        },
        'yyy': {
            'EUR/JPY': deque([prices2[2]]),
        }
    }
