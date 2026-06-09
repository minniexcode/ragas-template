"""Async helpers for executing bounded concurrent workloads."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


async def gather_with_limit(
    factories: list[Callable[[], Awaitable[T]]],
    limit: int,
) -> list[T]:
    """Run async factory callables with a maximum concurrency limit."""
    semaphore = asyncio.Semaphore(max(1, limit))

    async def guarded(factory: Callable[[], Awaitable[T]]) -> T:
        """Wrap one factory invocation with semaphore-based throttling."""
        async with semaphore:
            return await factory()

    return await asyncio.gather(*(guarded(factory) for factory in factories))
