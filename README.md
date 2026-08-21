Cyber Defense Multi-Agent Service (FastAPI + OpenAI)
A minimal, production-shaped multi-agent pipeline for SOC alert triage, enrichment, correlation,
and response recommendation -- built with FastAPI and the OpenAI API.
Architecture
```
POST /agents/alerts            -> ingest a raw alert
POST /agents/alerts/{id}/run   -> runs the pipeline: triage -> enrichment -> correlation -> response
GET  /agents/alerts/{id}/trace -> full audit trace of what every agent saw and said
POST /agents/alerts/{id}/approve-response  -> soc-lead ONLY; the sole endpoint that can approve
                                               a destructive action recommendation
```
Each agent (`app/agents/*.py`) has exactly one job and returns strict JSON, never free text.
Critical safety design -- read this before extending
Agents never call external threat-intel or execution APIs directly. `threat_intel.py`
performs deterministic lookups in your own code; only the results are handed to the LLM to
summarize. This avoids hallucinated indicators and unbounded/unauditable external calls.
Agents never execute actions -- only recommend them. `ResponseAgent` outputs a
recommendation constrained to `ALLOWED_ACTIONS`. `ResponseAgent.run()` re-validates the
model's output against that allowlist in code -- the model's own claims are never trusted
blindly (defense in depth: prompt constraint + code-level enforcement).
Destructive actions require human approval, enforced in code, not just by prompt.
`DESTRUCTIVE_ACTIONS` forces `requires_human_approval = True` regardless of what the model
says. Only `/agents/alerts/{id}/approve-response`, locked to the `soc-lead` Keycloak role,
can move an alert past `awaiting_approval` -- and even then, this service only marks it
approved; actually executing the action (isolate host, revoke token, etc.) is a separate,
infra-facing step -- wire it to a Temporal workflow with its own retries/idempotency rather
than firing it inline here.
Every agent output and every human decision is persisted immutably
(`agent_runs`, `audit_log` tables) -- this is what makes the system defensible in a
post-incident review: you can reconstruct exactly what each agent saw, what it concluded, and
who approved what.
Correlation only reasons over a pre-narrowed, deterministic candidate list
(`find_candidate_related_alerts`), never the full alert history -- keeps token usage bounded
and prevents the model from "discovering" spurious relationships across unrelated data.
Setup
```bash
cp .env.example .env   # fill in OPENAI_API_KEY, DATABASE_URL, etc.
pip install -r requirements.txt
alembic upgrade head    # after writing migrations for the models in app/models.py
uvicorn app.main:app --reload
```
Extending this
Swap the stub functions in `threat_intel.py` for real VirusTotal/MISP/CMDB calls.
Wire `/approve-response` to a Temporal workflow (see the earlier incident-response design) for
actual execution of approved actions, rather than just flipping a status field.
Add rate limiting / cost controls around OpenAI calls if alert volume is high -- consider
routing low-severity/high-confidence-false-positive alerts through cheaper models or skipping
the LLM entirely via deterministic rules where possible.
Add an eval harness that replays historical labeled alerts through the pipeline to measure
triage accuracy and false-positive/negative rates before trusting it in production.