# MemoryScope

Local developer beta for evaluating a real customer-support agent against approved facts.

**Not a hosted multi-user service, memory firewall, or proof of persistent-memory correctness.**
The beta tests individual answers; lifecycle testing needs session/seed/reset adapters that are not yet implemented.
The original synthetic memory experiments are archived in `backend/app/legacy_demo.py` and are not exposed by the beta API.

## What a user provides

1. A running support agent with an SSE chat endpoint (default `http://127.0.0.1:4175/api/chat`).
2. A JSON array of 1–20 cases: question, approved reference, expected behavior, and optional literal/citation-presence checks.
3. A server-side API key and judge model for a supported LLM provider.
4. Explicit consent to send the references and agent answers to that provider.

MemoryScope sends **only the question** to the agent. It captures the real answer, applies deterministic checks, and then uses a **required reference-grounded LLM judge**. It saves evidence, verdicts and model metadata locally in SQLite.

## Start locally

Use Python 3.11+ and Node 22. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
Copy-Item .env.example .env
```

Edit `.env` (never commit it) with your LLM provider credentials, base URL, model ID, and the allowed target origin. Use the variable names shown in [`.env.example`](.env.example):

There is no optional-judge switch or silent fallback. A model must be explicitly configured for comparable runs. The evaluation pipeline is fixed; choose a model available in your provider account. No model is claimed universally best. The judge uses an OpenAI-compatible chat-completions API at the configured base URL. Non-loopback provider URLs must use HTTPS. See `.env.example` and the provider's API documentation for configuration details.

Start the backend from the repository root:

```powershell
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
npm ci
npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000`. If the support-agent frontend already uses port 3000, run MemoryScope on 3001 and add `http://127.0.0.1:3001` to `CORS_ORIGINS` in `.env`; restart the backend.
Do not run `next dev` and `next build` concurrently in the same folder.
Restart the backend after changing environment variables.

Docker Compose is provided for local development, not production hosting.
Inside Docker, `127.0.0.1` points to the container, not your host agent.
On Docker Desktop, use `http://host.docker.internal:4175/api/chat` and explicitly
allowlist `http://host.docker.internal:4175` in `.env` instead.

## First real evaluation

Run your support agent separately. Its supported response contract is:

```text
data: {"choices":[{"delta":{"content":"Your answer"}}]}

data: [DONE]
```

Response type must be `text/event-stream`. Error events, empty answers, incomplete streams, and HTML responses are rejected. Provider-specific citation and cost events are captured when present.

Paste the agent endpoint in the dashboard. Replace the sample reference with a verified excerpt from **your agent's actual knowledge base**. Example schema (illustrative policy, not a claim about your agent):

```json
[
  {
    "name": "Refund window",
    "question": "How long do I have to request a refund?",
    "reference": "Customers may request a refund within 14 days of purchase.",
    "expected": "State that the refund window is 14 days.",
    "required_literals": ["14"],
    "forbidden_literals": ["30 days"],
    "require_citations": false
  }
]
```

Approve transmission and click **Run evaluation**. Expand each case to inspect the actual answer, approved reference, checks, judge rationale and supporting quotes. Export the report before sharing it; it contains your reference text and agent answers.
After changing your agent, rerun the same cases and compare with a completed baseline.

For authenticated agents, set a variable such as `MEMORYSCOPE_AGENT_SUPPORT_TOKEN` server-side and enter **that variable name**, not its value, in the dashboard.

## Evaluation policy

- Literal checks are case-insensitive substring tests, not semantic reasoning. Citation checks establish presence only, not citation authenticity.
- The judge evaluates semantic correctness and unsupported material claims against the supplied reference and expected behavior.
- Pass/fail judgments require verbatim supporting quotes from both answer and reference; invalid JSON and ungrounded quotes are errors.
- A deterministic failure overrides a valid passing judge judgment.
- Insufficient reference evidence produces **inconclusive**, never pass.
- Provider/configuration/protocol failures produce **error**, never pass. If the judge fails after the agent answers, that answer remains in the report.
- Pass rate uses only pass + fail as its denominator. Errors and inconclusive counts remain visible; a high pass rate with poor coverage is not release approval.
- Judge decisions remain fallible. Human-review disputed cases and calibrate against labelled examples before using scores for release decisions.
- One sequential run at a time, at most 20 cases, one agent call and one judge call per case, no automatic paid retries. Maximum 65 seconds per stage and 1 MB response limit.
- Cancellation prevents subsequent dispatches; an already in-flight provider request may complete and incur charges.
- Compare requires identical cases, pipeline and configured model. Provider routing can still change; reports include the returned model when supplied.

## Data and deployment boundaries

SQLite history lives in `data/beta.sqlite3` by default. `.env` and database files are ignored by git.
The API does not accept raw keys. Local reports contain potentially sensitive content: use synthetic/test customer data, protect disk access, and delete local database files only when the service is stopped if you want to clear history.
Data retention and billing follow your LLM provider's terms and configuration; MemoryScope does not promise zero retention.

**Bind to loopback only.** No user authentication, tenant isolation, encryption at rest, rate limiting, or hosted-worker durability is provided.
Explicit operator-controlled origins and disabled redirects limit outbound destinations; this is not a hardened internet-facing SSRF boundary.
Run one backend process. Interrupted runs are marked failed on restart; they are not silently resumed or billed again.

## Tests

```powershell
python -m pytest -q
cd frontend
npm run build
```

Automated tests use isolated SQLite files and mocked provider responses. They test the real evaluation code, not the accuracy of a live model. A paid end-to-end evaluation requires your credentials and running agent.
See [API.md](API.md) for beta endpoints.

## Next milestones

Session-aware seed/reset adapters; labelled judge calibration; CI exit-code integration; authenticated hosted deployment with isolated workers and retention controls. These are not current beta capabilities.
