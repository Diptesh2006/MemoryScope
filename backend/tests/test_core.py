from app.main import SCENARIOS, VersionedMemory
import pytest

def test_has_thirty_scenarios(): assert len(SCENARIOS) >= 30

@pytest.mark.asyncio
async def test_versioned_memory_hides_superseded_fact():
    m=VersionedMemory(); await m.write("refunds 30 days", {"fact_key":"refund"}, "n"); await m.write("refunds 14 days", {"fact_key":"refund"}, "n")
    rows=await m.search("refunds days", "n")
    assert len(rows)==1 and "14" in rows[0].content

