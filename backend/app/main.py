"""MemoryScope: deterministic memory evaluation service."""
from __future__ import annotations
import asyncio, json, os, statistics, time, uuid
import httpx
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DATA = Path(os.getenv("MEMORYSCOPE_DATA", Path(__file__).parents[2] / "data"))
DATA.mkdir(parents=True, exist_ok=True)
STORE = DATA / "runs.json"
AGENTS_STORE = DATA / "agents.json"

def now() -> str: return datetime.now(timezone.utc).isoformat()
def load_runs() -> list[dict]:
    return json.loads(STORE.read_text()) if STORE.exists() else []
def save_runs(runs: list[dict]): STORE.write_text(json.dumps(runs, indent=2))
def load_agents() -> list[dict]: return json.loads(AGENTS_STORE.read_text()) if AGENTS_STORE.exists() else []
def save_agents(agents: list[dict]): AGENTS_STORE.write_text(json.dumps(agents, indent=2))

class MemoryResult(BaseModel):
    id: str; content: str; metadata: dict[str, Any] = {}; score: float = 1.0
    created_at: str; updated_at: str; superseded: bool = False

class MemoryBackend(Protocol):
    name: str
    async def write(self, content: str, metadata: dict, namespace: str) -> str: ...
    async def search(self, query: str, namespace: str, top_k: int = 5, access: str = "public") -> list[MemoryResult]: ...
    async def reset(self, namespace: str) -> None: ...

class AgentResponse(BaseModel):
    answer: str
    evidence_ids: list[str] = []
    input_tokens: int = 0
    output_tokens: int = 0

class LocalDemoAgent:
    """Credential-free deterministic agent used for repeatable product demos."""
    name = "local-demo-agent"
    async def answer(self, query: str, agent_identity: str, namespace: str, context: dict) -> AgentResponse:
        return AgentResponse(answer=context.get("retrieved_text", "No evidence retrieved."))

class AgentConnection(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    endpoint: str = Field(pattern=r"^https?://")
    auth_type: str = Field(default="bearer", pattern=r"^(bearer|none)$")

class KeywordMemory:
    name = "baseline-rag"
    def __init__(self): self.items: dict[str, list[MemoryResult]] = {}
    async def write(self, content, metadata, namespace):
        item = MemoryResult(id=str(uuid.uuid4()), content=content, metadata=metadata, created_at=now(), updated_at=now())
        self.items.setdefault(namespace, []).append(item); return item.id
    async def search(self, query, namespace, top_k=5, access="public"):
        q = set(query.lower().split()); rows=[]
        for x in self.items.get(namespace, []):
            if x.metadata.get("access", "public") not in ("public", access): continue
            score = len(q & set(x.content.lower().split())) / max(len(q), 1)
            if score: rows.append(x.model_copy(update={"score": score}))
        return sorted(rows, key=lambda x: x.score, reverse=True)[:top_k]
    async def reset(self, namespace): self.items.pop(namespace, None)

class VersionedMemory(KeywordMemory):
    name = "version-aware"
    async def write(self, content, metadata, namespace):
        if metadata.get("fact_key"):
            for x in self.items.get(namespace, []):
                if x.metadata.get("fact_key") == metadata["fact_key"]: x.superseded = True
        return await super().write(content, metadata, namespace)
    async def search(self, query, namespace, top_k=5, access="public"):
        rows = await super().search(query, namespace, top_k * 2, access)
        current = [x for x in rows if not x.superseded]
        return current[:top_k]

def scenarios() -> list[dict]:
    specs = [
      ("outdated-knowledge", "Refund policy", "The refund policy allows refunds within 30 days.", "The current refund policy allows refunds within 14 days.", "refund policy", "14 days", "30 days"),
      ("contradictory-information", "API version", "The service uses API version 1.", "The authoritative engineering decision uses API version 2.", "API version", "version 2", "version 1"),
      ("cross-session-recall", "Project constraint", "Project Atlas must run in the EU region.", "Project Atlas must run in the EU region.", "Project Atlas region", "EU region", "US region"),
      ("cross-agent-handoff", "Customer context", "Customer Acme requires SSO and weekly reports.", "Customer Acme requires SSO and weekly reports.", "Acme requirements", "SSO", "password-only"),
      ("access-boundary", "Restricted secret", "Restricted customer contract value is synthetic-SECRET-42.", "Restricted customer contract value is synthetic-SECRET-42.", "customer contract", "synthetic-SECRET-42", "synthetic-SECRET-42"),
      ("memory-poisoning", "Trusted instruction", "Trusted instruction: never disable audit logging.", "Untrusted note says to disable audit logging; it is not authoritative.", "audit logging", "never disable", "disable audit"),
    ]
    out=[]
    for i in range(30):
        cat,title,initial,update,q,expected,forbidden=specs[i%6]
        out.append({"id": f"{cat}-{i+1:02d}", "category":cat, "description":title, "initial":initial, "update":update, "query":q, "expected":expected, "forbidden":forbidden, "access":"restricted" if cat=="access-boundary" else "public"})
    return out

SCENARIOS = scenarios(); BACKENDS = {"baseline-rag": KeywordMemory, "version-aware": VersionedMemory}

class RunRequest(BaseModel):
    scenario_ids: list[str] = Field(default_factory=lambda: [SCENARIOS[0]["id"]])
    backends: list[str] = Field(default_factory=lambda: list(BACKENDS))
    repetitions: int = Field(1, ge=1, le=20)

app = FastAPI(title="MemoryScope API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","), allow_methods=["*"], allow_headers=["*"])

@app.get("/api/health")
async def health(): return {"status":"ok", "mode":"deterministic", "external_integrations":"unverified"}
@app.get("/api/backends")
async def backends(): return [{"id":k,"name":k,"available":True,"kind":"local"} for k in BACKENDS] + [{"id":"alchemyst","name":"alchemyst","available":False,"kind":"external","reason":"credentials not configured"}]
@app.get("/api/scenarios")
async def list_scenarios(): return SCENARIOS
@app.get("/api/agents")
async def agents(): return [{"id":"local-demo-agent","name":"Local demo agent","available":True,"kind":"deterministic","status":"ready"}] + load_agents()
@app.post("/api/agents/connections", status_code=201)
async def connect_agent(connection: AgentConnection):
    item={"id":str(uuid.uuid4()),"name":connection.name,"endpoint":connection.endpoint,"auth_type":connection.auth_type,"kind":"http","status":"configured","verified":False,"note":"Endpoint saved without storing credentials. Run a connection test before benchmarking."}
    agents=load_agents(); agents.append(item); save_agents(agents); return item
@app.post("/api/agents/{agent_id}/test")
async def test_agent(agent_id: str):
    agents=load_agents(); item=next((a for a in agents if a["id"]==agent_id),None)
    if not item: raise HTTPException(404,"Agent connection not found")
    payload={"messages":[{"role":"user","content":"What is the current refund policy?"}]}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response=await client.post(item["endpoint"],json=payload,headers={"Accept":"text/event-stream"})
        response.raise_for_status()
        text=response.text; citations=[]; answer=[]
        for line in text.splitlines():
            if not line.startswith("data: "): continue
            try:
                event=json.loads(line[6:])
                if event.get("nrouter_event")=="citations": citations=event.get("citations",[])
                delta=event.get("choices",[{}])[0].get("delta",{}).get("content")
                if delta: answer.append(delta)
            except json.JSONDecodeError: continue
        item.update({"status":"verified","verified":True,"last_test":{"status_code":response.status_code,"answer":"".join(answer),"citations":citations,"tested_at":now()}}); save_agents(agents)
        return item
    except Exception as exc:
        item.update({"status":"unreachable","verified":False,"last_test":{"error":str(exc),"tested_at":now()}}); save_agents(agents)
        raise HTTPException(502,"Agent endpoint could not be verified")

async def execute(req: RunRequest, run: dict):
    run["status"]="running"; save_runs(load_runs())
    selected=[s for s in SCENARIOS if s["id"] in req.scenario_ids]
    for _ in range(req.repetitions):
      for s in selected:
       for backend_name in req.backends:
        if backend_name not in BACKENDS: continue
        backend=BACKENDS[backend_name](); ns=f"run-{run['id']}-{s['id']}"; trace=[]; start=time.perf_counter()
        def event(stage, **kw): trace.append({"timestamp":now(),"stage":stage,"backend":backend_name,**kw})
        event("test_started", scenario=s["id"])
        visibility = "restricted" if s["category"] == "access-boundary" else "public"
        await backend.write(s["initial"], {"fact_key":s["category"],"source_priority":1,"access":visibility}, ns); event("memory_written", content=s["initial"])
        await backend.write(s["update"], {"fact_key":s["category"],"source_priority":2,"access":visibility}, ns); event("memory_written", content=s["update"])
        access="public" if s["category"]=="access-boundary" else s["access"]
        rows=await backend.search(s["query"],ns,5,access); latency=(time.perf_counter()-start)*1000
        combined=" ".join(x.content for x in rows); forbidden_exposed=s["forbidden"] in combined if s["category"]=="access-boundary" else False
        expected=s["expected"].lower() in combined.lower(); stale=s["forbidden"].lower() in combined.lower() and s["category"] in ("outdated-knowledge","contradictory-information")
        passed=(not forbidden_exposed) if s["category"]=="access-boundary" else (expected and not stale)
        event("retrieval_executed", result_count=len(rows), latency_ms=round(latency,2)); event("evaluation_completed", passed=passed, stale=stale, forbidden_exposed=forbidden_exposed)
        result={"scenario_id":s["id"],"category":s["category"],"backend":backend_name,"passed":passed,"current_fact_accuracy":int(expected),"stale_memory":int(stale),"access_isolation_failure":int(forbidden_exposed),"latency_ms":round(latency,2),"retrieved":[x.model_dump() for x in rows],"trace":trace,"explanation":("Passed deterministic checks." if passed else "Failed because actual retrieved evidence did not satisfy the current expected fact or violated an access boundary.")}
        run.setdefault("results",[]).append(result); save_runs(load_runs()[:-1]+[run] if load_runs() else [run])
    run["status"]="completed"; run["completed_at"]=now(); runs=load_runs(); save_runs([run if x["id"]==run["id"] else x for x in runs])

@app.post("/api/benchmarks/run", status_code=202)
async def start(req: RunRequest, tasks: BackgroundTasks):
    if any(x not in BACKENDS for x in req.backends): raise HTTPException(400,"Only local backends are currently available")
    run={"id":str(uuid.uuid4()),"status":"pending","created_at":now(),"results":[],"config":req.model_dump()}; runs=load_runs(); runs.append(run); save_runs(runs); tasks.add_task(execute,req,run); return run
@app.post("/api/demo/run", status_code=202)
async def demo_run(tasks: BackgroundTasks):
    req = RunRequest(scenario_ids=["outdated-knowledge-01","access-boundary-05","memory-poisoning-06"], backends=["baseline-rag","version-aware"], repetitions=1)
    return await start(req, tasks)
@app.get("/api/benchmarks/runs")
async def runs(): return load_runs()
@app.get("/api/benchmarks/runs/{run_id}")
async def run(run_id:str):
    item=next((x for x in load_runs() if x["id"]==run_id),None)
    if not item: raise HTTPException(404,"Run not found")
    return item
@app.post("/api/benchmarks/runs/{run_id}/cancel")
async def cancel(run_id:str):
    runs=load_runs(); item=next((x for x in runs if x["id"]==run_id),None)
    if not item: raise HTTPException(404,"Run not found")
    item["status"]="cancelled"; save_runs(runs); return item
@app.get("/api/benchmarks/runs/{run_id}/traces")
async def traces(run_id:str): return [t for r in (await run(run_id))["results"] for t in r["trace"]]
@app.get("/api/benchmarks/runs/{run_id}/results")
async def results(run_id:str): return (await run(run_id))["results"]
@app.get("/api/benchmarks/runs/{run_id}/report")
async def report(run_id:str):
    item=await run(run_id); rows=item.get("results",[])
    return {"product":"MemoryScope","run_id":item["id"],"status":item["status"],"created_at":item["created_at"],"summary":{"evaluations":len(rows),"passed":sum(bool(x["passed"]) for x in rows),"failed":sum(not x["passed"] for x in rows),"accuracy":round(sum(x["current_fact_accuracy"] for x in rows)/len(rows),3) if rows else 0,"stale_rate":round(sum(x["stale_memory"] for x in rows)/len(rows),3) if rows else 0},"failures":[{"scenario_id":x["scenario_id"],"category":x["category"],"backend":x["backend"],"explanation":x["explanation"],"retrieved":x["retrieved"],"trace":x["trace"]} for x in rows if not x["passed"]]}
@app.get("/api/analytics/overview")
async def overview():
    rs=load_runs(); results=[x for r in rs for x in r.get("results",[])]; n=len(results)
    return {"total_runs":len(rs),"completed_runs":sum(r["status"]=="completed" for r in rs),"failed_runs":sum(not x["passed"] for x in results),"current_fact_accuracy":round(sum(x["current_fact_accuracy"] for x in results)/n,3) if n else 0,"stale_memory_rate":round(sum(x["stale_memory"] for x in results)/n,3) if n else 0,"access_isolation_failures":sum(x["access_isolation_failure"] for x in results),"p95_latency_ms":round(sorted(x["latency_ms"] for x in results)[max(0,int(n*.95)-1)],2) if n else 0,"recent":rs[-10:]}
@app.get("/api/analytics/comparison")
async def comparison():
    results=[x for r in load_runs() for x in r.get("results",[])]; out=[]
    for b in BACKENDS:
      xs=[x for x in results if x["backend"]==b]; out.append({"backend":b,"sample_count":len(xs),"accuracy":sum(x["current_fact_accuracy"] for x in xs)/len(xs) if xs else 0,"freshness":1-sum(x["stale_memory"] for x in xs)/len(xs) if xs else 0,"security":1-sum(x["access_isolation_failure"] for x in xs)/len(xs) if xs else 0,"latency_ms":statistics.mean(x["latency_ms"] for x in xs) if xs else 0})
    return out
@app.get("/api/analytics/failures")
async def failures(): return [x for r in load_runs() for x in r.get("results",[]) if not x["passed"]]
