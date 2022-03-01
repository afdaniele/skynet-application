import dataclasses
import os
import time
from abc import abstractmethod, ABC
from enum import Enum
from threading import Thread, Semaphore
from typing import TypeVar, Generic, Optional, Union, Any, List, Callable, Iterator

import cbor2 as cbor2
import zmq as zmq

from skynet.application.constants import SKYNET_SOCKETS_DIR, ZMQ_CONTEXT
from skynet.application.logging import salogger
from skynet.application.utils.buffer import Buffer

T = TypeVar("T")


class ISerializable(ABC):

    @abstractmethod
    def serialize(self, dynamic: bool = False) -> Union[str, dict]:
        pass

    @classmethod
    @abstractmethod
    def deserialize(cls, *args, **kwargs) -> Any:
        pass


@dataclasses.dataclass
class Message:
    timestamp: float
    data: bytes
    length: Optional[int] = None
    version: str = "1.0"

    def serialize(self) -> bytes:
        return cbor2.dumps(dataclasses.asdict(self))

    @classmethod
    def deserialize(cls, raw: bytes) -> Optional['Message']:
        try:
            # noinspection PyArgumentList
            msg = cls(**cbor2.loads(raw))
            msg.length = len(raw)
            return msg
        except (TypeError, ValueError) as e:
            salogger.warning(f"Received error '{str(e)}' while decoding a message")
            return None


class ServiceType(Enum):
    PUB = "pub"
    SUB = "sub"
    REQ = "req"
    REP = "rep"


@dataclasses.dataclass
class DataType(ISerializable):
    type: type
    dimensions: List[int] = dataclasses.field(default_factory=list)

    def serialize(self, dynamic: bool = False) -> dict:
        return {
            "name": self.type.__name__,
            "dimensions": self.dimensions,
        }

    @classmethod
    def deserialize(cls, data: dict):
        return None

    def __eq__(self, other):
        if not isinstance(other, DataType):
            return False
        return self.type is other.type and self.dimensions == other.dimensions


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
        self._socket_path = os.path.join(SKYNET_SOCKETS_DIR, "services", f"{name}.sock")
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
            raw = (data if isinstance(data, Message) else Message(time.time(), data)).serialize()
            self._socket.send(raw, copy=False)
            self._socket.recv(copy=False)


class SkynetServiceSub(SkynetService, Generic[T]):

    def __init__(self, name: str, data: DataType, callback: Optional[Callable[[T], None]] = None,
                 message_callback: bool = False, **kwargs):
        super(SkynetServiceSub, self).__init__(name, ServiceType.SUB, data, **kwargs)
        self._callback: Optional[Callable[[T], None]] = callback
        self._message_callback: bool = message_callback
        self._busy: bool = False
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
            self._socket.send(b"", copy=False)
            raw = self._socket.recv(copy=False)
            msg = Message.deserialize(raw)
            if msg is None:
                continue
            # callback
            if self._callback is not None:
                self._callback(msg if self._message_callback else msg.data)
            # buffer mode
            else:
                # TODO: this is where we check whether we are dropping messages
                self._buffer.push(msg)


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
