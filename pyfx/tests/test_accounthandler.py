import copy

from pyfx.accounthandler import Account, AccountHandler


def test_account_handler():
    h = AccountHandler()
    assert h.accounts == {}
    accounts = [Account('xxx', 1000, 10, 100, {'USD/JPY': 100, 'AUD/JPY': 200})]
    h.handle(accounts=copy.deepcopy(accounts))
    assert h.accounts == {'xxx': accounts[0]}
    accounts = [
        Account('xxx', 0, 10, 100, {}),
        Account('yyy', 100, 10, 100, {'USD/JPY': 100, 'AUD/JPY': 200}),
    ]
    h.handle(accounts=copy.deepcopy(accounts))
    h.handle(accounts=accounts)
