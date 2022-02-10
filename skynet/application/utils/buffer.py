from queue import Queue, Empty, Full
from threading import Semaphore
from typing import Optional, Generic, TypeVar

T = TypeVar("T")


class Buffer(Generic[T]):

    def __init__(self, size: int):
        self._size: int = size
        self._queue: Queue[T] = Queue(size)
        self._lock: Semaphore = Semaphore()

    def pop(self, block: bool = True, timeout: Optional[float] = None) -> Optional[T]:
        try:
            return self._queue.get(block=block, timeout=timeout)
        except Empty:
            return None

    def push(self, data: T):
        with self._lock:
            try:
                # try to put a new item in
                self._queue.put(data, block=False)
            except Full:
                # no space left in the queue, try to remove the oldest one
                try:
                    return self._queue.get(block=False)
                except Empty:
                    pass
                # add again, now we got a spot
                self._queue.put(data, block=False)
