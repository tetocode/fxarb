from pyfxnode.spread import Spread


def test_spread():
    a = Spread(('A', 'B'), 'USD/JPY', 10, 20)

    assert a.pair == ('A', 'B')
    assert a.instrument == 'USD/JPY'
    assert a.bid == 10
    assert a.ask == 20
    assert a.sp == 10
    assert a.time

    a = a.replace(ask=30)
    assert a.bid == 10
    assert a.ask == 30

    j = a.to_json()
    assert a == a.from_json(j)
