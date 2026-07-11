from app.core.config import settings
from app.services import ai_service


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "content": [{"type": "text", "text": "{}"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }


class _Client:
    calls = []

    def __init__(self, timeout):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, headers, json):
        self.calls.append(json)
        return _Response()


def test_claude_sonnet_5_omits_deprecated_temperature(monkeypatch):
    _Client.calls = []
    monkeypatch.setattr(settings, "anthropic_model", "claude-sonnet-5")
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(ai_service.httpx, "Client", _Client)

    ai_service._call_anthropic_messages([{"role": "user", "content": "hello"}])

    assert "temperature" not in _Client.calls[0]


def test_other_anthropic_models_keep_existing_temperature(monkeypatch):
    _Client.calls = []
    monkeypatch.setattr(settings, "anthropic_model", "claude-3-5-sonnet-latest")
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(ai_service.httpx, "Client", _Client)

    ai_service._call_anthropic_messages([{"role": "user", "content": "hello"}])

    assert _Client.calls[0]["temperature"] == 0
