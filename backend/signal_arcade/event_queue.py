"""Bounded priority queue with a finite, drainable season admission boundary."""

from __future__ import annotations

import asyncio
import heapq
from collections import deque
from threading import RLock

from .models import MarketEvent

QueuedEvent = tuple[int, int, MarketEvent]


class SeasonEventQueue(asyncio.PriorityQueue[QueuedEvent]):
    # asyncio initializes these queues, but typeshed omits its private extension hooks.
    _putters: deque[asyncio.Future[None]]
    _getters: deque[asyncio.Future[None]]

    def _wakeup_next(self, waiters: deque[asyncio.Future[None]]) -> None:
        while waiters:
            waiter = waiters.popleft()
            if not waiter.done():
                waiter.set_result(None)
                break

    def __init__(self, maxsize: int) -> None:
        self._boundary_lock = RLock()
        self.boundary: int | None = None
        self._pending_sequences: set[int] = set()
        self._dequeued_sequences: deque[int] = deque()
        super().__init__(maxsize=maxsize)

    def _init(self, maxsize: int) -> None:
        self._queue: list[tuple[int, int, int, MarketEvent]] = []

    def admit(self, sequence: int) -> None:
        # Include critical producers waiting for queue capacity in the finite admitted set.
        with self._boundary_lock:
            self._pending_sequences.add(sequence)

    @property
    def boundary_active(self) -> bool:
        with self._boundary_lock:
            return self.boundary is not None

    def forget(self, sequence: int) -> None:
        with self._boundary_lock:
            self._pending_sequences.discard(sequence)

    def _put(self, item: QueuedEvent) -> None:
        priority, sequence, event = item
        with self._boundary_lock:
            self._pending_sequences.add(sequence)
            later = int(self.boundary is not None and sequence > self.boundary)
            heapq.heappush(self._queue, (later, priority, sequence, event))

    def put_nowait(self, item: QueuedEvent) -> None:
        with self._boundary_lock:
            if self.boundary is not None and item[1] > self.boundary and self.maxsize > 0:
                admitted = {row[2] for row in self._queue} | set(self._dequeued_sequences)
                waiting = sum(
                    sequence <= self.boundary and sequence not in admitted
                    for sequence in self._pending_sequences
                )
                # Parked new arrivals must not occupy capacity owed to old critical producers.
                if self.qsize() >= max(0, self.maxsize - waiting):
                    raise asyncio.QueueFull
            super().put_nowait(item)

    async def put(self, item: QueuedEvent) -> None:
        while True:
            try:
                self.put_nowait(item)
                return
            except asyncio.QueueFull:
                if not self.full():
                    self._wakeup_next(self._putters)
                putter = asyncio.get_running_loop().create_future()
                self._putters.append(putter)
                try:
                    await putter
                except BaseException:
                    putter.cancel()
                    if putter in self._putters:
                        self._putters.remove(putter)
                    if not self.full() and not putter.cancelled():
                        self._wakeup_next(self._putters)
                    raise

    def _get(self) -> QueuedEvent:
        with self._boundary_lock:
            _, priority, sequence, event = heapq.heappop(self._queue)
            self._dequeued_sequences.append(sequence)
            return priority, sequence, event

    def empty(self) -> bool:
        with self._boundary_lock:
            return not self._queue or bool(self._queue[0][0])

    def get_nowait_before(self, priority: int) -> QueuedEvent:
        """Take a more urgent arrival only if it belongs to the current season boundary."""
        with self._boundary_lock:
            if self.empty() or self._queue[0][1] >= priority:
                raise asyncio.QueueEmpty
            return self.get_nowait()

    def has_ready_before(self, priority: int) -> bool:
        """Inspect admitted priority without consuming or scanning the heap."""
        with self._boundary_lock:
            return not self.empty() and self._queue[0][1] < priority

    def task_done(self) -> None:
        super().task_done()
        with self._boundary_lock:
            if self._dequeued_sequences:
                self._pending_sequences.discard(self._dequeued_sequences.popleft())

    def begin_boundary(self, sequence: int) -> None:
        with self._boundary_lock:
            if self.boundary is not None:
                return
            self.boundary = max(sequence, max(self._pending_sequences, default=sequence))
            self._queue = [(0, p, s, e) for _, p, s, e in self._queue]
            heapq.heapify(self._queue)

    def boundary_ready(self) -> bool:
        with self._boundary_lock:
            return self.boundary is not None and not any(
                sequence <= self.boundary for sequence in self._pending_sequences
            )

    def end_boundary(self) -> None:
        # Called by the event-loop owner, so waking queue consumers is thread-safe.
        with self._boundary_lock:
            self.boundary = None
            self._queue = [(0, p, s, e) for _, p, s, e in self._queue]
            heapq.heapify(self._queue)
        self._wakeup_next(self._getters)
        self._wakeup_next(self._putters)

    def discard_queued(self) -> None:
        """Discard queued/parked rows on a source switch, retaining in-flight accounting."""
        with self._boundary_lock:
            discarded = len(self._queue)
            for _, _, sequence, _ in self._queue:
                self._pending_sequences.discard(sequence)
            self._queue.clear()
            self.boundary = None
            # These rows were never dequeued. Do not consume an in-flight worker's receipts.
            for _ in range(discarded):
                super().task_done()
        while self._putters:
            self._wakeup_next(self._putters)
