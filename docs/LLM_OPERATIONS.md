# Local LLM Operations

## Serving boundary

The application calls only `LLM_BASE_URL`, using an OpenAI-compatible `POST /chat/completions` contract. Its hostname must appear in `LLM_ALLOWED_HOSTS`; it contains no OpenAI, Gemini, Anthropic, or other external inference integration. `LLM_INTERNAL_ONLY` cannot be disabled by configuration.

Use vLLM on a supported internal GPU for the primary deployment and expose it only on the organization network. For constrained hardware, llama.cpp with a vetted, locally staged quantized model may provide a suitable alternative. Model files, tokenizers, and embedding assets must be license-reviewed, scanned, and transferred to internal storage before deployment; startup never downloads them.

`LLM_MODEL` is configuration, not application logic. `qwen3-4b-pending-license-review` is only a candidate label. Before use, record the exact revision, license, quantization, tokenizer compatibility, hardware results, and internal approval.

## Capacity controls

The client enforces configured maximum output tokens, request timeout, concurrent generations, queue depth, and maximum queue wait. It turns full/expired queues and upstream `429`/`503` responses into a safe overload result.

These controls are process-local. For multiple FastAPI workers or replicas, enforce global admission, queueing, cancellation, and rate limits at an internal inference gateway or shared broker. Do not treat a Python semaphore as cluster-wide capacity. Benchmark actual concurrent generations separately from connected users before promising capacity.

Metrics include in-flight requests, local queue depth, accepted/rejected/failed/completed requests, and aggregate latency. vLLM or the selected server must supply GPU, VRAM, token-throughput, and batch scheduling metrics for operational monitoring.
