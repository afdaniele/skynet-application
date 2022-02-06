from threading import Condition
from typing import Optional


class MonitoredCondition(Condition):

    def __init__(self):
        super(MonitoredCondition, self).__init__()
        self._has_changes = False

    def clear(self):
        self._has_changes = False

    def notifyAll(self) -> None:
        return self.notify_all()

    def notify_all(self) -> None:
        self._has_changes = True
        super(MonitoredCondition, self).notify_all()

    def notify(self, n: int = 1) -> None:
        self._has_changes = True
        super(MonitoredCondition, self).notify(n=n)

    def wait(self, timeout: Optional[float] = None) -> bool:
        if self._has_changes:
            self._has_changes = False
            return True
        return super(MonitoredCondition, self).wait(timeout=timeout)
