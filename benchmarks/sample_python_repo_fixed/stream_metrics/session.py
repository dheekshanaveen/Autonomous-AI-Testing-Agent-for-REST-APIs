"""Session manager for stream events (Fixed revision)."""

from typing import Any, List, Optional


class StreamSession:
    """Manages active event queue and state transitions safely."""

    def __init__(self):
        self.events: List[Any] = []
        self.is_active = True

    def push(self, event: Any) -> None:
        """Add event to stream queue."""
        self.events.append(event)

    def pop(self) -> Optional[Any]:
        """
        Pop next event from stream queue safely.
        
        Returns:
            The next event, or None if queue is empty.
        """
        if not self.events:
            return None
        return self.events.pop()

