import logging


class Domain:
    def __init__(self, command_func, name: str = None):
        self._name = name or self.__class__.__name__
        self._command_func = command_func
        self.logger = logging.getLogger(name)

    def __getattr__(self, item):
        return lambda *, callback=None, **params: self.command(
            method='{}.{}'.format(self._name, item), callback=callback, **params)

    def command(self, method: str, *, callback=None, **params):
        return self._command_func(method=method, callback=callback, **params)

    def on_event(self, event: dict):
        pass
