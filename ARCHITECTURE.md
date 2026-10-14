# Architecture

The backend is a deliberately small monolith. `MemoryBackend` is the adapter contract; `KeywordMemory` models conventional retrieval and `VersionedMemory` suppresses superseded facts using a fact key. The scenario library is deterministic and produces 30 reproducible cases across six categories. Each execution records retrieval evidence, latency, evaluation flags, and an explanation. The frontend consumes only API responses.

For production, replace the JSON repository with SQLAlchemy/PostgreSQL + pgvector, add migrations and a durable queue, then implement authorization in the adapter query itself. External integrations must remain explicitly unavailable until a live credentialed test passes.

