"""Snapshot every read-only API response into ui/mock/, so the workbench runs without data or a graph.

    python scripts/snapshot_api.py      # then: cd ui && npm run dev:mock

The real backend needs the dataset, the traces in runs/ and a TigerGraph workspace, none of which are
in git. This calls each GET endpoint through the FastAPI app in-process and writes the JSON it returns
to ui/mock/api/<path>.json, which `vite --mode mock` serves. Writes (approvals, challenges, a live
investigation) are refused in mock mode rather than faked.
"""

import json

from fastapi.testclient import TestClient

from redthread import paths
from redthread.api.app import app

OUT = paths.ROOT / "ui" / "mock" / "api"


def save(client: TestClient, path: str) -> dict | list | None:
    r = client.get(path)
    if r.status_code != 200:
        print(f"skip {path}: {r.status_code}")
        return None
    target = OUT / (path.removeprefix("/api/") + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(r.json(), separators=(",", ":")), encoding="utf-8")
    return r.json()


def main() -> None:
    client = TestClient(app)
    cases = save(client, "/api/cases") or []
    for c in cases:
        cid = c["case_id"]
        for suffix in ("", "/replay", "/handover", "/challenges"):
            save(client, f"/api/cases/{cid}{suffix}")
    for path in ("/api/overview", "/api/monitoring", "/api/containment", "/api/evaluation", "/api/policy",
                 "/api/approvals/verify"):
        save(client, path)
    rings = save(client, "/api/rings") or {}
    for ring in rings.get("rings", []):
        save(client, f"/api/rings/{ring['ring_id']}")
    files = list(OUT.rglob("*.json"))
    print(f"{len(files)} responses, {sum(f.stat().st_size for f in files) / 1e6:.1f} MB in {OUT}")


if __name__ == "__main__":
    main()
