from .accounthandler import AccountHandler
from .pricehandler import PriceHandler
from .spreadhandler import SpreadHandler


class HandlerProxy:
    def __init__(self, *args, account: bool = False, price: bool = False, spread: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._account_handler = AccountHandler() if account else None
        self._price_handler = PriceHandler() if price or spread else None
        self._spread_handler = SpreadHandler(self._price_handler) if spread else None

    @property
    def accounts(self):
        assert self._account_handler
        return self._account_handler.accounts

    @property
    def prices(self):
        assert self._price_handler
        return self._price_handler.prices

    @property
    def spreads(self):
        assert self._spread_handler
        return self._spread_handler.spreads

    def handle(self, **data):
        if self._account_handler:
            self._account_handler.handle(**data)

        if self._spread_handler:
            self._spread_handler.handle(**data)
        elif self._price_handler:
            self._price_handler.handle(**data)
