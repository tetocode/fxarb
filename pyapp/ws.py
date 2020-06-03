import json
import threading
import time

import websocket
from docopt import docopt


def on_message(ws, message):
    message = json.loads(message)
    print(message)
    if message.get('method') == 'Network.dataReceived':
        ws.send(dict(method='Network.getResponseBody', requestId=int(message['params']['requestId'])))


def on_error(ws, error):
    print(error)


def on_close(ws):
    print("### closed ###")


def on_open(ws):
    def run(*args):
        for i in range(3):
            time.sleep(1)
            ws.send("Hello %d" % i)
        time.sleep(1)
        ws.close()
        print("thread terminating...")

    req = json.dumps(dict(method='Network.enable', id=1))#, url='https://google.com'))
    ws.send(req)
    #threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    args = docopt("""
    Usage:
      CMD [options] URL

    Options:
    """)
    url = args['URL']
    websocket.enableTrace(True)
    ws = websocket.WebSocketApp(url,
                                on_open=on_open,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close)
    #ws.on_open = on_open
    ws.run_forever()
