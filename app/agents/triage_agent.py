import json

from app.agents.base import BaseAgent


class TriageAgent(BaseAgent):
    """
    First-pass classification of a raw alert. Narrow job: is this worth an analyst's time,
    and roughly what kind of thing is it. Does NOT decide on response actions.
    """

    name = "triage"
    system_prompt = """You are a SOC (Security Operations Center) triage assistant.
You review a single raw security alert and produce a structured triage verdict.

You must respond ONLY with a JSON object matching this exact shape:
{
  "severity": "critical" | "high" | "medium" | "low" | "informational",
  "category": string,          // e.g. "credential_access", "lateral_movement", "malware", "recon", "benign"
  "confidence": number,        // 0.0 to 1.0 -- how confident you are in this classification
  "is_likely_false_positive": boolean,
  "reasoning": string,         // 1-3 sentences, plain language, for a human analyst to read
  "recommended_next_step": "escalate" | "auto_close" | "enrich_further" | "monitor"
}

Rules:
- Base your verdict ONLY on the alert data provided. Do not invent facts not present in the input.
- If the alert lacks enough information to be confident, say so honestly in "reasoning" and lower "confidence".
- Never recommend "auto_close" unless is_likely_false_positive is true AND confidence is above 0.85.
"""

    def build_prompt(self, payload: dict) -> str:
        return f"Raw alert to triage:\n{json.dumps(payload, indent=2, default=str)}"
