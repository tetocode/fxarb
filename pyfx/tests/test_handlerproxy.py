import copy
from collections import deque
from datetime import datetime

import gevent
import pytest
import pytz

from pyfx.accounthandler import Account
from pyfx.handlerproxy import HandlerProxy
from pyfx.pricehandler import Price
from pyfx.spreadhandler import Spread


def test_handler_proxy():
    h = HandlerProxy(account=False, price=False, spread=False)
    with pytest.raises(AssertionError):
        assert h.accounts == {}
    with pytest.raises(AssertionError):
        assert h.prices == {}
    with pytest.raises(AssertionError):
        assert h.spreads == {}
    h = HandlerProxy(account=True, price=True)

    now = datetime.utcnow().replace(tzinfo=pytz.utc)
    gevent.sleep(0.01)

    accounts = [Account('xxx', 1000, 10, 100, {'USD/JPY': 100, 'AUD/JPY': 200})]
    prices = [Price('xxx', 'USD/JPY', now, 0.01, 0.02)]
    h.handle(accounts=copy.deepcopy(accounts), prices=copy.deepcopy(prices))
    assert h.accounts == {'xxx': accounts[0]}
    assert h.prices == {'xxx': {'USD/JPY': deque(prices)}}
    with pytest.raises(AssertionError):
        assert h.spreads == {}

    h = HandlerProxy(account=True, price=True, spread=True)
    h.handle(accounts=copy.deepcopy(accounts), prices=copy.deepcopy(prices))
    expected = {
        ('xxx', 'xxx'): {
            'USD/JPY': deque([
                Spread(('xxx', 'xxx'), 'USD/JPY', now, 0.01, 0.02)
            ])
        }
    }
    assert h.accounts == {'xxx': accounts[0]}
    assert h.prices == {'xxx': {'USD/JPY': deque(prices)}}
    assert h.spreads == expected
