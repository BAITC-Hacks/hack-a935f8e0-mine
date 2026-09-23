import asyncio
import json

import httpx2
import pytest
from openai import AsyncOpenAI as RealAsyncOpenAI

import src.ai as ai
from src.ai import Provider


def install_transport(monkeypatch, handler):
    def client(**kwargs):
        # Real OpenAI serialization/parsing over an isolated in-memory transport.
        kwargs["max_retries"] = 0
        return RealAsyncOpenAI(**kwargs, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))
    monkeypatch.setattr(ai, "AsyncOpenAI", client)


def completion(text="Проверенный ответ", reason="stop"):
    return {"id": "test", "object": "chat.completion", "created": 0, "model": "test",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": reason}]}


def test_real_sdk_payloads_and_concurrent_requests(monkeypatch):
    seen = []

    async def run():
        both_started = asyncio.Event()

        async def handler(request):
            seen.append((str(request.url), json.loads(request.content)))
            if len(seen) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=2)
            return httpx2.Response(200, json=completion())

        install_transport(monkeypatch, handler)
        return await ai.generate_reports([
            Provider("OpenAI", ai.OPENAI_MODEL, "test-key"),
            Provider("NVIDIA", ai.NVIDIA_MODEL, "test-key", ai.NVIDIA_BASE_URL),
        ], {"score": 56.5})

    result = asyncio.run(run())
    assert all(r.ok for r in result.values())
    requests = {body["model"]: (url, body) for url, body in seen}
    url, body = requests[ai.OPENAI_MODEL]
    assert url == "https://api.openai.com/v1/chat/completions"
    assert body["max_completion_tokens"] == 1800
    assert body["store"] is False
    url, body = requests[ai.NVIDIA_MODEL]
    assert url == ai.NVIDIA_BASE_URL + "/chat/completions"
    assert body["chat_template_kwargs"]["enable_thinking"] is False
    assert body["max_tokens"] == 1800


@pytest.mark.parametrize("status,word", [(401, "Ключ"), (403, "Ключ"), (429, "лимит"),
                                        (404, "Модель"), (500, "сервиса"), (400, "HTTP 400")])
def test_safe_api_errors(monkeypatch, status, word):
    def handler(request):
        return httpx2.Response(status, json={"error": {"message": "secret-key-must-not-leak", "type": "test"}})
    install_transport(monkeypatch, handler)
    result = asyncio.run(ai.assess(Provider("OpenAI", ai.OPENAI_MODEL, "private-key"), {}))
    assert not result.ok
    assert word in result.error
    assert "secret-key" not in result.error
    assert "private-key" not in repr(result)


def test_timeout_does_not_cancel_other_provider(monkeypatch):
    monkeypatch.setattr(ai, "DEADLINE_SECONDS", .1)

    async def request(provider, payload):
        if provider.name == "NVIDIA":
            await asyncio.sleep(10)
        return "Отчет урбаниста", ""

    monkeypatch.setattr(ai, "_request", request)
    result = asyncio.run(ai.generate_reports([
        Provider("OpenAI", ai.OPENAI_MODEL, "test"), Provider("NVIDIA", ai.NVIDIA_MODEL, "test"),
    ], {}))
    assert result["OpenAI"].ok
    assert "вовремя" in result["NVIDIA"].error


def test_missing_keys_never_make_network_requests(monkeypatch):
    def fail(**kwargs):
        pytest.fail("Network client must not be created without a key")
    monkeypatch.setattr(ai, "AsyncOpenAI", fail)
    assert not asyncio.run(ai.assess(Provider("OpenAI", ai.OPENAI_MODEL, ""), {})).ok


@pytest.mark.parametrize("body", [{"choices": []}, completion(""), completion(None)])
def test_empty_response(monkeypatch, body):
    install_transport(monkeypatch, lambda request: httpx2.Response(200, json=body))
    result = asyncio.run(ai.assess(Provider("OpenAI", ai.OPENAI_MODEL, "test"), {}))
    assert not result.ok
    assert "некорректный" in result.error


def test_truncation_is_visible(monkeypatch):
    install_transport(monkeypatch, lambda request: httpx2.Response(200, json=completion("Часть отчета", "length")))
    result = asyncio.run(ai.assess(Provider("OpenAI", ai.OPENAI_MODEL, "test"), {}))
    assert result.ok
    assert result.warning


@pytest.mark.parametrize("error,word", [(httpx2.ConnectError, "подключиться"), (httpx2.ReadTimeout, "вовремя")])
def test_network_errors_are_actionable(monkeypatch, error, word):
    def handler(request):
        raise error("private detail", request=request)
    install_transport(monkeypatch, handler)
    result = asyncio.run(ai.assess(Provider("OpenAI", ai.OPENAI_MODEL, "test"), {}))
    assert not result.ok
    assert word in result.error
    assert "private" not in result.error


def test_settings_refresh_and_no_secret_repr(monkeypatch, tmp_path):
    monkeypatch.setattr(ai, "ROOT", tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=file-secret\nNVIDIA_API_KEY=nv-secret\n", encoding="utf-8")
    providers = ai.load_providers()
    assert providers[0].api_key == "file-secret"
    assert "secret" not in repr(providers)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=updated-secret\n", encoding="utf-8")
    assert ai.load_providers()[0].api_key == "updated-secret"
    monkeypatch.setenv("OPENAI_API_KEY", "env-secret")
    assert ai.load_providers()[0].api_key == "env-secret"
