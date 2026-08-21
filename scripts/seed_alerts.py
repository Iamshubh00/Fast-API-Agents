"""
Posts every alert in test_data/sample_alerts.json to a running instance of the service,
then (optionally) runs the agent pipeline on each one and prints the result.

Usage:
    python -m scripts.seed_alerts                  # just ingest alerts
    python -m scripts.seed_alerts --run             # ingest AND run the pipeline on each
    python -m scripts.seed_alerts --run --base-url http://localhost:8000

Requires the service to be running (uvicorn app.main:app --reload) and, for this script,
DEV_DISABLE_AUTH=true set in your .env -- otherwise you'll need to pass a real bearer token.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

SAMPLE_FILE = Path(__file__).parent.parent / "test_data" / "sample_alerts.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--run", action="store_true", help="also run the agent pipeline on each seeded alert")
    parser.add_argument("--token", default=None, help="bearer token, if DEV_DISABLE_AUTH is not set")
    args = parser.parse_args()

    alerts = json.loads(SAMPLE_FILE.read_text())
    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}

    with httpx.Client(base_url=args.base_url, headers=headers, timeout=60.0) as client:
        for entry in alerts:
            label = entry.pop("_label", "unlabeled")
            resp = client.post("/agents/alerts", json=entry)
            if resp.status_code != 201:
                print(f"[{label}] FAILED to ingest: {resp.status_code} {resp.text}", file=sys.stderr)
                continue

            alert_id = resp.json()["alert_id"]
            print(f"[{label}] ingested as alert_id={alert_id}")

            if args.run:
                run_resp = client.post(f"/agents/alerts/{alert_id}/run")
                if run_resp.status_code != 200:
                    print(f"  -> pipeline FAILED: {run_resp.status_code} {run_resp.text}", file=sys.stderr)
                    continue
                result = run_resp.json()
                print(f"  -> status: {result.get('status')}")
                if "response_recommendation" in result:
                    rec = result["response_recommendation"]
                    print(f"  -> recommended_action: {rec.get('recommended_action')} "
                          f"(requires_approval={rec.get('requires_human_approval')})")

    print("\nDone. Try:")
    print(f"  curl {args.base_url}/agents/alerts/1/trace")


if __name__ == "__main__":
    main()
