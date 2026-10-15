from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_and_catalog():
    assert client.get('/api/health').status_code == 200
    scenarios = client.get('/api/scenarios').json()
    assert len(scenarios) == 30
    assert {x['category'] for x in scenarios} == {
        'outdated-knowledge', 'contradictory-information', 'cross-session-recall',
        'cross-agent-handoff', 'access-boundary', 'memory-poisoning'
    }

def test_benchmark_persists_evidence():
    response = client.post('/api/benchmarks/run', json={
        'scenario_ids': ['outdated-knowledge-01', 'access-boundary-05'],
        'backends': ['baseline-rag', 'version-aware']
    })
    assert response.status_code == 202
    run = client.get('/api/benchmarks/runs/' + response.json()['id']).json()
    assert run['status'] == 'completed'
    assert len(run['results']) == 4
    assert all(result['trace'] for result in run['results'])
    access = [x for x in run['results'] if x['category'] == 'access-boundary']
    assert all(x['access_isolation_failure'] == 0 for x in access)

def test_rejects_external_backend_until_configured():
    response = client.post('/api/benchmarks/run', json={'backends': ['alchemyst']})
    assert response.status_code == 400
