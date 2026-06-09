"""Python callable adapter for in-process application integrations."""

from __future__ import annotations

from importlib import import_module
from typing import Any, Callable

from rag_eval.shared.models import AppAdapterConfig

from .base import AppAdapter


class PythonFunctionAdapter(AppAdapter):
    """Wrap a configured Python callable so it can participate in online evaluation."""

    def __init__(self, config: AppAdapterConfig):
        """Load and cache the configured callable during adapter initialization."""
        self.config = config
        self._callable = self._load_callable(config.callable or "")

    @staticmethod
    def _load_callable(target: str) -> Callable[..., dict[str, Any]]:
        """Resolve a `module:function` target into a callable object."""
        module_name, _, attr_name = target.partition(":")
        if not module_name or not attr_name:
            raise ValueError("Python adapter callable must use module:function syntax.")
        module = import_module(module_name)
        fn = getattr(module, attr_name)
        if not callable(fn):
            raise TypeError(f"Configured callable is not callable: {target}")
        return fn

    async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
        """Invoke the configured callable and enforce the adapter response contract."""
        result = self._callable(question=question, **self.config.static_kwargs, **kwargs)
        if not isinstance(result, dict):
            raise TypeError("Python adapter callable must return a dict.")
        return result
