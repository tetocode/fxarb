import logging
from collections import defaultdict
from datetime import timedelta, datetime
from typing import Dict
from typing import Tuple

import gevent
import gsocketpool.pool
from gevent.event import Event
from gevent.lock import RLock
from gevent.server import StreamServer
from mprpc import RPCServer, RPCClient as _RPCClient, RPCPoolClient as _RPCPoolClient

import timeutil


class Client(_RPCClient):
    def __init__(self, server_address: Tuple[str, int], *args, name: str = None, **kwargs):
        super().__init__(*server_address, *args, **kwargs)
        self.name = name
        self.logger = logging.getLogger('{}.{}'.format(self.name, server_address))

    def __getattr__(self, item):
        return lambda *args: self.call(item, *args)


class PoolClient(_RPCPoolClient):
    def __init__(self, server_address: Tuple[str, int], *args, name: str = None, **kwargs):
        super().__init__(*server_address, *args, **kwargs)
        self.name = name
        self.logger = logging.getLogger('{}.{}'.format(self.name, server_address))

    def __getattr__(self, item):
        return lambda *args: self.call(item, *args)


class Node(RPCServer):
    def __init__(self, name: str, bind_address: Tuple[str, int], *, logger_name=None):
        super().__init__()
        self.name = name
        self.bind_address = bind_address
        self.bound_address = None
        self.logger = logging.getLogger(logger_name or '{}.{}'.format(self.__class__.__name__, name))
        self.logger.debug('__init__({}, {})'.format(name, bind_address))
        self._started = Event()
        self._stopped = Event()

    def run(self):
        while not self.stopped:
            gevent.sleep(0.1)

    @property
    def started(self):
        return self._started.is_set()

    @property
    def stopped(self):
        return self._stopped.is_set()

    def wait_started(self, timeout=None):
        return self._started.wait(timeout)

    def wait_stopped(self, timeout=None):
        return self._stopped.wait(timeout)

    def echo(self, s: str):
        return s

    def start(self):
        while not self.stopped:
            try:
                server = StreamServer(self.bind_address, self)
                server.start()
                self.bound_address = server.address
                self._started.set()
                self.logger.debug('server bound_address:{}'.format(self.bound_address))
                self.run()
            except KeyboardInterrupt:
                server.stop()
                self.stop()
                raise
            except Exception as e:
                self.logger.exception(str(e))
                server.stop()

    def stop(self):
        self._stopped.set()


class Master(Node):
    def __init__(self, name: str, bind_address: Tuple[str, int]):
        super().__init__(name, bind_address)
        self.registered = {}  # type: Dict[str, Tuple[str,int]]
        self.last_checked = defaultdict(lambda: datetime.min)
        self.lock = RLock()

    def run_loop(self):
        pass

    def run(self):
        while not self.stopped:
            gevent.sleep(0.01)
            now = timeutil.jst_now()
            with self.lock:
                for name in list(self.registered.keys()):
                    try:
                        last_checked = self.last_checked[name]
                        if now - last_checked >= timedelta(seconds=3.0):
                            try:
                                del self.registered[name]
                            except KeyError:
                                pass
                            self.logger.warn('timeouted {} unregistered'.format(name))
                            try:
                                del self.last_checked[name]
                            except KeyError:
                                pass
                    except KeyError:
                        pass
                try:
                    self.run_loop()
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    self.logger.exception(str(e))

    def register(self, name: str, client_address: Tuple[str, int]):
        with self.lock:
            try:
                address = self.registered[name]
                if address == client_address:
                    self.logger.debug('{}({}) health-check'.format(name, address))
                    self.last_checked[name] = timeutil.jst_now()
                    return True
                else:
                    self.logger.info('{}: changed address {} -> {}'.format(name, address, client_address))
            except KeyError:
                pass
            self.registered[name] = client_address
            self.last_checked[name] = timeutil.jst_now()
            self.logger.info('{}({}) registered'.format(name, client_address))
            return True

    def unregister(self, name: str):
        with self.lock:
            try:
                self.registered.pop(name)
                self.logger.info('{} unregistered'.format(name))
            except KeyError:
                self.logger.warn('{}: not registered'.format(name))

    def get_registered(self) -> Dict[str, Tuple[str, int]]:
        with self.lock:
            self.logger.debug('get_registered')
            return dict(**self.registered)


class Slave(Node):
    POLL_INTERVAL = 1.0  # type: float
    RETRY_INTERVAL = 5.0  # type: float

    def __init__(self, name: str, bind_address: Tuple[str, int], *, master_address: Tuple[str, int]):
        super().__init__(name, bind_address)
        self.master_address = master_address

    def run(self):
        while not self.stopped:
            pool = None
            try:
                pool = gsocketpool.pool.Pool(PoolClient, dict(server_address=self.master_address))
                while not self.stopped:
                    with pool.connection() as client:
                        client.register(self.name, self.bound_address)
                        gevent.sleep(self.POLL_INTERVAL)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                self.logger.exception(str(e))
                try:
                    with pool.connection() as client:
                        client.unregister(self.name)
                except:
                    pass
                gevent.sleep(self.RETRY_INTERVAL)
