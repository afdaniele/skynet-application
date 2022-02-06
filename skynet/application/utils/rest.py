import socket

from requests import Session
from urllib3.connection import HTTPConnection
from urllib3.connectionpool import HTTPConnectionPool
from requests.adapters import HTTPAdapter


class UnixSocketConnection(HTTPConnection):

    def __init__(self, socket_fpath: str):
        super().__init__()
        self._socket_fpath = socket_fpath
        self.sock = None

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self._socket_fpath)


class UnixSocketConnectionPool(HTTPConnectionPool):

    def __init__(self, socket_fpath: str):
        super().__init__(socket_fpath)

    def _new_conn(self):
        return UnixSocketConnection(self.host)


class UnixSocketAdapter(HTTPAdapter):

    def __init__(self, socket_fpath: str):
        super().__init__()
        self._socket_fpath = socket_fpath

    def get_connection(self, url, proxies=None):
        return UnixSocketConnectionPool(self._socket_fpath)


class UnixSocketHTTPEndpoint(Session):

    def __init__(self, socket_fpath: str, host: str, protocol: str = "http"):
        super(UnixSocketHTTPEndpoint, self).__init__()
        self.mount(f"{protocol}://{host}/", UnixSocketAdapter(socket_fpath))
