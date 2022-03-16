import json
import os
import signal
from collections import defaultdict
from threading import Semaphore
from typing import Dict, Callable, Set, Tuple

from skynet.application.logging import salogger
from skynet.application.proxy.node import Node
from skynet.application.types import SkynetService
from skynet.application.utils.monitored_condition import MonitoredCondition

EventName = str
CallbackPriority = int


class SkynetApplication:
    services: Dict[Tuple[str, str], SkynetService] = {}

    # properties
    # TODO: this is temporary, these should be returned by the call to "service/expose" above
    properties: dict = json.loads(os.environ.get("_SKYNET_APP_PROPERTIES_JSON", "{}"))

    # events
    events_callbacks: Dict[EventName, Dict[CallbackPriority, Set[Callable]]] = defaultdict(
        lambda: defaultdict(set))
    events_lock: Semaphore = Semaphore()
    shutdown_event: MonitoredCondition = MonitoredCondition()

    @classmethod
    def storage_path(cls, fpath: str = "") -> str:
        return os.path.join("/storage", fpath).rstrip("/")

    @classmethod
    def expose(cls, service: SkynetService):
        if (service.type.value, service.name) in cls.services:
            raise ValueError(f"Service '{service.name}' of type '{service.type}' is already "
                             f"exposed. You can't expose the same service twice.")
        cls.services[(service.type.value, service.name)] = service
        # notify the node
        Node.call("service/expose", service.serialize())

    @classmethod
    def _on_event_shutdown(cls):
        with cls.events_lock:
            callbacks = cls.events_callbacks["shutdown"]
            for priority in sorted(callbacks.keys(), reverse=True):
                for cb in callbacks[priority]:
                    cb()
            # trigger internal signal
            with cls.shutdown_event:
                cls.shutdown_event.notify_all()

    @classmethod
    def _on_sigint_signal(cls, _, __):
        salogger.info("Received shutdown request. Terminating gracefully...")
        cls._on_event_shutdown()
        exit(0)

    @classmethod
    def on_shutdown(cls, callback: Callable, priority: CallbackPriority = 0):
        with cls.events_lock:
            cls.events_callbacks["shutdown"][priority].add(callback)

    @classmethod
    def join(cls):
        # wait on internal shutdown signal
        with cls.shutdown_event:
            cls.shutdown_event.wait()


# noinspection PyProtectedMember
signal.signal(signal.SIGINT, SkynetApplication._on_sigint_signal)
