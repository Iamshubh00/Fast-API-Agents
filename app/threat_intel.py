"""
Deterministic threat-intel lookups. Deliberately kept OUTSIDE any agent -- the LLM never decides
which external API to call or with what parameters. Your own code decides what to look up (based
on IOCs literally present in the alert), and only the RESULTS are handed to the enrichment agent
to summarize. This avoids the model hallucinating indicators or making unbounded external calls.

Wire the functions below to your real providers (VirusTotal, MISP, internal CMDB, etc.).
"""

import httpx


async def fetch_threat_intel(raw_event: dict) -> dict:
    intel: dict = {}

    if ip := raw_event.get("src_ip"):
        intel["ip_reputation"] = await _lookup_ip_reputation(ip)

    if file_hash := raw_event.get("file_hash"):
        intel["file_reputation"] = await _lookup_file_hash(file_hash)

    if host_id := raw_event.get("host_id"):
        intel["asset_context"] = await _lookup_asset_criticality(host_id)

    return intel


async def _lookup_ip_reputation(ip: str) -> dict:
    # Example shape -- replace with a real call to your threat intel provider.
    # async with httpx.AsyncClient(timeout=5.0) as client:
    #     resp = await client.get(f"https://your-ti-provider/api/ip/{ip}", headers={"x-api-key": "..."})
    #     return resp.json()
    return {"ip": ip, "reputation": "unknown", "source": "stub"}


async def _lookup_file_hash(file_hash: str) -> dict:
    return {"hash": file_hash, "known_malicious": False, "source": "stub"}


async def _lookup_asset_criticality(host_id: str) -> dict:
    return {"host_id": host_id, "criticality": "unknown", "source": "stub"}
