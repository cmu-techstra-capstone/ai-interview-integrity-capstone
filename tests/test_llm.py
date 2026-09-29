import pytest

from interview_integrity.llm import LLMConfigError, OpenRouterClient


def test_openrouter_requires_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LLMConfigError):
        OpenRouterClient()


def test_openrouter_repr_hides_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret")
    client = OpenRouterClient()
    assert "sk-secret" not in repr(client)
    with pytest.raises(NotImplementedError):
        client.generate("hi", model="any")
