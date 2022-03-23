import dataclasses
import os
import time
from abc import abstractmethod, ABC
from enum import Enum
from threading import Thread, Semaphore
from typing import TypeVar, Generic, Optional, Union, Any, Callable, Iterator, Tuple

import cbor2 as cbor2
import zmq as zmq

from skynet.application.constants import SKYNET_SOCKETS_DIR, ZMQ_CONTEXT
from skynet.application.logging import salogger
from skynet.application.utils.buffer import Buffer
from skynet.application.utils.monitored_condition import MonitoredCondition

T = TypeVar("T")
NOTHING = object()
EMPTY_REQUEST = (b"", b"")


class ISerializable(ABC):

    @abstractmethod
    def serialize(self, dynamic: bool = False) -> Union[str, dict]:
        pass

    @classmethod
    @abstractmethod
    def deserialize(cls, *args, **kwargs) -> Any:
        pass


@dataclasses.dataclass
class Header:
    timestamp: float
    version: str = "1.0"

    def serialize(self) -> bytes:
        return cbor2.dumps(dataclasses.asdict(self))

    @classmethod
    def deserialize(cls, raw: bytes) -> Optional['Header']:
        try:
            # noinspection PyArgumentList
            msg = cls(**cbor2.loads(raw))
            return msg
        except (TypeError, ValueError) as e:
            salogger.warning(f"Received error '{str(e)}' while decoding a message header")
            return None


class Message:

    def __init__(self, timestamp: float, data: Any):
        self._header: Header = Header(timestamp=timestamp)
        self._data: Any = data
        self._length: Optional[int] = None
        self._version: str = "1.0"

    @property
    def data(self) -> Any:
        return self._data

    @property
    def timestamp(self) -> float:
        return self._header.timestamp

    @timestamp.setter
    def timestamp(self, value: float):
        self._header.timestamp = value

    @property
    def header(self) -> Header:
        return self._header

    @header.setter
    def header(self, value: Header):
        self._header = value

    def as_dict(self) -> dict:
        return {
            "data": self._data,
            "version": self._version,
        }

    def serialize(self) -> Tuple[bytes, bytes]:
        return self._header.serialize(), cbor2.dumps(self.as_dict())

    @classmethod
    def deserialize(cls, header: bytes, payload: bytes) -> Optional['Message']:
        # decode header
        header = Header.deserialize(header)
        if header is None:
            return None
        # decode message
        try:
            # noinspection PyArgumentList
            d = cbor2.loads(payload)

            # TODO: support multiple versions
            assert d.pop("version", None) == "1.0"

            msg = cls(**d, timestamp=header.timestamp)
            msg.length = len(payload)
            msg.header = header
        except (TypeError, ValueError) as e:
            salogger.warning(f"Received error '{str(e)}' while decoding a message")
            return None
        # ---
        return msg


class ServiceType(Enum):
    PUB = "pub"
    SUB = "sub"
    REQ = "req"
    REP = "rep"


@dataclasses.dataclass
class DataType(ISerializable):
    type: type
    shape: Tuple[int, ...] = dataclasses.field(default_factory=tuple)

    def serialize(self, dynamic: bool = False) -> dict:
        return {
            "name": self.type.__name__,
            "shape": self.shape,
        }

    @classmethod
    def deserialize(cls, data: dict):
        return None

    def __eq__(self, other):
        if not isinstance(other, DataType):
            return False
        return self.type is other.type and self.shape == other.shape


class SkynetService(ISerializable, Generic[T], ABC):
    QUEUE_SIZE: int = 1

    def __init__(self, name: str, type: ServiceType, data: DataType, expose: bool = True,
                 queue_size: Optional[int] = None):
        self._name = name
        self._type = type
        self._data = data
        # buffer and worker thread
        self._buffer: Buffer[T] = Buffer(queue_size or self.QUEUE_SIZE)
        self._worker: Thread = Thread(target=self._work, daemon=True)
        # connect to local unix socket
        self._socket_path = os.path.join(SKYNET_SOCKETS_DIR, "services", type.value,
                                         f"{name}.sock")
        self._url = f"ipc://{self._socket_path}"
        self._socket = ZMQ_CONTEXT.socket(zmq.REQ)
        # TODO: set high watermark
        self._socket.connect(self._url)
        salogger.info(f"Connected to socket '{self._url}'")
        # auto-expose
        if expose:
            from skynet.application import SkynetApplication
            SkynetApplication.expose(self)

    @property
    def name(self) -> str:
        return self._name

    @property
    def type(self) -> ServiceType:
        return self._type

    @property
    def data(self) -> DataType:
        return self._data

    @abstractmethod
    def _work(self):
        pass

    def serialize(self, dynamic: bool = False) -> dict:
        return {
            "name": self._name,
            "type": self._type.value,
            "data": self._data.serialize(dynamic=dynamic),
        }

    @classmethod
    def deserialize(cls, data: dict) -> 'SkynetService':
        return SkynetService(
            name=data["name"],
            type=ServiceType(data["type"]),
            data=DataType.deserialize(data["data"]),
        )


class SkynetServicePub(SkynetService, Generic[T]):

    def __init__(self, name: str, data: DataType, **kwargs):
        super(SkynetServicePub, self).__init__(name, ServiceType.PUB, data, **kwargs)
        self._worker.start()

    @property
    def message(self) -> None:
        return None

    @message.setter
    def message(self, value: Message):
        # TODO: this is where we check whether we are dropping messages
        self._buffer.push(value)

    @property
    def value(self) -> None:
        return None

    @value.setter
    def value(self, value: T):
        # TODO: this is where we check whether we are dropping messages
        self._buffer.push(value)

    def _work(self):
        while True:
            # REQ(msg)  ->  SWITCHBOARD  ->  REP("")
            data = self._buffer.pop()
            header, raw = (data if isinstance(data, Message) else Message(time.time(), data)).serialize()
            self._socket.send_multipart((header, raw), copy=False)
            self._socket.recv_multipart(copy=False)


class SkynetServiceSub(SkynetService, Generic[T]):

    def __init__(self, name: str, data: DataType, callback: Optional[Callable[[T], None]] = None,
                 message_callback: bool = False, changes_only: bool = False, **kwargs):
        super(SkynetServiceSub, self).__init__(name, ServiceType.SUB, data, **kwargs)
        self._callback: Optional[Callable[[T], None]] = callback
        self._message_callback: bool = message_callback
        self._changes_only: bool = changes_only
        self._last: Union[Message, object] = NOTHING
        self._last_raw: bytes = b""
        # events
        self._event_new_message = MonitoredCondition()
        # mailman
        self._worker.start()

    @property
    def message(self) -> Message:
        self._assert_no_callback()
        return self._buffer.pop()

    @property
    def messages(self) -> Iterator[Message]:
        self._assert_no_callback()
        while True:
            yield self._buffer.pop()

    @property
    def value(self) -> T:
        return self.message.data

    @property
    def last(self) -> Message:
        if self._last is NOTHING:
            with self._event_new_message:
                self._event_new_message.wait()
        return self._last

    def register_callback(self, callback: Callable[[T], None],
                          message_callback: Optional[bool] = None):
        self._callback = callback
        if message_callback is not None:
            self._message_callback = message_callback

    def __iter__(self):
        self._assert_no_callback()
        while True:
            yield self._buffer.pop().data

    def _assert_no_callback(self):
        if self._callback is not None:
            raise ValueError("You cannot use an instance of SkynetServiceSub with both a callback "
                             "function and .value/iterator.")

    def _work(self):
        while True:
            # REQ("")  ->  SWITCHBOARD  ->  REP(msg)
            self._socket.send_multipart(EMPTY_REQUEST, copy=False)
            header, payload = self._socket.recv_multipart(copy=False)
            msg = Message.deserialize(header, payload)
            if msg is None:
                continue
            # store as "last"
            self._last = msg
            # callback
            if self._callback is not None:
                propagate: bool = True
                # changes only
                if self._changes_only:
                    if len(payload) == len(self._last_raw) and payload == self._last_raw:
                        propagate = False
                    self._last_raw = payload
                if propagate:
                    self._callback(msg if self._message_callback else msg.data)
            # buffer mode
            else:
                # TODO: this is where we check whether we are dropping messages
                self._buffer.push(msg)
            # trigger event
            with self._event_new_message:
                self._event_new_message.notify_all()


class SkynetInteraction:
    QUEUE_SIZE: int = 1

    def __init__(self, callback: Optional[Callable[[bytes], None]] = None,
                 queue_size: Optional[int] = None):
        self._callback = callback
        # buffer and worker thread
        self._buffer: Buffer[T] = Buffer(queue_size or self.QUEUE_SIZE)
        self._worker: Thread = Thread(target=self._work, daemon=True)
        self._lock: Semaphore = Semaphore()
        # connect to local unix socket
        self._socket_path = os.path.join(SKYNET_SOCKETS_DIR, "interaction.sock")
        self._url = f"ipc://{self._socket_path}"
        self._socket = ZMQ_CONTEXT.socket(zmq.PAIR)
        # TODO: set high watermark
        self._socket.connect(self._url)
        salogger.info(f"Connected to socket '{self._url}'")
        self._worker.start()

    def _work(self):
        # PAIR(self)  <->  PAIR(ApplicationDeployment)
        while True:
            if not self._socket.poll(1000, zmq.POLLIN):
                continue
            # get data
            data = self._socket.recv(flags=zmq.NOBLOCK)
            if self._callback:
                self._callback(data)

    def send(self, data: Any):
        raw: bytes = cbor2.dumps(data)
        with self._lock:
            self._socket.send(raw)
