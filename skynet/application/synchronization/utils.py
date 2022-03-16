from typing import Tuple, Iterator, Any, Union

from skynet.application import SkynetServiceSub
from skynet.application.synchronization import SimpleServicesSynchronizer
from skynet.application.types import Message


def join(services: Tuple[SkynetServiceSub, ...], messages: bool = False) -> \
        Iterator[Tuple[Union[Message, Any], ...]]:
    sync = SimpleServicesSynchronizer(services, message_callback=messages)
    return sync.__iter__()
