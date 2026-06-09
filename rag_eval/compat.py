"""Compatibility helpers for optional third-party import paths."""

from __future__ import annotations

import sys
import types


def ensure_ragas_import_compat() -> None:
    """Patch optional langchain module paths that ragas imports eagerly.

    The local environment ships a `langchain_community` build that still exposes
    `langchain_community.llms.vertexai` but no longer provides
    `langchain_community.chat_models.vertexai`. Ragas imports the chat module at
    import time even when only OpenAI is used. Inject a minimal module so ragas
    can import without mutating site-packages.
    """

    module_name = "langchain_community.chat_models.vertexai"
    if module_name in sys.modules:
        return

    try:
        import langchain_community.chat_models.vertexai  # type: ignore  # noqa: F401

        return
    except ModuleNotFoundError:
        pass

    # Inject a minimal shim so ragas can import successfully in stripped builds.
    shim = types.ModuleType(module_name)

    class ChatVertexAI:  # pragma: no cover - only used for import compatibility
        """Compatibility shim for environments that do not ship ChatVertexAI."""

        pass

    shim.ChatVertexAI = ChatVertexAI
    sys.modules[module_name] = shim
