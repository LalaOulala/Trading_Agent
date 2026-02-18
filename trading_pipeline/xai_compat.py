from __future__ import annotations

from typing import Any


_MODELS_WITHOUT_REASONING_EFFORT: set[str] = set()


def _model_key(model: str) -> str:
    return (model or "").strip().lower()


def _error_text(exc: Exception) -> str:
    parts: list[str] = []
    base = str(exc or "").strip()
    if base:
        parts.append(base)

    details_attr = getattr(exc, "details", None)
    details = ""
    if callable(details_attr):
        try:
            details = str(details_attr() or "").strip()
        except Exception:
            details = ""

    if details and details not in parts:
        parts.append(details)
    return " | ".join(parts)


def _is_reasoning_effort_unsupported_error(exc: Exception) -> bool:
    message = _error_text(exc)
    lowered = message.lower()
    if "does not support parameter" not in lowered and "unsupported parameter" not in lowered:
        return False
    if "reasoningeffort" in lowered or "reasoning effort" in lowered or "reasoning_effort" in lowered:
        return True
    return "does not support reasoning" in lowered or "unsupported reasoning" in lowered


def register_model_without_reasoning_effort(*, model: str, exc: Exception) -> bool:
    if not _is_reasoning_effort_unsupported_error(exc):
        return False
    key = _model_key(model)
    if key:
        _MODELS_WITHOUT_REASONING_EFFORT.add(key)
    return True


def format_reasoning_compat_error(*, model: str, exc: Exception) -> str:
    if _is_reasoning_effort_unsupported_error(exc):
        model_name = (model or "").strip()
        if model_name:
            return f"Incompatibilité du modèle {model_name} en mode reasoning."
        return "Incompatibilité du modèle en mode reasoning."
    return f"{type(exc).__name__}: {exc}"


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
            if not register_model_without_reasoning_effort(model=model, exc=exc):
                raise

    return client.chat.create(model=model, **base_kwargs)
