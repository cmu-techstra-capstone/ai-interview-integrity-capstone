import io
import json
import urllib.error

import pytest

from interview_integrity.llm import (
    BudgetExceeded, CachedClient, LLMClient, LLMConfigError, LLMResponse, OpenRouterClient, OpenRouterError,
    load_dotenv,
)


class FakeHTTP:
    """Stands in for urllib.request.urlopen; replays queued responses or errors."""

    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return io.BytesIO(json.dumps(r).encode())  # supports `with` and .read()


def http_error(code):
    return urllib.error.HTTPError("u", code, "err", {}, io.BytesIO(b'{"error":"x"}'))


def ok(text, model="m"):
    return {"id": "1", "model": model, "choices": [{"message": {"content": text}}], "usage": {"total_tokens": 3}}


def test_openrouter_requires_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LLMConfigError):
        OpenRouterClient()


def test_openrouter_repr_and_errors_hide_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret")
    http = FakeHTTP(http_error(401))
    client = OpenRouterClient(urlopen=http, sleep=lambda s: None)
    assert "sk-secret" not in repr(client)
    with pytest.raises(OpenRouterError) as e:
        client.generate("hi", model="any")
    assert "sk-secret" not in str(e.value)


def test_generate_sends_messages_and_options():
    http = FakeHTTP(ok("hello", "openai/x"))
    client = OpenRouterClient(api_key="k", urlopen=http, sleep=lambda s: None)
    resp = client.generate("hi", model="openai/x", system="sys", temperature=0.1, max_tokens=5,
                           json_mode=True, seed=3)
    assert resp.text == "hello" and resp.model == "openai/x" and resp.raw["usage"]["total_tokens"] == 3
    body = json.loads(http.requests[0].data)
    assert body["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    assert body["response_format"] == {"type": "json_object"} and body["seed"] == 3 and body["max_tokens"] == 5
    assert http.requests[0].get_header("Authorization") == "Bearer k"


def test_retries_on_rate_limit_then_succeeds():
    sleeps = []
    http = FakeHTTP(http_error(429), urllib.error.URLError("down"), ok("fine"))
    client = OpenRouterClient(api_key="k", urlopen=http, sleep=sleeps.append)
    assert client.generate("hi", model="m").text == "fine"
    assert sleeps == [1.0, 2.0]


def test_gives_up_after_max_retries():
    http = FakeHTTP(*[http_error(503)] * 3)
    client = OpenRouterClient(api_key="k", urlopen=http, sleep=lambda s: None, max_retries=2)
    with pytest.raises(OpenRouterError, match="gave up"):
        client.generate("hi", model="m")


def test_error_payload_and_list_models():
    client = OpenRouterClient(api_key="k", urlopen=FakeHTTP({"error": {"message": "no"}}), sleep=lambda s: None)
    with pytest.raises(OpenRouterError):
        client.generate("hi", model="m")
    client = OpenRouterClient(api_key="k", urlopen=FakeHTTP({"data": [{"id": "b/2"}, {"id": "a/1"}]}))
    assert client.list_models() == ["a/1", "b/2"]


def test_load_dotenv_does_not_override(tmp_path, monkeypatch):
    monkeypatch.setenv("EXISTING", "keep")
    monkeypatch.delenv("NEW_KEY", raising=False)
    f = tmp_path / ".env"
    f.write_text("# c\nNEW_KEY='v1'\nEXISTING=other\nEMPTY=\n")
    assert load_dotenv(f) and not load_dotenv(tmp_path / "missing")
    import os
    assert os.environ["NEW_KEY"] == "v1" and os.environ["EXISTING"] == "keep"


class Counting(LLMClient):
    provider = "fake"

    def __init__(self):
        self.n = 0

    def generate(self, prompt, *, model, system=None, temperature=0.7, max_tokens=None, **kw):
        self.n += 1
        return LLMResponse(f"{prompt}-{self.n}", model, self.provider, {"usage": {"t": 1}})


def test_cache_reuses_calls_across_instances_and_enforces_budget(tmp_path):
    inner = Counting()
    c = CachedClient(inner, tmp_path / "c.jsonl", max_calls=2)
    assert c.generate("a", model="m").text == "a-1"
    assert c.generate("a", model="m").text == "a-1" and c.hits == 1
    assert c.generate("a", model="m", seed=1).text == "a-2"  # extra options are part of the key
    with pytest.raises(BudgetExceeded):
        c.generate("b", model="m")
    c2 = CachedClient(inner, tmp_path / "c.jsonl", max_calls=0)
    assert c2.generate("a", model="m", seed=1).text == "a-2" and inner.n == 2
