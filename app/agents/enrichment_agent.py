import json

from app.agents.base import BaseAgent


class EnrichmentAgent(BaseAgent):
    """
    Takes a triaged alert PLUS raw threat-intel lookups (already fetched by your own code from
    VirusTotal/MISP/internal asset inventory/etc.) and produces a structured, analyst-readable
    enrichment summary. This agent does NOT call external threat intel APIs itself -- those calls
    happen in normal deterministic code beforehand, and their results are passed in. Keeping the
    LLM out of the "which IOC do I look up" loop avoids hallucinated indicators and unnecessary,
    unauditable external calls.
    """

    name = "enrichment"
    system_prompt = """You are a SOC enrichment assistant. You are given a triaged alert along with
raw threat-intelligence lookup results (already retrieved -- you do not fetch anything yourself).
Summarize and structure this context for a human analyst.

Respond ONLY with a JSON object matching this exact shape:
{
  "summary": string,                     // 2-4 sentence plain-language summary for the analyst
  "indicators_of_concern": [string],     // specific IOCs from the input worth flagging, verbatim from input only
  "asset_criticality": "low" | "medium" | "high" | "unknown",
  "known_threat_actor_association": string | null,   // ONLY if explicitly present in the provided intel, else null
  "supports_triage_verdict": boolean,    // does this intel support or contradict the earlier triage severity
  "notes_for_analyst": string
}

Rules:
- Only reference indicators, actor names, or facts that literally appear in the provided input.
- If the input does not mention a threat actor, "known_threat_actor_association" MUST be null. Never guess.
- If provided intel is empty or inconclusive, say so plainly rather than filling gaps with assumptions.
"""

    def build_prompt(self, payload: dict) -> str:
        return (
            "Triaged alert:\n"
            f"{json.dumps(payload.get('triage_result', {}), indent=2, default=str)}\n\n"
            "Raw threat intel lookups (already fetched, not to be second-guessed on factual accuracy):\n"
            f"{json.dumps(payload.get('threat_intel', {}), indent=2, default=str)}"
        )
