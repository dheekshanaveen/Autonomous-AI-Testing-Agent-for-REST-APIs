"""Session manager for stream events."""

from typing import Any, List


class StreamSession:
    """Manages active event queue and state transitions."""

    def __init__(self):
        self.events: List[Any] = []
        self.is_active = True

    def push(self, event: Any) -> None:
        """Add event to stream queue."""
        self.events.append(event)

    def pop(self) -> Any:
        """
        Pop next event from stream queue.
        
        Returns:
            The next event.
        """
        # Defect: IndexError when popping from empty queue on uninitialized state
        return self.events.pop()

