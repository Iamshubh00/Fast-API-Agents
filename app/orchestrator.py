import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Alert, AgentRun, AuditLog
from app.agents.triage_agent import TriageAgent
from app.agents.enrichment_agent import EnrichmentAgent
from app.agents.correlation_agent import CorrelationAgent
from app.agents.response_agent import ResponseAgent
from app.threat_intel import fetch_threat_intel  # your own deterministic lookups, not agent calls
from app.config import settings

logger = logging.getLogger(__name__)

triage_agent = TriageAgent()
enrichment_agent = EnrichmentAgent()
correlation_agent = CorrelationAgent()
response_agent = ResponseAgent()


async def _persist_run(session: AsyncSession, alert_id: int, agent_name: str, input_summary: dict, result: dict):
    run = AgentRun(
        alert_id=alert_id,
        agent_name=agent_name,
        input_summary=input_summary,
        output=result["output"],
        model=result["model"],
        latency_ms=result["latency_ms"],
    )
    session.add(run)
    await session.commit()
    return run


async def _audit(session: AsyncSession, actor: str, action: str, target: str, details: dict | None = None):
    session.add(AuditLog(actor=actor, action=action, target=target, details=details or {}))
    await session.commit()


async def find_candidate_related_alerts(session: AsyncSession, alert: Alert, limit: int = 10) -> list[dict]:
    """
    Deterministic candidate lookup -- NOT an LLM call. Pulls other recent alerts sharing an
    entity (host/ip/user) from the raw_event JSON. The correlation agent only ever reasons over
    this pre-narrowed shortlist, never the full alert table.
    """
    entity_keys = ("host_id", "src_ip", "user")
    entity_values = [alert.raw_event.get(k) for k in entity_keys if alert.raw_event.get(k)]
    if not entity_values:
        return []

    stmt = (
        select(Alert)
        .where(Alert.id != alert.id)
        .order_by(Alert.created_at.desc())
        .limit(limit * 3)  # over-fetch, then filter in Python for simplicity at this scale
    )
    result = await session.execute(stmt)
    candidates = []
    for other in result.scalars():
        if any(other.raw_event.get(k) in entity_values for k in entity_keys):
            candidates.append({"id": other.id, "raw_event": other.raw_event, "severity_raw": other.severity_raw})
        if len(candidates) >= limit:
            break
    return candidates


async def run_pipeline(session: AsyncSession, alert_id: int) -> dict:
    """
    Runs the full agent pipeline against one alert, sequentially, persisting every intermediate
    output. If a destructive response action is recommended, the alert is left in
    'awaiting_approval' status and NOTHING is executed -- a separate, human-gated endpoint
    (see api/routes.py: /alerts/{id}/approve-response) must confirm before any action fires.
    """
    alert = await session.get(Alert, alert_id)
    if not alert:
        raise ValueError(f"Alert {alert_id} not found")

    # --- Stage 1: Triage ---
    alert.status = "triaging"
    await session.commit()

    triage_result = await triage_agent.run(alert.raw_event)
    await _persist_run(session, alert.id, "triage", alert.raw_event, triage_result)
    await _audit(session, actor="agent:triage", action="triaged_alert", target=f"alert:{alert.id}",
                 details={"severity": triage_result["output"].get("severity")})

    if triage_result["output"].get("recommended_next_step") == "auto_close":
        alert.status = "closed"
        await session.commit()
        await _audit(session, actor="agent:triage", action="auto_closed_false_positive", target=f"alert:{alert.id}")
        return {"status": "closed", "reason": "high-confidence false positive", "triage": triage_result["output"]}

    # --- Stage 2: Enrichment (deterministic intel fetch, then LLM summarization) ---
    alert.status = "enriched"
    intel = await fetch_threat_intel(alert.raw_event)  # your own code: VT/MISP/asset DB lookups
    enrichment_result = await enrichment_agent.run({"triage_result": triage_result["output"], "threat_intel": intel})
    await _persist_run(session, alert.id, "enrichment",
                        {"triage_result": triage_result["output"], "threat_intel": intel}, enrichment_result)
    await session.commit()

    # --- Stage 3: Correlation (deterministic candidate lookup, then LLM judgment) ---
    candidates = await find_candidate_related_alerts(session, alert)
    correlation_result = await correlation_agent.run({
        "enrichment_result": enrichment_result["output"],
        "candidate_alerts": candidates,
    })
    await _persist_run(session, alert.id, "correlation",
                        {"candidate_ids": [c["id"] for c in candidates]}, correlation_result)
    alert.status = "correlated"
    await session.commit()

    # --- Stage 4: Response recommendation ---
    response_result = await response_agent.run({
        "triage_result": triage_result["output"],
        "enrichment_result": enrichment_result["output"],
        "correlation_result": correlation_result["output"],
    })
    await _persist_run(session, alert.id, "response",
                        {"pipeline_summary": "triage+enrichment+correlation"}, response_result)

    requires_approval = response_result["output"].get("requires_human_approval", True)
    alert.status = "awaiting_approval" if requires_approval else "auto_actionable"
    await session.commit()

    await _audit(session, actor="agent:response", action="recommended_response", target=f"alert:{alert.id}",
                 details={"action": response_result["output"].get("recommended_action"),
                          "requires_approval": requires_approval})

    return {
        "status": alert.status,
        "triage": triage_result["output"],
        "enrichment": enrichment_result["output"],
        "correlation": correlation_result["output"],
        "response_recommendation": response_result["output"],
    }
