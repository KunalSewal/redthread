"""Who is approving: identities the server issues, never a role the client claims.

Policy section 2 routes BLOCK_CARD, FILE_REPORT and similar actions to a team lead (L1) or fraud
manager (L2). The role used to arrive in the request body, so anyone could claim L2. Now each
approver holds a secret key; the server keeps only its SHA-256 and resolves the key to a name and a
role. A request can say *what* it decides, never *who* is deciding.

    python scripts/approvers.py add --name "Asha Rao" --role L1   # prints the key once

The keys file lives outside git (``secrets/approvers.json``, or ``REDTHREAD_APPROVERS``).
"""

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from redthread import paths

APPROVERS_ENV = "REDTHREAD_APPROVERS"
ROLES = ("L1", "L2")


@dataclass(frozen=True)
class Approver:
    id: str
    name: str
    role: str


def approvers_file() -> Path:
    return Path(os.environ.get(APPROVERS_ENV, paths.ROOT / "secrets" / "approvers.json"))


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _load() -> list[dict]:
    f = approvers_file()
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def add(name: str, role: str) -> tuple[Approver, str]:
    """Register an approver and return their key. The key is never stored, only its hash."""
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    entries = _load()
    approver = Approver(id=f"approver-{len(entries) + 1:03d}", name=name, role=role)
    key = secrets.token_urlsafe(24)
    entries.append({"id": approver.id, "name": name, "role": role, "key_sha256": _digest(key)})
    f = approvers_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return approver, key


def resolve(key: str) -> Approver | None:
    digest = _digest(key)
    for e in _load():
        if hmac.compare_digest(digest, e["key_sha256"]):  # constant time, so timing reveals nothing
            return Approver(id=e["id"], name=e["name"], role=e["role"])
    return None


def current_approver(authorization: str | None = Header(default=None)) -> Approver:
    """FastAPI dependency: the approver behind ``Authorization: Bearer <key>``, or 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "sign in with your approver key to decide on an action")
    approver = resolve(authorization.removeprefix("Bearer ").strip())
    if approver is None:
        raise HTTPException(401, "that approver key is not recognised")
    return approver


CurrentApprover = Annotated[Approver, Depends(current_approver)]
