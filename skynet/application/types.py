import dataclasses
from abc import abstractmethod, ABC
from enum import Enum
from threading import Semaphore
from typing import TypeVar, Generic, Optional, Union, Any, List

from skynet.application.utils.monitored_condition import MonitoredCondition

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
class DataType(ISerializable):
    name: str
    dimensions: List[int] = dataclasses.field(default_factory=list)

    def serialize(self, dynamic: bool = False) -> dict:
        return {
            "name": self.name,
            "dimensions": self.dimensions,
        }

    @classmethod
    def deserialize(cls, data: dict) -> 'DataType':
        return DataType(
            name=data["name"],
            dimensions=data.get("dimensions", []),
        )

    def __eq__(self, other):
        if not isinstance(other, DataType):
            return False
        return self.name == other.name and self.dimensions == other.dimensions


class SkynetService(ISerializable, Generic[T]):

    def __init__(self, name: str, type: ServiceType, data: DataType, expose: bool = True):
        self._name = name
        self._type = type
        self._data = data
        self._lock = Semaphore()
        self._event = MonitoredCondition()
        self._buffer = None
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

    def __s_buffer_pop__(self) -> Optional[T]:
        # empty buffer
        with self._lock:
            data = self._buffer
            self._buffer = None
        return data

    def __s_buffer_put__(self, data: T):
        # populate buffer
        with self._lock:
            # TODO: this is where we check whether we are dropping messages
            self._buffer = data
        # notify sender thread
        with self._event:
            self._event.notify()

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

    def publish(self, data: T):
        # put data into the buffer, the worker thread will be notified automatically
        self.__s_buffer_put__(data)


class SkynetServiceSub(SkynetService, Generic[T]):

    def __init__(self, name: str, data: DataType, **kwargs):
        super(SkynetServiceSub, self).__init__(name, ServiceType.SUB, data, **kwargs)

    def receive(self, timeout: Optional[float] = None) -> Optional[T]:
        # we already have something?
        data = self.__s_buffer_pop__()
        if data is not None or timeout <= 0.0:
            return data
        # let's wait then
        with self._event:
            self._event.wait(timeout)
            return self.__s_buffer_pop__()
