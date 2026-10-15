"""Capacity and Load Testing Benchmark Tool for Enterprise Intranet Assistant.

Measures bounded admission concurrency, queue latency, throughput, and rejection behavior
under peak concurrency to establish baseline hardware and process capacity.
"""

from __future__ import annotations

import argparse
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import httpx

from app.config import Settings
from app.llm.service import (
    ChatMessage,
    InferenceOverloaded,
    LocalLLMClient,
)


@dataclass
class BenchmarkRunResult:
    total_requests: int
    concurrency: int
    completed: int
    rejected: int
    failed: int
    duration_seconds: float
    throughput_rps: float
    latencies: list[float]
    p50_latency: float
    p95_latency: float
    p99_latency: float


class SimulatedInferenceClient:
    """Mock client simulating local GPU inference latency without GPU hardware."""

    def __init__(self, simulated_latency: float = 0.25) -> None:
        self.simulated_latency = simulated_latency

    def post(self, url: str, **kwargs) -> httpx.Response:
        time.sleep(self.simulated_latency)
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "model": "benchmark-model",
                "choices": [{"message": {"content": "Simulated assistant answer."}}],
                "usage": {"prompt_tokens": 30, "completion_tokens": 15},
            },
        )


def run_synthetic_benchmark(
    concurrency: int = 10,
    total_requests: int = 50,
    max_concurrent_generations: int = 4,
    max_queue_depth: int = 10,
    max_queue_wait_seconds: int = 2,
    simulated_gpu_latency: float = 0.1,
) -> BenchmarkRunResult:
    """Run an in-process load test against BoundedAdmission and LocalLLMClient."""
    settings = Settings(
        _env_file=None,
        app_env="test",
        secret_key="b" * 32,
        dev_auth_signing_key="k" * 32,
        llm_enabled=True,
        llm_base_url="http://llm.internal:8000/v1",
        llm_allowed_hosts=["llm.internal"],
        llm_max_concurrent_generations=max_concurrent_generations,
        llm_max_queue_depth=max_queue_depth,
        llm_max_queue_wait_seconds=max_queue_wait_seconds,
    )

    mock_http = SimulatedInferenceClient(simulated_latency=simulated_gpu_latency)
    client = LocalLLMClient(settings, mock_http)

    latencies: list[float] = []
    completed = rejected = failed = 0

    def single_worker(req_id: int) -> tuple[bool, str, float]:
        start = time.perf_counter()
        try:
            client.generate([ChatMessage(role="user", content=f"Benchmark query {req_id}")])
            dur = time.perf_counter() - start
            return True, "completed", dur
        except InferenceOverloaded:
            dur = time.perf_counter() - start
            return False, "rejected", dur
        except Exception:
            dur = time.perf_counter() - start
            return False, "failed", dur

    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(single_worker, i) for i in range(total_requests)]
        for f in as_completed(futures):
            ok, outcome, dur = f.result()
            if outcome == "completed":
                completed += 1
                latencies.append(dur)
            elif outcome == "rejected":
                rejected += 1
            else:
                failed += 1

    total_duration = time.perf_counter() - wall_start
    throughput = completed / total_duration if total_duration > 0 else 0.0

    p50 = statistics.median(latencies) if latencies else 0.0
    p95 = (
        statistics.quantiles(latencies, n=20)[18]
        if len(latencies) >= 20
        else (max(latencies) if latencies else 0.0)
    )
    p99 = (
        statistics.quantiles(latencies, n=100)[98]
        if len(latencies) >= 100
        else (max(latencies) if latencies else 0.0)
    )

    return BenchmarkRunResult(
        total_requests=total_requests,
        concurrency=concurrency,
        completed=completed,
        rejected=rejected,
        failed=failed,
        duration_seconds=total_duration,
        throughput_rps=throughput,
        latencies=latencies,
        p50_latency=p50,
        p95_latency=p95,
        p99_latency=p99,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capacity benchmark harness")
    parser.add_argument("--concurrency", type=int, default=8, help="Number of concurrent workers")
    parser.add_argument("--requests", type=int, default=40, help="Total requests to dispatch")
    parser.add_argument("--gpu-latency", type=float, default=0.08, help="Simulated inference delay in seconds")
    args = parser.parse_args()

    print(f"Executing capacity benchmark (concurrency={args.concurrency}, requests={args.requests})...")
    res = run_synthetic_benchmark(
        concurrency=args.concurrency,
        total_requests=args.requests,
        simulated_gpu_latency=args.gpu_latency,
    )

    print("\n=== Benchmark Results ===")
    print(f"Total Requests:       {res.total_requests}")
    print(f"Completed (200 OK):   {res.completed}")
    print(f"Rejected (429/Busy):  {res.rejected}")
    print(f"Failed (Errors):      {res.failed}")
    print(f"Total Duration:       {res.duration_seconds:.3f} s")
    print(f"Throughput:           {res.throughput_rps:.2f} req/s")
    print(f"Latency P50:          {res.p50_latency * 1000:.1f} ms")
    print(f"Latency P95:          {res.p95_latency * 1000:.1f} ms")
    print(f"Latency P99:          {res.p99_latency * 1000:.1f} ms")
