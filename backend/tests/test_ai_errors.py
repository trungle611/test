import json
from types import SimpleNamespace

import httpx
import pytest

from app import ai


class FakeModels:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(next(self.payloads), ensure_ascii=False))


def test_project_fallback_on_quota_error(monkeypatch):
    class QuotaModels:
        def generate_content(self, **kwargs):
            raise ai.errors.ClientError(429, {"error": {"message": "Quota exhausted"}})

    backup = FakeModels([{"ok": True}])
    monkeypatch.setenv("GEMINI_API_KEY", "primary-test-key")
    monkeypatch.setenv("GEMINI_FALLBACK_API_KEY", "backup-test-key")
    monkeypatch.setattr(ai, "client", lambda key=None: SimpleNamespace(models=backup))
    monkeypatch.setattr(ai.time, "sleep", lambda _: None)

    result = ai.generate_json(SimpleNamespace(models=QuotaModels()), "test", {"type": "object"})
    assert result == {"ok": True}
    assert len(backup.calls) == 1


def test_project_fallback_does_not_hide_bad_request(monkeypatch):
    class BadModels:
        def generate_content(self, **kwargs):
            raise ai.errors.ClientError(400, {"error": {"message": "Invalid schema"}})

    monkeypatch.setenv("GEMINI_FALLBACK_API_KEY", "backup-test-key")
    monkeypatch.setattr(ai, "client", lambda key=None: pytest.fail("Must not call backup for 400"))
    with pytest.raises(ai.errors.ClientError):
        ai.generate_json(SimpleNamespace(models=BadModels()), "test", {"type": "object"})


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout("read timeout"),
        httpx.ConnectError("connection failed"),
        ai.errors.ServerError(503, {"error": {"message": "Busy"}}),
    ],
)
def test_transport_and_overload_switch_to_backup(monkeypatch, failure):
    primary_calls = []

    def failed(**kwargs):
        primary_calls.append(kwargs)
        raise failure

    backup = FakeModels([{"ok": True}])
    monkeypatch.setenv("GEMINI_API_KEY", "primary-test")
    monkeypatch.setenv("GEMINI_FALLBACK_API_KEY", "backup-test")
    monkeypatch.setattr(ai, "client", lambda key=None: SimpleNamespace(models=backup))
    monkeypatch.setattr(ai.time, "sleep", lambda _: None)
    result = ai.generate_json(
        SimpleNamespace(models=SimpleNamespace(generate_content=failed)), "test", {"type": "object"}
    )
    assert result == {"ok": True}
    assert len(primary_calls) == 1
    assert len(backup.calls) == 1


def test_network_retry_stops_and_reports_timeout(monkeypatch):
    calls = []

    def failed(**kwargs):
        calls.append(kwargs)
        raise httpx.ReadTimeout("may contain sensitive request details")

    monkeypatch.delenv("GEMINI_FALLBACK_API_KEY", raising=False)
    monkeypatch.setattr(ai.time, "sleep", lambda _: None)
    with pytest.raises(ai.AIServiceError) as caught:
        ai.generate_json(
            SimpleNamespace(models=SimpleNamespace(generate_content=failed)),
            "test",
            {"type": "object"},
        )
    assert caught.value.reason == "timeout"
    assert "sensitive" not in str(caught.value)
    assert len(calls) == ai.MAX_ATTEMPTS


def test_elapsed_budget_prevents_extra_attempt(monkeypatch):
    elapsed = [0.0]
    calls = []

    def failed(**kwargs):
        calls.append(kwargs)
        elapsed[0] = ai.REQUEST_BUDGET_SECONDS + 1
        raise httpx.ReadTimeout("timeout")

    monkeypatch.delenv("GEMINI_FALLBACK_API_KEY", raising=False)
    monkeypatch.setattr(ai.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(ai.time, "sleep", lambda _: None)
    with pytest.raises(ai.AIServiceError, match="phản hồi quá lâu"):
        ai.generate_json(
            SimpleNamespace(models=SimpleNamespace(generate_content=failed)),
            "test",
            {"type": "object"},
        )
    assert len(calls) == 1


def test_language_correction_shares_request_budget(monkeypatch):
    elapsed = [10.0]
    configured_timeouts = []

    def generated(**kwargs):
        configured_timeouts.append(kwargs["config"].http_options.timeout)
        elapsed[0] += 35
        return SimpleNamespace(text="{}")

    monkeypatch.setattr(ai.time, "monotonic", lambda: elapsed[0])
    fake = SimpleNamespace(models=SimpleNamespace(generate_content=generated))

    @ai.bounded_request
    def two_steps():
        ai.generate_json(fake, "scan", {"type": "object"})
        ai.generate_json(fake, "translate", {"type": "object"})

    two_steps()
    assert configured_timeouts == [20000, 10000]
    assert ai._request_deadline.get() is None


@pytest.mark.parametrize("payload", [[], None, True, 5, "không phải object"])
def test_non_object_json_is_rejected_without_provider_details(payload):
    models = FakeModels([payload])
    with pytest.raises(ai.AIResponseError, match="kết quả không hợp lệ"):
        ai.generate_json(SimpleNamespace(models=models), "test", {"type": "object"})


@pytest.mark.parametrize(
    "text",
    ['{"value": NaN}', '{"value": Infinity}', '{"value": -Infinity}', "secret-provider-data"],
)
def test_invalid_json_is_rejected_without_raw_content(text):
    fake = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **kwargs: SimpleNamespace(text=text))
    )
    with pytest.raises(ai.AIResponseError) as caught:
        ai.generate_json(fake, "test", {"type": "object"})
    assert text not in str(caught.value)


def test_missing_or_blank_primary_key_is_a_configuration_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    assert ai.client() is None
    with pytest.raises(ai.AIConfigurationError):
        ai.require_client()


def test_whitespace_does_not_turn_same_key_into_fallback(monkeypatch):
    calls = []

    def failed(**kwargs):
        calls.append(kwargs)
        raise httpx.ReadTimeout("private connection details")

    monkeypatch.setenv("GEMINI_API_KEY", " same-test-key ")
    monkeypatch.setenv("GEMINI_FALLBACK_API_KEY", "same-test-key")
    monkeypatch.setattr(ai, "client", lambda *_: pytest.fail("Duplicate key is not a fallback"))
    monkeypatch.setattr(ai.time, "sleep", lambda _: None)
    with pytest.raises(ai.AIServiceError):
        ai.generate_json(
            SimpleNamespace(models=SimpleNamespace(generate_content=failed)),
            "test",
            {"type": "object"},
        )
    assert len(calls) == ai.MAX_ATTEMPTS
