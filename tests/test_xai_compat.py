from __future__ import annotations

import unittest

from trading_pipeline import xai_compat


class _FakeChatApi:
    def __init__(self, *, unsupported_models: set[str] | None = None, force_error: str | None = None) -> None:
        self.unsupported_models = set(unsupported_models or set())
        self.force_error = force_error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        if self.force_error:
            raise RuntimeError(self.force_error)

        model = str(kwargs.get("model") or "")
        has_reasoning = "reasoning_effort" in kwargs
        if has_reasoning and model in self.unsupported_models:
            raise RuntimeError(
                f"Model {model} does not support parameter reasoningEffort."
            )
        return {"ok": True, "model": model, "kwargs": kwargs}


class _FakeClient:
    def __init__(self, chat_api: _FakeChatApi) -> None:
        self.chat = chat_api


class XaiCompatTests(unittest.TestCase):
    def setUp(self) -> None:
        xai_compat._MODELS_WITHOUT_REASONING_EFFORT.clear()

    def test_create_chat_uses_reasoning_effort_when_supported(self) -> None:
        chat_api = _FakeChatApi()
        client = _FakeClient(chat_api)

        result = xai_compat.create_chat_with_reasoning_fallback(
            client=client,
            model="grok-supported",
            reasoning_effort="high",
            max_tokens=123,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(len(chat_api.calls), 1)
        self.assertEqual(chat_api.calls[0]["reasoning_effort"], "high")
        self.assertEqual(chat_api.calls[0]["max_tokens"], 123)

    def test_create_chat_retries_without_reasoning_effort_and_caches_model(self) -> None:
        chat_api = _FakeChatApi(unsupported_models={"grok-unsupported"})
        client = _FakeClient(chat_api)

        first = xai_compat.create_chat_with_reasoning_fallback(
            client=client,
            model="grok-unsupported",
            reasoning_effort="high",
            max_tokens=10,
        )
        second = xai_compat.create_chat_with_reasoning_fallback(
            client=client,
            model="grok-unsupported",
            reasoning_effort="high",
            max_tokens=20,
        )

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(len(chat_api.calls), 3)
        self.assertIn("reasoning_effort", chat_api.calls[0])
        self.assertNotIn("reasoning_effort", chat_api.calls[1])
        self.assertNotIn("reasoning_effort", chat_api.calls[2])
        self.assertEqual(chat_api.calls[1]["max_tokens"], 10)
        self.assertEqual(chat_api.calls[2]["max_tokens"], 20)

    def test_create_chat_does_not_swallow_unrelated_error(self) -> None:
        chat_api = _FakeChatApi(force_error="network down")
        client = _FakeClient(chat_api)

        with self.assertRaisesRegex(RuntimeError, "network down"):
            xai_compat.create_chat_with_reasoning_fallback(
                client=client,
                model="grok-any",
                reasoning_effort="high",
                max_tokens=99,
            )

        self.assertEqual(len(chat_api.calls), 1)


if __name__ == "__main__":
    unittest.main()
