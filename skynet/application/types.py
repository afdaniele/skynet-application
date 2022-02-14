import dataclasses
import os
import time
from abc import abstractmethod, ABC
from enum import Enum
from threading import Thread
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


class ServiceType(Enum):
    PUB = "pub"
    SUB = "sub"
    REQ = "req"
    REP = "rep"


@dataclasses.dataclass
class Message(Generic[T]):
    timestamp: float
    data: T
    version: str = "1.0"

    def serialize(self) -> bytes:
        return cbor2.dumps(dataclasses.asdict(self))

    @staticmethod
    def deserialize(raw: bytes) -> 'Message':
        return Message(**cbor2.loads(raw))


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
        self._is_shutdown: bool = False
        # buffer and worker thread
        self._buffer: Buffer[Message[T]] = Buffer(queue_size or self.QUEUE_SIZE)
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

    @property
    def is_shutdown(self) -> bool:
        return self._is_shutdown

    @abstractmethod
    def _work(self):
        pass

    @abstractmethod
    def _shutdown(self):
        pass

    def shutdown(self):
        self._is_shutdown = True
        self._shutdown()

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
    def value(self) -> None:
        return None

    @value.setter
    def value(self, value: Union[T, Message]):
        # TODO: this is where we check whether we are dropping messages
        if isinstance(value, Message):
            msg = value
        else:
            msg = Message(timestamp=time.time(), data=value)
        # ---
        self._buffer.push(msg)

    def _work(self):
        while not self.is_shutdown:
            # REQ(msg)  ->  SWITCHBOARD  ->  REP("")
            data = self._buffer.pop()
            if self.is_shutdown:
                return
            raw = data.serialize()
            self._socket.send(raw, copy=False)
            self._socket.recv(copy=False)

    def _shutdown(self):
        # push a fake message to the queue so that the worker thread wakes up
        self._buffer.push(None)


class SkynetServiceSub(SkynetService, Generic[T]):

    def __init__(self, name: str, data: DataType, callback: Optional[Callable[[T], None]] = None,
                 **kwargs):
        super(SkynetServiceSub, self).__init__(name, ServiceType.SUB, data, **kwargs)
        self._callback: Optional[Callable[[T], None]] = callback
        self._busy: bool = False
        self._worker.start()

    def _pop(self) -> Message:
        return self._buffer.pop()

    @property
    def message(self) -> Message:
        self._assert_no_callback()
        return self._pop()

    @property
    def value(self) -> T:
        return self.message.data

    @property
    def messages(self) -> Iterator[Message]:
        self._assert_no_callback()
        while True:
            yield self._pop()

    def __iter__(self) -> Iterator[T]:
        for message in self.messages:
            yield message.data

    def _assert_no_callback(self):
        if self._callback is not None:
            raise ValueError("You cannot use an instance of SkynetServiceSub with both a callback "
                             "function and .value/iterator.")

    def _work(self):
        while not self.is_shutdown:
            # REQ("")  ->  SWITCHBOARD  ->  REP(msg)
            self._socket.send(b"", copy=False)
            raw = self._socket.recv(copy=False)
            msg = Message.deserialize(raw)
            # callback
            if self._callback is not None:
                self._callback(msg.data)
            # buffer mode
            else:
                # TODO: this is where we check whether we are dropping messages
                self._buffer.push(msg)

    def _shutdown(self):
        pass
