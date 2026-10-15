import httpx
import pytest

from app.config import Settings
from app.llm.service import BoundedAdmission, ChatMessage, InferenceOverloaded, LocalLLMClient


def settings(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "secret_key": "a" * 32,
        "dev_auth_signing_key": "b" * 32,
        "llm_enabled": True,
        "llm_base_url": "http://llm.internal:8000/v1",
        "llm_allowed_hosts": ["llm.internal"],
        "llm_model": "reviewed-local-model",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class FakeClient:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        request = httpx.Request("POST", url)
        return httpx.Response(
            self.status_code,
            request=request,
            json={"model": "reviewed-local-model", "choices": [{"message": {"content": "Answer"}}], "usage": {"prompt_tokens": 4, "completion_tokens": 1}},
        )


def test_client_uses_internal_openai_compatible_endpoint_and_configured_model():
    fake = FakeClient()
    client = LocalLLMClient(settings(), fake)
    result = client.generate([ChatMessage(role="user", content="Hello")])
    assert result.content == "Answer"
    assert fake.calls[0][0] == "http://llm.internal:8000/v1/chat/completions"
    assert fake.calls[0][1]["json"]["model"] == "reviewed-local-model"
    assert client.metrics().completed == 1


def test_busy_upstream_is_reported_without_upstream_detail():
    with pytest.raises(InferenceOverloaded):
        LocalLLMClient(settings(), FakeClient(503)).generate([ChatMessage(role="user", content="Hello")])


def test_queue_capacity_rejects_before_unbounded_waiting():
    admission = BoundedAdmission(max_in_flight=1, max_queue_depth=0, max_wait_seconds=0)
    admission.acquire()
    with pytest.raises(InferenceOverloaded):
        admission.acquire()
    admission.release(True, 0.1)
    assert admission.snapshot().rejected == 1


def test_llm_configuration_requires_internal_endpoint_when_enabled():
    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        settings(llm_base_url=None)


def test_llm_configuration_rejects_unapproved_host():
    with pytest.raises(ValueError, match="LLM_ALLOWED_HOSTS"):
        settings(llm_allowed_hosts=[])
