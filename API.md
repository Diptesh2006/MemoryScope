# MemoryScope developer beta API

OpenAPI schemas: `http://127.0.0.1:8000/docs`. Loopback-only, single-user deployment.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Process health, not upstream readiness |
| `GET /api/beta/settings` | Judge configured flag, model, pipeline, limits, allowed origins; no keys |
| `POST /api/beta/runs` | Validate and enqueue real evaluation; HTTP 202 |
| `GET /api/beta/runs` | Latest 100 run summaries |
| `GET /api/beta/runs/{id}` | Status and full evidence |
| `GET /api/beta/runs/{id}/report` | Portable JSON report |
| `POST /api/beta/runs/{id}/cancel` | Cancel remaining work, not already-billed calls |
| `GET /api/beta/compare/{before}/{after}` | Per-case comparison for completed identical suites |

Start request:

```json
{
  "agent_name": "My support agent",
  "endpoint": "http://127.0.0.1:4175/api/chat",
  "auth_env": null,
  "send_to_judge": true,
  "cases": [{
    "name": "Refund",
    "question": "What is the refund window?",
    "reference": "Refunds within 14 days.",
    "expected": "State 14 days.",
    "required_literals": ["14"],
    "forbidden_literals": [],
    "require_citations": false
  }]
}
```

Use your actual policy, not the illustrative reference above.
HTTP 422: invalid schema, unapproved endpoint, missing consent, incompatible comparison.
HTTP 503: judge not configured. HTTP 409: another active run or cancellation of terminal run.
Run statuses: pending, running, completed, failed, cancelled. Case statuses: pass, fail, error, inconclusive.
`completed` means evaluation finished, not that every case passed. Judge/provider errors make the run `failed`.

The previous `/api/benchmarks/*`, `/api/agents/*`, and `/api/analytics/*` synthetic endpoints are intentionally no longer mounted.
# Beta integration contract

`GET /api/beta/capabilities` returns the machine-readable `memoryscope-answer-evaluation-v1` contract. It reports external SSE answer evaluation and grounded judging as supported, and persistent memory lifecycle and tenant-isolation testing as unsupported. Orchestrators should check this manifest before submitting cases; it does not imply those unsupported capabilities.

