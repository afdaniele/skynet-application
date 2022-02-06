import socket

from requests import Session
from urllib3.connection import HTTPConnection
from urllib3.connectionpool import HTTPConnectionPool
from requests.adapters import HTTPAdapter


class UnixSocketConnection(HTTPConnection):

    def __init__(self, socket_fpath: str, host: str):
        super(UnixSocketConnection, self).__init__(host)
        self._socket_fpath = socket_fpath
        self.sock = None

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self._socket_fpath)


class UnixSocketConnectionPool(HTTPConnectionPool):

    def __init__(self, socket_fpath: str, host: str):
        super().__init__(host)
        self._host = host
        self._socket_fpath = socket_fpath

    def _new_conn(self):
        return UnixSocketConnection(self._socket_fpath, self._host)


class UnixSocketAdapter(HTTPAdapter):

    def __init__(self, socket_fpath: str, host: str):
        super(UnixSocketAdapter, self).__init__()
        self._host = host
        self._socket_fpath = socket_fpath

    def get_connection(self, url, proxies=None):
        return UnixSocketConnectionPool(self._socket_fpath, self._host)


class UnixSocketHTTPEndpoint(Session):

    def __init__(self, socket_fpath: str, host: str, protocol: str = "http"):
        super(UnixSocketHTTPEndpoint, self).__init__()
        self.mount(f"{protocol}://{host}/", UnixSocketAdapter(socket_fpath, host))
