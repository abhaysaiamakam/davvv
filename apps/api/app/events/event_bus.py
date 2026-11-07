"""
M6 — In-Process Thread-Safe Event Bus.

Provides decoupled pub/sub for dataset lifecycle events without external message brokers.
Handlers are executed safely and idempotently.
"""
from __future__ import annotations

import logging
import threading
import uuid
from typing import Callable, Dict, List, Optional

from app.events.event_types import DatasetLifecycleEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[DatasetLifecycleEvent], None]


class EventBus:
    """Lightweight in-memory event bus with listener error isolation."""

    def __init__(self):
        self._lock = threading.RLock()
        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._event_history: List[DatasetLifecycleEvent] = []
        self._processed_events: set = set()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register a callback for an event type."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unregister a callback."""
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type] = [
                    h for h in self._subscribers[event_type] if h != handler
                ]

    def publish(self, event: DatasetLifecycleEvent) -> None:
        """
        Publish an event to all registered listeners.
        Guarantees isolation: one handler failure does not prevent other handlers from executing.
        """
        with self._lock:
            # Check idempotency per event_id
            if event.event_id in self._processed_events:
                logger.debug(f"Event {event.event_id} already processed, skipping.")
                return
            self._processed_events.add(event.event_id)
            self._event_history.append(event)
            # Keep history bounded to last 500 events
            if len(self._event_history) > 500:
                self._event_history = self._event_history[-500:]

            handlers = list(self._subscribers.get(event.event_type, []))
            # Also invoke wildcard handlers if any
            handlers.extend(self._subscribers.get("*", []))

        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                logger.error(
                    f"Error in event handler {handler.__name__ if hasattr(handler, '__name__') else handler} "
                    f"for event {event.event_type} ({event.event_id}): {exc}",
                    exc_info=True,
                )

    def emit(
        self,
        event_type: str,
        dataset_id: str,
        version_id: Optional[str] = None,
        job_id: Optional[str] = None,
        payload: Optional[Dict] = None,
    ) -> DatasetLifecycleEvent:
        """Helper to create and publish a DatasetLifecycleEvent in one call."""
        event = DatasetLifecycleEvent(
            event_id=f"evt-{uuid.uuid4().hex[:12]}",
            event_type=event_type,
            dataset_id=dataset_id,
            version_id=version_id,
            job_id=job_id,
            payload=payload or {},
        )
        self.publish(event)
        return event

    def get_history(
        self, dataset_id: Optional[str] = None, event_type: Optional[str] = None
    ) -> List[DatasetLifecycleEvent]:
        """Query recent event audit log."""
        with self._lock:
            events = list(self._event_history)
        if dataset_id:
            events = [e for e in events if e.dataset_id == dataset_id]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events

    def clear(self) -> None:
        """Reset subscriptions and history (primarily for tests)."""
        with self._lock:
            self._subscribers.clear()
            self._event_history.clear()
            self._processed_events.clear()


# Global singleton event bus
event_bus = EventBus()

