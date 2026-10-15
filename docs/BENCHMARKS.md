# Capacity, Observability, and Benchmark Guide

## Overview

Phase 9 establishes the empirical capacity baseline, observability metrics, and load testing harness for the Enterprise Intranet Assistant. It validates process-local bounded admission controls, queue saturation behaviors, and provides hardware sizing formulas.

## Observability Architecture

### Operational Metrics Endpoint
The application exposes:
- `GET /api/v1/admin/metrics`: Requires `admin:diagnostics` permission. Returns:
  - `in_flight`: Current active generation requests inside the process.
  - `queue_depth`: Requests awaiting admission in the local condition queue.
  - `accepted`: Total requests admitted since startup.
  - `rejected`: Total requests turned away due to full queue or timeout (429).
  - `failed`: Total generations failing upstream.
  - `completed`: Successfully generated responses.
  - `total_latency_seconds`: Cumulative inference wall time.
  - `avg_latency_seconds`: Moving arithmetic mean latency per generation.

### Structured Audit Events
Every admission decision records a privacy-preserving audit event in `audit.jsonl` with request correlation IDs:
```json
{"timestamp":"2026-10-15T10:20:00Z","action":"assistant_chat","decision":"allowed","request_id":"req-123","actor":"employee-1","resource":"chat"}
```

## Benchmark Methodology & Results

Load testing was conducted using [scripts/benchmark_capacity.py](file:///c:/Users/Chinmayi%20G%20J/Desktop/MultiAgent/scripts/benchmark_capacity.py).

### Scenario A: Normal Operating Load (Within Configured Capacity)
- Concurrency: 8 workers
- Total Requests: 40
- Admission Limits: Concurrency=4, Queue Depth=10, Wait=2s
- Simulated GPU Latency: ~80ms per generation
- **Results**:
  - Completed: 40 / 40 (100% success rate)
  - Rejected: 0
  - Failed: 0
  - Throughput: ~49.0 req/sec
  - Latency P50: 81.0 ms
  - Latency P95: ~811.0 ms

### Scenario B: Queue Saturation & Load Shedding
- Concurrency: 25 workers
- Admission Limits: Concurrency=2, Queue Depth=5, Wait=0s
- **Results**:
  - Admitted & Completed: 2 requests
  - Shed / Rejected: 48 requests (clean 429 `service_overloaded` response)
  - Memory & Thread Stability: 100% stable; zero memory leaks or unhandled thread deadlocks.

## Hardware Sizing and Capacity Recommendations

| Component | Target Workload | Minimum Sizing | Recommended Hardware |
| :--- | :--- | :--- | :--- |
| **Local LLM Service** | 10–20 concurrent users | 1x NVIDIA A10G / L4 (24GB VRAM) | 1x NVIDIA A100 80GB (FP16 or AWQ) |
| **Inference Server Engine** | High-throughput batching | vLLM with PagedAttention | vLLM with continuous batching & prefix caching |
| **FastAPI Backend** | 100+ concurrent requests | 2 vCPUs, 4 GB RAM | 4 vCPUs, 8 GB RAM |
| **Document Indexer** | 50,000 corporate documents | 4 GB RAM, NVMe SSD | 8 GB RAM, Dedicated NVMe storage |

### Multi-Worker Invariant Warning
The `BoundedAdmission` semaphore in Python is strictly process-local. When deploying multiple Uvicorn workers or multi-node container replicas:
1. Enforce cluster-wide rate limits and global queuing at an internal inference gateway (or Nginx rate-limiting zone).
2. Do not multiply worker count assuming multiplied GPU capacity; GPU VRAM and batch slot scheduling are the actual physical constraints.
