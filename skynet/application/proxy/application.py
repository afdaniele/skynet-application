from typing import Dict

from skynet.application.proxy.node import Node
from skynet.application.types import SkynetService


class SkynetApplication:
    services: Dict[str, SkynetService] = {}

    @classmethod
    def expose(cls, service: SkynetService):
        if service.name in cls.services:
            raise ValueError(f"Service '{service.name}' is already exposed. You can't expose "
                             f"the same service twice.")
        cls.services[service.name] = service
        # notify the node
        Node.call("service/expose", service.serialize())
