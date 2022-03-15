from functools import partial
from threading import Semaphore
from typing import Tuple, List, Any, Optional, Callable, Iterator

from skynet.application import SkynetServiceSub
from skynet.application.types import Message
from skynet.application.utils.buffer import Buffer


class SimpleServicesSynchronizer:

    def __init__(self,
                 services: Tuple[SkynetServiceSub, ...],
                 callback: Optional[Callable[[Tuple[Any, ...]], None]] = None,
                 message_callback: bool = False):
        # store parameters
        self._services: Tuple[SkynetServiceSub, ...] = services
        self._callback: Optional[Callable[[Tuple[Any, ...]], None]] = callback
        self._message_callback: bool = message_callback
        # utility objects
        self._lock: Semaphore = Semaphore()
        # internal state
        self._buffer: Buffer[Tuple[Any, ...]] = Buffer(size=1)
        self._partial: List[Any] = [None] * len(self._services)
        self._counter = 0
        # register same callback with all services
        for i, service in enumerate(self._services):
            service.register_callback(partial(self._internal_callback, i), message_callback=True)

    def _internal_callback(self, index: int, msg: Message):
        with self._lock:
            self._counter += int(self._partial[index] is None)
            self._partial[index] = msg
            # open gate when we have one message per service
            if self._counter == len(self._services):
                # send messages out
                # - callback mode
                if self._callback is not None:
                    msgs = tuple((m if self._message_callback else m.data) for m in self._partial)
                    self._callback(msgs)
                # - buffer mode
                else:
                    msgs = tuple(self._partial)
                    self._buffer.push(msgs)
                # clear internal state
                self._partial.clear()
                self._counter = 0

    @property
    def message(self) -> Tuple[Message, ...]:
        self._assert_no_callback()
        return self._buffer.pop()

    @property
    def messages(self) -> Iterator[Tuple[Message, ...]]:
        self._assert_no_callback()
        while True:
            yield self._buffer.pop()

    @property
    def value(self) -> Tuple[Any]:
        return tuple(m.data for m in self.message)

    def __iter__(self) -> Iterator[Tuple[Any]]:
        self._assert_no_callback()
        while True:
            yield tuple(m.data for m in self._buffer.pop())

    def _assert_no_callback(self):
        if self._callback is not None:
            raise ValueError("You cannot use an instance of SimpleServicesSynchronizer with both "
                             "a callback function and .value/iterator.")
