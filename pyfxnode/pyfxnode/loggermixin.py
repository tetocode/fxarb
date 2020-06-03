import logging


class LoggerMixin:
    def __init__(self, *args, logger: logging.Logger = None, **kwargs):
        getattr(super(), '__init__')(*args, **kwargs)
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    def debug(self, msg: str, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        self.logger.critical(msg, *args, **kwargs)

    def fatal(self, msg: str, *args, **kwargs):
        self.logger.fatal(msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs):
        self.logger.exception(msg, *args, **kwargs)
