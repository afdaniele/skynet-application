from typing import Tuple, Iterator, Any

from skynet.application import SkynetServiceSub
from skynet.application.synchronization import SimpleServicesSynchronizer


def join(services: Tuple[SkynetServiceSub, ...], messages: bool = False) -> \
        Iterator[Tuple[Any, ...]]:
    sync = SimpleServicesSynchronizer(services, message_callback=messages)
    return sync.__iter__()
