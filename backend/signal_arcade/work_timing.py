"""Fixed, worker-local measurements; no I/O, model inputs or shared mutable authority."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any, ParamSpec, TypeVar

WorkDetail = dict[str, list[float]]
WORK_DETAIL: ContextVar[WorkDetail | None] = ContextVar("work_detail", default=None)
WORK_FIELDS = {
    "persist": frozenset(
        {
            "persist_dispatch",
            "persist_worker",
            "persist_resume",
            "persist_serialize",
            "persist_lock",
            "persist_sql",
            "persist_transaction",
        }
    ),
    "broker": frozenset(
        {
            "broker_mark",
            "broker_assess",
            "broker_orders",
            "position_save",
            "order_save",
            "order_lock",
            "order_lookup",
            "fill_save",
            "broker_dispatch",
            "broker_resume",
        }
    ),
    "equity": frozenset(
        {
            "broker_equity",
            "broker_snapshot",
            "setting_read_lock",
            "ledger_read_lock",
            "ledger_read_sql",
            "equity_save",
            "equity_write_lock",
            "equity_commit",
        }
    ),
    "decision": frozenset(
        {
            "decision_serialize",
            "decision_lock",
            "decision_sql",
            "decision_commit",
            "decision_dispatch",
            "decision_resume",
        }
    ),
    "rpc": frozenset(
        {
            "rpc_validate",
            "rpc_observe",
            "checkpoint_persist",
            "checkpoint_govern",
            "checkpoint_prune",
            "rpc_dispatch",
            "rpc_resume",
        }
    ),
    "candidate": frozenset(
        {
            "candidate_reference",
            "candidate_policy",
            "candidate_sizing",
            "candidate_permission",
            "broker_snapshot",
            "setting_read_lock",
            "ledger_read_lock",
            "ledger_read_sql",
            "candidate_dispatch",
            "candidate_worker",
            "candidate_resume",
        }
    ),
    "governance": frozenset(
        {
            "govern_model",
            "govern_tournament",
            "govern_retrain",
            "govern_skills",
            "govern_policy_select",
            "govern_health",
            "govern_join",
            "govern_training_rows",
        }
    ),
}
_NAMES = frozenset().union(*WORK_FIELDS.values())
_Args = ParamSpec("_Args")
_Result = TypeVar("_Result")


def record_work(detail: WorkDetail, name: str, elapsed: float) -> None:
    if name not in _NAMES or not math.isfinite(elapsed) or elapsed < 0:
        return
    values = detail.setdefault(name, [0, 0.0, 0.0])
    values[0] = min(2**53 - 1, values[0] + 1)
    values[1] = min(1e12, values[1] + elapsed)
    values[2] = min(1e12, max(values[2], elapsed))


@contextmanager
def measure_work(name: str) -> Iterator[None]:
    detail = WORK_DETAIL.get()
    if detail is None:
        yield
        return
    started = time.monotonic()
    try:
        yield
    finally:
        record_work(detail, name, max(0.0, time.monotonic() - started))


def timed_work(name: str) -> Callable[[Callable[_Args, _Result]], Callable[_Args, _Result]]:  # noqa: UP047
    """Fast disabled path for existing synchronous operations, including failed calls."""

    def decorate(function: Callable[_Args, _Result]) -> Callable[_Args, _Result]:
        @wraps(function)
        def measured(*args: _Args.args, **kwargs: _Args.kwargs) -> _Result:
            if WORK_DETAIL.get() is None:
                return function(*args, **kwargs)
            with measure_work(name):
                return function(*args, **kwargs)

        return measured

    return decorate


@contextmanager
def measured_context(
    manager: AbstractContextManager[Any], *, enter: str | None = None, exit: str | None = None
) -> Iterator[None]:
    """Time lock acquisition or transaction exit while preserving context semantics."""
    detail = WORK_DETAIL.get()
    if detail is None:
        with manager:
            yield
        return
    started = time.monotonic()
    exiting: float | None = None
    try:
        with manager:
            if enter is not None:
                record_work(detail, enter, max(0.0, time.monotonic() - started))
            try:
                yield
            finally:
                exiting = time.monotonic()
    finally:
        if exit is not None and exiting is not None:
            record_work(detail, exit, max(0.0, time.monotonic() - exiting))
