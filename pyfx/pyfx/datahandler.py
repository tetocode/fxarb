from abc import ABC, abstractmethod


class DataHandler(ABC):
    @abstractmethod
    def handle(self, **data):
        pass
