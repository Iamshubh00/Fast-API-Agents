from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db import get_session
from app.models import Alert, AgentRun, AuditLog
from app.orchestrator import run_pipeline, response_agent
from app.auth import require_role  # Keycloak-backed role dependency, see app/auth.py

router = APIRouter(prefix="/agents", tags=["multi-agent-defense"])


class RawAlertIn(BaseModel):
    source: str
    severity_raw: str
    raw_event: dict


class ApprovalDecision(BaseModel):
    approved: bool
    justification: str


@router.post("/alerts", status_code=201)
async def submit_alert(
    payload: RawAlertIn,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(require_role("soc-analyst")),
):
    """Ingest a raw alert. Does not run the pipeline synchronously -- see /alerts/{id}/run."""
    alert = Alert(source=payload.source, severity_raw=payload.severity_raw, raw_event=payload.raw_event)
    session.add(alert)
    await session.commit()
    return {"alert_id": alert.id, "status": alert.status}


@router.post("/alerts/{alert_id}/run")
async def run_alert_pipeline(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(require_role("soc-analyst")),
):
    """
    Runs triage -> enrichment -> correlation -> response-recommendation sequentially.
    Any destructive recommendation is NEVER executed here -- it lands in 'awaiting_approval'.
    """
    try:
        result = await run_pipeline(session, alert_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return result


@router.get("/alerts/{alert_id}/trace")
async def get_alert_trace(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(require_role("soc-analyst")),
):
    """Full audit trace of every agent run against this alert -- what each agent saw and said."""
    alert = await session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")

    return {
        "alert": {"id": alert.id, "status": alert.status, "raw_event": alert.raw_event},
        "agent_runs": [
            {
                "agent": run.agent_name,
                "output": run.output,
                "model": run.model,
                "latency_ms": run.latency_ms,
                "created_at": run.created_at.isoformat(),
            }
            for run in sorted(alert.agent_runs, key=lambda r: r.created_at)
        ],
    }


@router.post("/alerts/{alert_id}/approve-response")
async def approve_response(
    alert_id: int,
    decision: ApprovalDecision,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(require_role("soc-lead")),  # stricter role than triage/run
):
    """
    The ONLY endpoint that can turn a response recommendation into an actual action.
    Locked to soc-lead. Every decision -- approved or denied -- is written to the audit log
    with the real approver's identity from the Keycloak JWT.
    """
    alert = await session.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    if alert.status != "awaiting_approval":
        raise HTTPException(409, f"Alert is not awaiting approval (status={alert.status})")

    latest_response_run = next(
        (r for r in sorted(alert.agent_runs, key=lambda r: r.created_at, reverse=True) if r.agent_name == "response"),
        None,
    )
    if not latest_response_run:
        raise HTTPException(500, "No response recommendation found for this alert")

    action = latest_response_run.output.get("recommended_action")

    session.add(AuditLog(
        actor=user["sub"],
        action="approved_response" if decision.approved else "denied_response",
        target=f"alert:{alert_id}",
        details={"recommended_action": action, "justification": decision.justification},
    ))

    if decision.approved:
        alert.status = "response_approved"
        # In a real system: start a Temporal workflow here to actually execute `action`,
        # e.g. temporal.start_workflow(ExecuteResponseAction.run, args=[alert_id, action], ...)
        # This service intentionally stops short of execution -- that's a separate, infra-facing
        # concern with its own retry/idempotency guarantees (see the Temporal design discussed earlier).
    else:
        alert.status = "response_denied"

    await session.commit()
    return {"status": alert.status, "action": action}
