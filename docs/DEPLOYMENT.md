# Deployment and Operations Guide

## Overview

Phase 8 defines the production deployment topology for the Enterprise Intranet Assistant using Docker Compose or Podman. The deployment strictly enforces:
1. **Network Isolation**: Outbound blocking on internal and backend networks to guarantee no data exfiltration or external AI calls.
2. **Reverse Proxy Edge Controls**: Internal TLS termination, rate-limiting, and security headers via Nginx.
3. **Least-Privilege Execution**: Non-root container execution (`appuser`, UID 10001) with unprivileged read-only document mounts.
4. **Offline Capability**: Pre-staged wheels and models, eliminating runtime internet downloads.

## Topology Diagram

```text
[ Employee Browser ]
        │ HTTPS (Port 443)
        ▼
[ intranet-reverse-proxy (Nginx) ]
        │ TLS Termination, Rate Limit (10r/s), Security Headers
        │ Network: internal_app (internal: true)
        ▼
[ intranet-assistant-app (FastAPI) ]
        │ Token Auth, ACL Filtering, LangGraph Orchestration
        │ Network: isolated_backend (internal: true)
        ▼
[ intranet-llm-service (vLLM / llama.cpp) ]
  Local weights mounted read-only at /models
```

## Network Isolation & Outbound Blocking

The Compose specification declares:
```yaml
networks:
  internal_app:
    driver: bridge
    internal: true
  isolated_backend:
    driver: bridge
    internal: true
```

### Outbound Blocking Validation
When `internal: true` is set on Docker/Podman networks:
- No default gateway to the public internet is attached to the container interfaces.
- Attempts to reach public IPs or external domain names (e.g. `api.openai.com`, `pypi.org`) fail immediately with `Network unreachable` or name resolution failure.
- This provides network-level proof that no prompts, embeddings, or corporate documents can leave the intranet perimeter.

## Offline Staging Procedure

In compliance with enterprise air-gap policies, runtime internet access is prohibited:

1. **Stage Dependency Wheels**:
   Execute `./deploy/offline-staging.sh` (or `offline-staging.ps1` on Windows) on an approved build workstation with access to the internal package mirror.
   This places all pinned wheels into `deploy/wheelhouse/`.

2. **Stage Approved Model Weights**:
   Place the license-reviewed, scanned model weights (e.g. Qwen or Llama weights in GGUF or Safetensors format) into `deploy/models/approved-model`.

3. **Deploy with Compose/Podman**:
   ```bash
   cd deploy
   docker compose up -d --build
   ```

## Production Configuration Checklist

Before initiating production:
- [ ] Place valid internal CA-signed TLS certificates in `deploy/certs/server.crt` and `deploy/certs/server.key`.
- [ ] Set `SECRET_KEY` in `.env` to a high-entropy secret (>= 32 characters).
- [ ] Configure `OIDC_ISSUER`, `OIDC_JWKS_URL`, and `AUTH_AUDIENCE` pointing to the corporate Identity Provider.
- [ ] Populate `ROLE_PERMISSION_MAP` with server-side role assignments.
- [ ] Confirm `DOCUMENT_ROOTS` point to authorized directories containing `.acl.json` files.
- [ ] Verify `LLM_ALLOWED_HOSTS` includes only `llm-service`.
