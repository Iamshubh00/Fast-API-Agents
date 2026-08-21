import json

from app.agents.base import BaseAgent

# The ONLY actions the model is allowed to recommend. This list is enforced in code after the
# model responds (see orchestrator.py) -- the model's output is never trusted blindly, even
# though the prompt also constrains it. Defense in depth: prompt constraint + code-level allowlist.
ALLOWED_ACTIONS = {
    "monitor_only",
    "notify_analyst",
    "isolate_host",
    "disable_account",
    "revoke_token",
    "block_ip",
    "require_mfa_reverify",
    "escalate_to_oncall",
}

DESTRUCTIVE_ACTIONS = {"isolate_host", "disable_account", "revoke_token", "block_ip"}


class ResponseAgent(BaseAgent):
    """
    Recommends a response action. Critically: this agent's output is a RECOMMENDATION, never an
    executed action. Anything in DESTRUCTIVE_ACTIONS must go through human approval before any
    downstream system (e.g. a Temporal workflow) actually performs it. See orchestrator.py.
    """

    name = "response"
    system_prompt = f"""You are a SOC response-recommendation assistant. You are given the full
context of an investigated alert (triage, enrichment, correlation) and must recommend ONE response
action from this exact allowed list, nothing else:
{sorted(ALLOWED_ACTIONS)}

Respond ONLY with a JSON object matching this exact shape:
{{
  "recommended_action": string,     // MUST be exactly one value from the allowed list above
  "justification": string,          // plain-language reasoning an analyst/approver can review
  "is_destructive": boolean,        // true if this action changes system/account state
  "requires_human_approval": boolean,
  "confidence": number              // 0.0 to 1.0
}}

Rules:
- recommended_action MUST be exactly one of the allowed values, verbatim. Never invent a new action name.
- If evidence is weak or ambiguous, prefer "notify_analyst" or "monitor_only" over a destructive action.
- Any action that isolates, disables, revokes, or blocks something MUST have requires_human_approval: true.
"""

    def build_prompt(self, payload: dict) -> str:
        return (
            "Full investigation context:\n"
            f"Triage: {json.dumps(payload.get('triage_result', {}), default=str)}\n"
            f"Enrichment: {json.dumps(payload.get('enrichment_result', {}), default=str)}\n"
            f"Correlation: {json.dumps(payload.get('correlation_result', {}), default=str)}"
        )

    async def run(self, payload: dict) -> dict:
        result = await super().run(payload)
        action = result["output"].get("recommended_action")

        # Code-level enforcement -- never trust the model's own claim about its output shape.
        if action not in ALLOWED_ACTIONS:
            raise ValueError(f"Model recommended an action outside the allowed set: {action!r}")

        # Code-level override: destructive actions ALWAYS require approval, regardless of what
        # the model claims in requires_human_approval. The model's field is informational only.
        if action in DESTRUCTIVE_ACTIONS:
            result["output"]["requires_human_approval"] = True
            result["output"]["is_destructive"] = True

        return result
