from pyfxnode.account import Account


def test_account():
    a = Account('acc')

    assert a.name == 'acc'
    assert a.equity == 0
    assert a.profit_loss == 0
    assert a.used_margin == 0
    assert a.positions == {}
    assert a.time

    a = a.replace(positions={'i': 10}, profit_loss=10)
    assert a.positions == {'i': 10}
    assert a.profit_loss == 10

    j = a.to_json()
    assert a == a.from_json(j)
