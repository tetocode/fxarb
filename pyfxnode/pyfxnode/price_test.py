from pyfxnode.price import Price


def test_price():
    a = Price('acc', 'USD/JPY', 10, 20)

    assert a.name == 'acc'
    assert a.instrument == 'USD/JPY'
    assert a.bid == 10
    assert a.ask == 20
    assert a.time

    a = a.replace(ask=30)
    assert a.bid == 10
    assert a.ask == 30

    j = a.to_json()
    assert a == a.from_json(j)
