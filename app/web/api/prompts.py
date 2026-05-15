"""
Prompt Version Management API.

Supports two prompt types per agent:
  - "base"           : core system prompt (identity, permissions, behaviors)
  - "specialization" : domain-specific knowledge appended at runtime

Each type is versioned independently; only one version per type is active.

Endpoints:
  GET  /agents/{id}/prompts               — list versions (?type=base|specialization)
  GET  /agents/{id}/prompts/active        — get active version content
  POST /agents/{id}/prompts               — save new version (becomes active)
  POST /agents/{id}/prompts/{vid}/activate — rollback to a previous version
"""
import uuid
from datetime import datetime
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from web.db.database import get_db
from web.db.models import Agent, PromptVersion, ExamRun

router = APIRouter(tags=["prompts"])

VALID_TYPES = {"base", "specialization"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _exam_stats_by_version(agent_id: str, db: Session) -> dict[str, dict]:
    """Return {version_id: {runs, passed, pass_rate}} for all versions of an agent."""
    runs = (
        db.query(ExamRun)
        .filter(
            ExamRun.agent_id == agent_id,
            ExamRun.status == "done",
            ExamRun.prompt_version_id.isnot(None),
        )
        .all()
    )
    stats: dict[str, dict] = defaultdict(lambda: {"runs": 0, "passed": 0})
    for r in runs:
        s = stats[r.prompt_version_id]
        s["runs"] += 1
        if r.passed:
            s["passed"] += 1
    for s in stats.values():
        s["pass_rate"] = round(s["passed"] / s["runs"], 3) if s["runs"] else None
    return stats


def _version_to_dict(v: PromptVersion, stats: dict) -> dict:
    s = stats.get(v.id, {})
    return {
        "id":          v.id,
        "type":        v.type or "base",
        "version":     v.version,
        "note":        v.note or "",
        "is_active":   v.is_active,
        "created_at":  v.created_at.isoformat() + "Z" if v.created_at else None,
        "exam_runs":   s.get("runs", 0),
        "exam_passed": s.get("passed", 0),
        "pass_rate":   s.get("pass_rate"),
    }


def _ensure_v1(agent_id: str, prompt_type: str, db: Session) -> PromptVersion:
    """Ensure agent has at least v1 for the given type. Seeds from defaults if missing."""
    existing = (
        db.query(PromptVersion)
        .filter(PromptVersion.agent_id == agent_id, PromptVersion.type == prompt_type)
        .first()
    )
    if existing:
        return existing

    if prompt_type == "base":
        # Use the role-specific template from the DB (or fall back to built-in defaults)
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        role  = (agent.role or "QA") if agent else "QA"
        try:
            from web.db.models import RolePromptTemplate
            tpl = db.query(RolePromptTemplate).filter(RolePromptTemplate.role == role).first()
            content = tpl.content if (tpl and tpl.content.strip()) else None
        except Exception:
            content = None
        if not content:
            from agent.prompts import ROLE_PROMPTS
            content = ROLE_PROMPTS.get(role, ROLE_PROMPTS["QA"])
        note = f"Initial version (seeded from {role} role template)"
    else:
        # Seed specialization from the agent's existing specialization field
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        content = (agent.specialization or "") if agent else ""
        note = "Initial version (seeded from agent specialization field)"

    v1 = PromptVersion(
        id=str(uuid.uuid4()),
        agent_id=agent_id,
        type=prompt_type,
        version=1,
        content=content,
        note=note,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(v1)
    db.commit()
    db.refresh(v1)
    return v1


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/agents/{agent_id}/prompts")
def list_versions(
    agent_id: str,
    type: str = Query("base"),
    db: Session = Depends(get_db),
):
    if type not in VALID_TYPES:
        raise HTTPException(400, f"type must be one of: {', '.join(VALID_TYPES)}")
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    _ensure_v1(agent_id, type, db)

    versions = (
        db.query(PromptVersion)
        .filter(PromptVersion.agent_id == agent_id, PromptVersion.type == type)
        .order_by(PromptVersion.version.desc())
        .all()
    )
    stats = _exam_stats_by_version(agent_id, db)
    return [_version_to_dict(v, stats) for v in versions]


@router.get("/agents/{agent_id}/prompts/active")
def get_active(
    agent_id: str,
    type: str = Query("base"),
    db: Session = Depends(get_db),
):
    if type not in VALID_TYPES:
        raise HTTPException(400, f"type must be one of: {', '.join(VALID_TYPES)}")
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    v = _ensure_v1(agent_id, type, db)
    active = (
        db.query(PromptVersion)
        .filter(
            PromptVersion.agent_id == agent_id,
            PromptVersion.type == type,
            PromptVersion.is_active == True,
        )
        .first()
    )
    if active:
        v = active
    return {
        "id":         v.id,
        "type":       v.type or type,
        "version":    v.version,
        "content":    v.content,
        "note":       v.note or "",
        "is_active":  v.is_active,
        "created_at": v.created_at.isoformat() + "Z" if v.created_at else None,
    }


class SaveRequest(BaseModel):
    content: str
    note: str = ""
    type: str = "base"


@router.post("/agents/{agent_id}/prompts", status_code=201)
def save_version(agent_id: str, body: SaveRequest, db: Session = Depends(get_db)):
    """Save new version and make it active."""
    if body.type not in VALID_TYPES:
        raise HTTPException(400, f"type must be one of: {', '.join(VALID_TYPES)}")
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    prompt_type = body.type

    # Deactivate current active version of this type
    db.query(PromptVersion).filter(
        PromptVersion.agent_id == agent_id,
        PromptVersion.type == prompt_type,
        PromptVersion.is_active == True,
    ).update({"is_active": False})

    # Next version number for this type
    count = db.query(PromptVersion).filter(
        PromptVersion.agent_id == agent_id,
        PromptVersion.type == prompt_type,
    ).count()

    new_ver = PromptVersion(
        id=str(uuid.uuid4()),
        agent_id=agent_id,
        type=prompt_type,
        version=count + 1,
        content=body.content.strip(),
        note=body.note.strip(),
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(new_ver)

    # Keep agent.specialization in sync for backward compat (terminal mode)
    if prompt_type == "specialization":
        agent.specialization = body.content.strip()

    db.commit()
    db.refresh(new_ver)
    stats = _exam_stats_by_version(agent_id, db)
    return _version_to_dict(new_ver, stats)


@router.post("/agents/{agent_id}/prompts/{version_id}/activate", status_code=200)
def activate_version(agent_id: str, version_id: str, db: Session = Depends(get_db)):
    """Roll back to a previous version."""
    ver = db.query(PromptVersion).filter(
        PromptVersion.id == version_id,
        PromptVersion.agent_id == agent_id,
    ).first()
    if not ver:
        raise HTTPException(404, "Version not found")

    prompt_type = ver.type or "base"
    db.query(PromptVersion).filter(
        PromptVersion.agent_id == agent_id,
        PromptVersion.type == prompt_type,
        PromptVersion.is_active == True,
    ).update({"is_active": False})

    ver.is_active = True

    # Keep agent.specialization in sync
    if prompt_type == "specialization":
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if agent:
            agent.specialization = ver.content

    db.commit()
    stats = _exam_stats_by_version(agent_id, db)
    return _version_to_dict(ver, stats)
