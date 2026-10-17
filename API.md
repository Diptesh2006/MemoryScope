# API

Interactive OpenAPI documentation is available at `/docs` when the backend is running.

- `GET /api/health`
- `GET /api/backends`
- `GET /api/scenarios`
- `POST /api/benchmarks/run`
- `GET /api/benchmarks/runs`
- `GET /api/benchmarks/runs/{id}`
- `GET /api/benchmarks/runs/{id}/traces`
- `GET /api/benchmarks/runs/{id}/results`
- `GET /api/benchmarks/runs/{id}/report`
- `POST /api/benchmarks/runs/{id}/cancel`
- `GET /api/analytics/overview`
- `GET /api/analytics/comparison`
- `GET /api/analytics/failures`

The report endpoint returns a portable JSON summary plus failed evaluations, retrieved evidence, and trace events. It is intended for attaching benchmark evidence to an issue, review, or CI artifact.

