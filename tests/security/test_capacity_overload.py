"""Security Verification: Capacity Overload and DoS Mitigations."""

import pytest

from app.llm.service import BoundedAdmission, InferenceOverloaded


def test_bounded_admission_queue_saturation():
    """Verify that requests exceeding queue depth fail fast with InferenceOverloaded."""
    admission = BoundedAdmission(max_in_flight=1, max_queue_depth=1, max_wait_seconds=1)

    # First request acquires the in-flight slot
    admission.acquire()
    assert admission.snapshot().in_flight == 1

    # Second request enters queue (queue depth becomes 1)
    # To test immediate queue rejection, a third request when queue is full:
    admission._queued = 1  # simulate queued request
    with pytest.raises(InferenceOverloaded, match="queue is full"):
        admission.acquire()

    # Releasing restores state
    admission.release(succeeded=True, latency_seconds=0.05)
    assert admission.snapshot().in_flight == 0
    assert admission.snapshot().completed == 1


def test_bounded_admission_wait_timeout():
    """Verify that queued requests wait at most max_wait_seconds before timing out."""
    admission = BoundedAdmission(max_in_flight=1, max_queue_depth=5, max_wait_seconds=0)

    # Fill in-flight slot
    admission.acquire()

    # With max_wait_seconds=0, subsequent request cannot wait and must immediately be rejected
    with pytest.raises(InferenceOverloaded, match="wait limit exceeded"):
        admission.acquire()

    assert admission.snapshot().rejected == 1
    admission.release(succeeded=True, latency_seconds=0.01)
