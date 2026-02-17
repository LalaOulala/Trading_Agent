from __future__ import annotations

from typing import Any


_MODELS_WITHOUT_REASONING_EFFORT: set[str] = set()


def _model_key(model: str) -> str:
    return (model or "").strip().lower()


def _is_reasoning_effort_unsupported_error(exc: Exception) -> bool:
    message = str(exc or "")
    lowered = message.lower()
    return "reasoningeffort" in lowered and "does not support parameter" in lowered


def create_chat_with_reasoning_fallback(
    *,
    client: Any,
    model: str,
    reasoning_effort: str | None,
    **kwargs: Any,
) -> Any:
    """
    Crée un chat xAI en appliquant un fallback automatique si le modèle
    ne supporte pas le paramètre `reasoning_effort`.
    """
    key = _model_key(model)
    base_kwargs = dict(kwargs)

    should_try_with_reasoning = bool(reasoning_effort) and key not in _MODELS_WITHOUT_REASONING_EFFORT
    if should_try_with_reasoning:
        try:
            return client.chat.create(
                model=model,
                reasoning_effort=reasoning_effort,
                **base_kwargs,
            )
        except Exception as exc:
            if not _is_reasoning_effort_unsupported_error(exc):
                raise
            _MODELS_WITHOUT_REASONING_EFFORT.add(key)

    return client.chat.create(model=model, **base_kwargs)
