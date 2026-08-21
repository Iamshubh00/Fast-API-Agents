import json

from app.agents.base import BaseAgent


class CorrelationAgent(BaseAgent):
    """
    Given an enriched alert plus a shortlist of other recent alerts (already narrowed down by
    deterministic code -- e.g. shared IP/host/user via a SQL query or graph lookup, NOT by the LLM
    scanning your whole alert history), decide whether this looks like part of a broader incident.
    """

    name = "correlation"
    system_prompt = """You are a SOC correlation assistant. You are given one enriched alert and a
shortlist of other recent alerts that share some overlapping entity (same host, IP, or user --
already identified by deterministic matching, not by you).

Decide whether these alerts likely represent a single coordinated incident.

Respond ONLY with a JSON object matching this exact shape:
{
  "is_part_of_incident": boolean,
  "related_alert_ids": [integer],       // subset of the provided candidate IDs you believe are related, only
  "incident_hypothesis": string | null, // short plain-language theory of what's happening, or null if unrelated
  "confidence": number                  // 0.0 to 1.0
}

Rules:
- related_alert_ids MUST be a subset of the candidate IDs given to you. Never invent an ID.
- If the shared entity alone doesn't imply a real relationship (e.g. same corporate proxy IP for
  thousands of unrelated users), say is_part_of_incident: false and explain why in incident_hypothesis.
"""

    def build_prompt(self, payload: dict) -> str:
        return (
            "Enriched alert:\n"
            f"{json.dumps(payload.get('enrichment_result', {}), indent=2, default=str)}\n\n"
            "Candidate related alerts (only these IDs are valid references):\n"
            f"{json.dumps(payload.get('candidate_alerts', []), indent=2, default=str)}"
        )
