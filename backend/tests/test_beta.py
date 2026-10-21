import json
import pytest
from fastapi.testclient import TestClient
from app import beta
from app.main import app

CASE = dict(name="refund", question="Refund window?", reference="Refunds within 14 days.",
            expected="Explain the 14 day window.", required_literals=["14"])
PAYLOAD = dict(agent_name="support", endpoint="http://127.0.0.1:4175/api/chat",
               cases=[CASE], send_to_judge=True)

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(beta, "DB", tmp_path / "test.sqlite3")
    monkeypatch.setenv("NROUTER_API_KEY", "test-secret")
    monkeypatch.setenv("NROUTER_JUDGE_MODEL", "test-model")
    monkeypatch.setenv("NROUTER_BASE_URL", "https://api.nrouter.ai/v1")
    monkeypatch.setenv("MEMORYSCOPE_AGENT_ORIGINS", "http://127.0.0.1:4175")
    with TestClient(app) as client:
        yield client

def sse(answer="Refunds within 14 days."):
    return 'data: ' + json.dumps({"choices": [{"delta": {"content": answer}}]}) + '\n\ndata: [DONE]\n\n'

async def fake_request(url, payload, headers, timeout=60):
    if url.endswith("/api/chat"):
        assert payload == {"messages": [{"role": "user", "content": CASE["question"]}]}
        return sse(), "text/event-stream"
    assert headers["Authorization"] == "Bearer test-secret"
    assert payload["model"] == "test-model"
    verdict = dict(verdict="pass", rationale="Matches the approved policy.",
                   answer_quote="14 days", reference_quote="14 days")
    return json.dumps({"model": "test-model", "choices": [{"message": {"content": json.dumps(verdict)}}]}), "application/json"

def test_real_pipeline_contract(client, monkeypatch):
    monkeypatch.setattr(beta, "request_bytes", fake_request)
    response = client.post("/api/beta/runs", json=PAYLOAD)
    assert response.status_code == 202
    run_id = response.json()["id"]
    run = client.get("/api/beta/runs/" + run_id).json()
    assert run["status"] == "completed"
    assert run["summary"]["pass"] == 1
    assert run["results"][0]["judge"]["answer_quote"] == "14 days"
    assert "test-secret" not in client.get(f"/api/beta/runs/{run_id}/report").text
    assert len(client.get("/api/beta/runs").json()) == 1
    assert client.post(f"/api/beta/runs/{run_id}/cancel").status_code == 409

def test_capability_manifest_distinguishes_answer_judging_from_memory_lifecycle(client):
    manifest = client.get("/api/beta/capabilities").json()
    assert manifest["contract"] == "memoryscope-answer-evaluation-v1"
    assert manifest["capabilities"]["external_agent_answer_evaluation"] is True
    assert manifest["capabilities"]["persistent_memory_lifecycle"] is False
    assert manifest["requires_explicit_judge_consent"] is True

@pytest.mark.parametrize("text,kind", [
    ("<html>OK</html>", "text/html"),
    ("data: [DONE]\n\n", "text/event-stream"),
    ('data: {"choices":[]}\n\n', "text/event-stream"),
    ('data: {"nrouter_event":"error"}\n\ndata: [DONE]\n\n', "text/event-stream"),
    ('data: broken\n\n', "text/event-stream"),
])
def test_invalid_agent_responses(text, kind):
    with pytest.raises(ValueError):
        beta.parse_sse(text, kind)

@pytest.mark.parametrize("override", [
    {"cases": []}, {"cases": [CASE, CASE]}, {"send_to_judge": False},
    {"endpoint": "http://169.254.169.254/latest"},
    {"endpoint": "http://127.0.0.1:4175/api/chat?token=secret"},
    {"auth_env": "PATH"},
    {"cases": [{**CASE, "unexpected": True}]},
])
def test_invalid_requests(client, override):
    assert client.post("/api/beta/runs", json={**PAYLOAD, **override}).status_code == 422

def test_missing_judge_does_not_run(client, monkeypatch):
    monkeypatch.delenv("NROUTER_API_KEY")
    assert client.post("/api/beta/runs", json=PAYLOAD).status_code == 503
    assert client.get("/api/beta/runs").json() == []

def test_failure_keeps_answer_and_no_false_score(client, monkeypatch):
    async def failing(url, payload, headers, timeout=60):
        if url.endswith("/api/chat"):
            return sse(), "text/event-stream"
        raise ValueError("test-secret upstream body")
    monkeypatch.setattr(beta, "request_bytes", failing)
    run_id = client.post("/api/beta/runs", json=PAYLOAD).json()["id"]
    run = client.get("/api/beta/runs/" + run_id).json()
    assert run["status"] == "failed"
    assert run["summary"]["pass_rate"] is None
    assert run["results"][0]["answer"]
    assert "test-secret" not in json.dumps(run)

@pytest.mark.asyncio
async def test_ungrounded_judge_rejected(monkeypatch):
    monkeypatch.setenv("NROUTER_API_KEY", "test")
    monkeypatch.setenv("NROUTER_JUDGE_MODEL", "test")
    async def ungrounded(*args, **kwargs):
        verdict = dict(verdict="pass", rationale="yes", answer_quote="invented", reference_quote="14")
        return json.dumps({"choices": [{"message": {"content": json.dumps(verdict)}}]}), "application/json"
    monkeypatch.setattr(beta, "request_bytes", ungrounded)
    with pytest.raises(ValueError):
        await beta.judge(beta.Case(**CASE), {"answer": "14 days"})

@pytest.mark.asyncio
async def test_judge_uses_configured_nrouter_base_url(monkeypatch):
    monkeypatch.setenv("NROUTER_API_KEY", "test")
    monkeypatch.setenv("NROUTER_JUDGE_MODEL", "test")
    monkeypatch.setenv("NROUTER_BASE_URL", "https://router.example/v2/")
    observed = {}
    async def fake(url, payload, headers, timeout=60):
        observed["url"] = url
        verdict = dict(verdict="pass", rationale="Grounded.", answer_quote="14 days", reference_quote="14 days")
        return json.dumps({"choices": [{"message": {"content": json.dumps(verdict)}}]}), "application/json"
    monkeypatch.setattr(beta, "request_bytes", fake)
    await beta.judge(beta.Case(**CASE), {"answer": "Refunds within 14 days."})
    assert observed["url"] == "https://router.example/v2/chat/completions"

@pytest.mark.asyncio
async def test_judge_rejects_insecure_non_loopback_provider_base(monkeypatch):
    monkeypatch.setenv("NROUTER_API_KEY", "test")
    monkeypatch.setenv("NROUTER_JUDGE_MODEL", "test")
    monkeypatch.setenv("NROUTER_BASE_URL", "http://router.example/v1")
    with pytest.raises(ValueError, match="HTTPS"):
        await beta.judge(beta.Case(**CASE), {"answer": "Refunds within 14 days."})

def test_deterministic_fail_overrides_judge(client, monkeypatch):
    monkeypatch.setattr(beta, "request_bytes", fake_request)
    payload = {**PAYLOAD, "cases": [{**CASE, "forbidden_literals": ["14"]}]}
    run_id = client.post("/api/beta/runs", json=payload).json()["id"]
    assert client.get("/api/beta/runs/" + run_id).json()["summary"]["fail"] == 1

def test_recovery_and_cancel_do_not_resurrect(client):
    run = dict(id="r", status="running", results=[], summary=beta.summary([]))
    with beta.connect() as db:
        db.execute("INSERT INTO runs VALUES (?,?,?)", ("r", "running", json.dumps(run)))
    assert client.post("/api/beta/runs", json=PAYLOAD).status_code == 409
    assert client.post("/api/beta/runs/r/cancel").status_code == 200
    beta.put(run)
    assert beta.get("r")["status"] == "cancelled"
    with beta.connect() as db:
        db.execute("UPDATE runs SET status='running',payload=?", (json.dumps(run),))
    beta.recover()
    assert beta.get("r")["status"] == "failed"

def test_compare_same_suite(client, monkeypatch):
    monkeypatch.setattr(beta, "request_bytes", fake_request)
    first = client.post("/api/beta/runs", json=PAYLOAD).json()["id"]
    second = client.post("/api/beta/runs", json=PAYLOAD).json()["id"]
    comparison = client.get(f"/api/beta/compare/{first}/{second}")
    assert comparison.status_code == 200
    assert comparison.json()[0]["regression"] is False
    different_agent = {**PAYLOAD, "agent_name": "another support agent"}
    third = client.post("/api/beta/runs", json=different_agent).json()["id"]
    assert client.get(f"/api/beta/compare/{first}/{third}").status_code == 422
    assert client.get("/api/agents").status_code == 404

@pytest.mark.asyncio
@pytest.mark.parametrize("status,body", [(302, b""), (500, b"secret"), (200, b"x" * 101)])
async def test_transport_rejects_errors_redirects_and_oversize(monkeypatch, status, body):
    import httpx
    original = httpx.AsyncClient
    def factory(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        return original(**kwargs, transport=httpx.MockTransport(
            lambda request: httpx.Response(status, content=body)))
    monkeypatch.setattr(beta.httpx, "AsyncClient", factory)
    monkeypatch.setattr(beta, "MAX_BYTES", 100)
    with pytest.raises(ValueError):
        await beta.request_bytes("http://example.test", {}, {})

def test_inconclusive_is_not_pass(client, monkeypatch):
    async def uncertain(url, payload, headers, timeout=60):
        if url.endswith("/api/chat"):
            return sse(), "text/event-stream"
        verdict = dict(verdict="insufficient_evidence", rationale="Policy is insufficient.",
                       answer_quote="", reference_quote="")
        return json.dumps({"choices": [{"message": {"content": json.dumps(verdict)}}]}), "application/json"
    monkeypatch.setattr(beta, "request_bytes", uncertain)
    run_id = client.post("/api/beta/runs", json=PAYLOAD).json()["id"]
    run = beta.get(run_id)
    assert run["summary"]["inconclusive"] == 1
    assert run["summary"]["pass_rate"] is None

def test_cancel_after_agent_does_not_call_judge(client, monkeypatch):
    async def cancel_during_agent(config, case):
        beta.cancel(beta.history()[0]["id"])
        return {"answer": "14 days", "citations": []}
    async def must_not_call(*args):
        pytest.fail("Judge dispatched after cancellation")
    monkeypatch.setattr(beta, "ask_agent", cancel_during_agent)
    monkeypatch.setattr(beta, "judge", must_not_call)
    run_id = client.post("/api/beta/runs", json=PAYLOAD).json()["id"]
    assert beta.get(run_id)["status"] == "cancelled"
