"""OpenAI-compatible client for a locally hosted model service only."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field

from app.config import Settings


class InferenceError(Exception):
    """Safe inference error; raw upstream details are intentionally discarded."""


class InferenceOverloaded(InferenceError):
    pass


class InferenceUnavailable(InferenceError):
    pass


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1, max_length=20000)


@dataclass(frozen=True)
class GenerationResult:
    content: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None


@dataclass(frozen=True)
class InferenceMetrics:
    in_flight: int
    queue_depth: int
    accepted: int
    rejected: int
    failed: int
    completed: int
    total_latency_seconds: float


class HttpClient(Protocol):
    def post(self, url: str, **kwargs: Any) -> httpx.Response: ...


class BoundedAdmission:
    """Thread-safe process-local capacity control.

    Deploy a shared inference gateway or broker to enforce capacity across multiple
    application workers; this class deliberately makes no cluster-wide claim.
    """

    def __init__(self, max_in_flight: int, max_queue_depth: int, max_wait_seconds: int) -> None:
        self._max_in_flight = max_in_flight
        self._max_queue_depth = max_queue_depth
        self._max_wait_seconds = max_wait_seconds
        self._condition = threading.Condition()
        self._in_flight = self._queued = self._accepted = self._rejected = self._failed = self._completed = 0
        self._total_latency_seconds = 0.0

    def acquire(self) -> None:
        deadline = time.monotonic() + self._max_wait_seconds
        with self._condition:
            if self._in_flight >= self._max_in_flight:
                if self._queued >= self._max_queue_depth:
                    self._rejected += 1
                    raise InferenceOverloaded("Inference queue is full")
                self._queued += 1
                try:
                    while self._in_flight >= self._max_in_flight:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not self._condition.wait(remaining):
                            self._rejected += 1
                            raise InferenceOverloaded("Inference queue wait limit exceeded")
                finally:
                    self._queued -= 1
            self._in_flight += 1
            self._accepted += 1

    def release(self, succeeded: bool, latency_seconds: float) -> None:
        with self._condition:
            self._in_flight -= 1
            self._total_latency_seconds += latency_seconds
            if succeeded:
                self._completed += 1
            else:
                self._failed += 1
            self._condition.notify()

    def snapshot(self) -> InferenceMetrics:
        with self._condition:
            return InferenceMetrics(
                self._in_flight,
                self._queued,
                self._accepted,
                self._rejected,
                self._failed,
                self._completed,
                self._total_latency_seconds,
            )


class LocalLLMClient:
    def __init__(self, settings: Settings, client: HttpClient | None = None) -> None:
        if not settings.llm_enabled or not settings.llm_base_url:
            raise ValueError("Local LLM inference is not configured")
        self._base_url = settings.llm_base_url.rstrip("/")
        self._model = settings.llm_model
        self._max_output_tokens = settings.llm_max_output_tokens
        self._timeout = settings.llm_request_timeout_seconds
        self._client = client or httpx.Client(timeout=self._timeout)
        self._admission = BoundedAdmission(
            settings.llm_max_concurrent_generations,
            settings.llm_max_queue_depth,
            settings.llm_max_queue_wait_seconds,
        )

    def generate(self, messages: list[ChatMessage]) -> GenerationResult:
        self._admission.acquire()
        started = time.monotonic()
        succeeded = False
        try:
            response = self._client.post(
                f"{self._base_url}/chat/completions",
                json={
                    "model": self._model,
                    "messages": [message.model_dump() for message in messages],
                    "max_tokens": self._max_output_tokens,
                    "stream": False,
                },
                timeout=self._timeout,
            )
            if response.status_code in {429, 503}:
                raise InferenceOverloaded("Internal inference service is busy")
            response.raise_for_status()
            payload = response.json()
            choice = payload["choices"][0]
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content:
                raise ValueError("Empty model content")
            usage = payload.get("usage", {})
            succeeded = True
            return GenerationResult(
                content=content,
                model=str(payload.get("model", self._model)),
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
            )
        except InferenceOverloaded:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise InferenceUnavailable("Internal inference service is unavailable") from error
        finally:
            self._admission.release(succeeded, time.monotonic() - started)

    def metrics(self) -> InferenceMetrics:
        return self._admission.snapshot()
