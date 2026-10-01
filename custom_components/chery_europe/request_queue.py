"""Serialize Chery API calls and space repeated vehicle commands."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

from .const import COMMAND_MIN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

_VEHICLE_CONTROL_PREFIX = "/asc/vehicleControl/"
# GPS read used by polling. It is not a remote command and is not spaced.
_UNPACED_ENDPOINTS = frozenset({"queryVehicleLocation"})


def command_interval_key(path: str, params: dict | None = None) -> str | None:
    """Return the pacing key for a vehicle command, or None for other calls.

    The key is ``vin:endpoint`` so lock and climate are independent, while
    repeating the same command for one vehicle shares one 5 second slot.
    """
    normalized = path if path.startswith("/") else f"/{path}"
    if not normalized.startswith(_VEHICLE_CONTROL_PREFIX):
        return None
    endpoint = normalized[len(_VEHICLE_CONTROL_PREFIX) :].split("/", 1)[0]
    if not endpoint or endpoint in _UNPACED_ENDPOINTS:
        return None
    vin = ""
    if isinstance(params, dict) and params.get("vin"):
        vin = str(params["vin"])
    return f"{vin}:{endpoint}"


class _CommandGate:
    """Serialize sends of one command key."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()


class ApiRequestQueue:
    """Queue outgoing API calls and keep each command at least 5s apart.

    One shared slot means a single request is on the wire at a time, including
    when a 401 retry re-enters from the same task. Vehicle commands wait until
    ``min_interval`` seconds have passed since that same command was last sent.
    Status reads are queued, but they are not held back by the command interval.
    """

    def __init__(
        self,
        min_interval: float = COMMAND_MIN_INTERVAL_SECONDS,
        *,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._min_interval = min_interval
        self._clock = clock or time.monotonic
        self._sleep = sleep or asyncio.sleep
        self._request_lock = asyncio.Lock()
        self._owner: asyncio.Task | None = None
        self._depth = 0
        self._gates_guard = asyncio.Lock()
        self._gates: dict[str, _CommandGate] = {}
        self._last_sent: dict[str, float] = {}

    async def execute(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        command_key: str | None = None,
    ) -> T:
        """Run ``operation`` when the queue and, for commands, the interval allow it."""
        if command_key is None:
            async with self._slot():
                return await operation()

        gate = await self._gate_for(command_key)
        async with gate.lock:
            await self._wait_until_due(command_key)
            async with self._slot():
                # Stamp the moment the command is actually dispatched. The gate
                # stays held until the call finishes, so the next send of this
                # command cannot start until the interval has elapsed.
                self._last_sent[command_key] = self._clock()
                return await operation()

    async def _gate_for(self, command_key: str) -> _CommandGate:
        async with self._gates_guard:
            gate = self._gates.get(command_key)
            if gate is None:
                gate = _CommandGate()
                self._gates[command_key] = gate
            return gate

    def _delay_for(self, command_key: str) -> float:
        last = self._last_sent.get(command_key)
        if last is None:
            return 0.0
        return max(0.0, self._min_interval - (self._clock() - last))

    async def _wait_until_due(self, command_key: str) -> None:
        delay = self._delay_for(command_key)
        if delay <= 0:
            return
        _LOGGER.debug(
            "Queuing command %s for %.1fs (minimum interval %.0fs)",
            command_key,
            delay,
            self._min_interval,
        )
        await self._sleep(delay)

    @asynccontextmanager
    async def _slot(self):
        """Hold the single in-flight request slot.

        The task that already owns the slot may re-enter. Token refresh retries
        call back into the API client from inside the response handler.
        """
        task = asyncio.current_task()
        if task is not None and self._owner is task:
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return

        async with self._request_lock:
            self._owner = task
            self._depth = 1
            try:
                yield
            finally:
                self._owner = None
                self._depth = 0
