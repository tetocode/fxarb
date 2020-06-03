import logging
import signal
import sys
import threading
from typing import Tuple

from mitmproxy import options, exceptions
from mitmproxy.controller import handler as controller_handler
from mitmproxy.http import HTTPFlow
from mitmproxy.proxy import config
from mitmproxy.tools import cmdline
from mitmproxy.tools.dump import DumpMaster
from mitmproxy.utils import version_check, debug
from mitmproxy.websocket import WebSocketFlow

from pyfxnode.server import Server


class ProxyHandler:
    def handle_request_header(self, flow: HTTPFlow):
        pass

    def handle_request(self, flow: HTTPFlow):
        pass

    def handle_response_header(self, flow: HTTPFlow):
        pass

    def handle_response(self, flow: HTTPFlow):
        pass

    def handle_websocket_message(self, flow: WebSocketFlow):
        pass


class ProxyServer(Server):
    def __init__(self, address: Tuple[str, int], handler: ProxyHandler, logger: logging.Logger = None):
        class ProxyMaster(DumpMaster):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

            @controller_handler
            def requestheaders(self, flow: HTTPFlow):
                handler.handle_request_header(flow)

            @controller_handler
            def request(self, flow: HTTPFlow):
                handler.handle_request_header(flow)

            @controller_handler
            def responseheaders(self, flow: HTTPFlow):
                handler.handle_response_header(flow)

            @controller_handler
            def response(self, flow: HTTPFlow):
                handler.handle_response(flow)

            @controller_handler
            def websocket_message(self, flow: WebSocketFlow):
                handler.handle_websocket_message(flow)

        super().__init__(logger=logger)
        self.address = address
        self._thread = threading.Thread(target=self.run, name=self.logger.name, daemon=True)
        self._master_type = ProxyMaster
        self._master = None  # type: ProxyMaster

    def is_running(self) -> bool:
        return self._thread.is_alive()

    @property
    def server_address(self) -> Tuple[str, int]:
        return self.address

    def start(self):
        self._thread.start()

        def clean_kill(*args, **kwargs):
            self._master and self._master.shutdown()

        signal.signal(signal.SIGTERM, clean_kill)

    def stop(self, timeout: float = None):
        if self._master:
            self._master.shutdown()

    def join(self, timeout: float = None):
        self._thread.join(timeout)

    def run(self):
        def process_options(_, _options, _args):
            from mitmproxy.proxy import server  # noqa

            if _args.version:
                print(debug.dump_system_info())
                sys.exit(0)

            # debug.register_info_dumpers()
            pconf = config.ProxyConfig(_options)
            if _options.no_server:
                return server.DummyServer(pconf)
            else:
                try:
                    return server.ProxyServer(pconf)
                except exceptions.ServerException as v:
                    print(str(v), file=sys.stderr)
                    sys.exit(1)

        from mitmproxy.tools import dump

        args = ['-b', self.address[0], '-p', str(self.address[1]), '-q']

        version_check.check_pyopenssl_version()

        parser = cmdline.mitmdump()
        args = parser.parse_args(args)
        if args.quiet:
            args.flow_detail = 0

        master = None
        try:
            dump_options = options.Options()
            dump_options.load_paths(args.conf)
            dump_options.merge(cmdline.get_common_options(args))
            dump_options.merge(
                dict(
                    flow_detail=args.flow_detail,
                    keepserving=args.keepserving,
                    filtstr=" ".join(args.filter) if args.filter else None,
                )
            )

            server = process_options(parser, dump_options, args)
            self._master = master = self._master_type(dump_options, server)

            # def clean_kill(*args, **kwargs):
            #    master.shutdown()

            # signal.signal(signal.SIGTERM, clean_kill)
            self.info('bind at tcp:{}'.format(self.server_address))
            master.run()
            self.info('stopped')
        except (dump.DumpError, exceptions.OptionsError) as e:
            print("mitmdump: %s" % e, file=sys.stderr)
            sys.exit(1)
        except (KeyboardInterrupt, RuntimeError):
            pass
        if master is None or master.has_errored:
            print("mitmdump: errors occurred during run", file=sys.stderr)
            sys.exit(1)
