from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from time import monotonic


@dataclass(slots=True)
class HourlyRateLimiter:
    limit: int
    window_seconds: int = 3600
    _events: dict[int, deque[float]] = field(default_factory=lambda: defaultdict(deque))

    def allow(self, user_id: int, now: float | None = None) -> bool:
        timestamp = monotonic() if now is None else now
        events = self._events[user_id]
        threshold = timestamp - self.window_seconds
        while events and events[0] <= threshold:
            events.popleft()
        if len(events) >= self.limit:
            return False
        events.append(timestamp)
        return True

