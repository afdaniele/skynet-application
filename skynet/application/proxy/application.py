import signal
from types import FrameType
from typing import Dict, Callable, Set, Optional

from skynet.application.proxy.node import Node
from skynet.application.types import SkynetService


class SkynetApplication:
    __services: Dict[str, SkynetService] = {}
    __shutdown_callbacks: Set[Callable[[int, Optional[FrameType]], None]] = set()

    @classmethod
    def expose(cls, service: SkynetService):
        if service.name in cls.__services:
            raise ValueError(f"Service '{service.name}' is already exposed. You can't expose "
                             f"the same service twice.")
        cls.__services[service.name] = service
        # notify the node
        Node.call("service/expose", service.serialize())

    @classmethod
    def on_shutdown(cls, handler: Callable[[int, Optional[FrameType]], None]):
        cls.__shutdown_callbacks.add(handler)

    @classmethod
    def shutdown(cls, sig: int, frame: Optional[FrameType]):
        for cb in cls.__shutdown_callbacks:
            cb(sig, frame)


# register SkynetApplication.shutdown as handler for SIGINT
signal.signal(signal.SIGINT, SkynetApplication.shutdown)
