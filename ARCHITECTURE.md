# Developer beta architecture

```text
Local dashboard
  │ endpoint + user-authored cases + consent
  ▼
FastAPI validation ──► SQLite run history
  │ single-process background execution
  ▼
nRouter support agent /api/chat
  │ question only → validated SSE answer
  ▼
Literal / citation-presence checks
  │ answer + approved reference + expected behavior
  ▼
Required nRouter LLM judge
  │ strict JSON + verbatim evidence validation
  ▼
Final case verdict ──► SQLite ──► dashboard / report / comparison
```

`app/main.py` loads root `.env` and mounts only `app/beta.py`. The old experiments in
`app/legacy_demo.py` are not production routes. Frontend forms and history use `/api/beta`.
SQLite transactions protect run admission and cancellation. On startup, unfinished
runs become failed; no automatic resumption or paid retries.

The judge is required, not an optional plugin. A deterministic failure overrides
a valid semantic pass. Judge errors are unscored, and insufficient reference evidence
is inconclusive. Evidence quotes are checked against input; that does not make the
judge infallible or immune to prompt injection.

Local trust boundary: server-owned credentials, explicit agent-origin allowlist,
redirects disabled, response/time limits, references withheld from agent prompts.
No hosted authentication, tenant isolation or durable queue. Browser consent covers
sending user-provided references and answers to nRouter. Data remains in local reports
and may also be retained by the provider under its applicable policy.

Current scope is answer correctness, not memory lifecycle verification.
To test deletion, conflicting updates or cross-session isolation, add explicit
fixture setup/reset and session adapters before making those claims.
