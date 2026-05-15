"""
Role Prompt Template API.

One editable base-prompt template per role (QA / Dev / PM / SRE / PJ).
These templates are used to seed the base prompt of newly onboarded agents.

Endpoints:
  GET  /role-prompts          — list all 5 role templates (auto-seeds defaults if missing)
  GET  /role-prompts/{role}   — get single template
  PUT  /role-prompts/{role}   — update template content
  POST /role-prompts/{role}/reset — reset to built-in default
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from web.db.database import get_db
from web.db.models import RolePromptTemplate

router = APIRouter(tags=["role-prompts"])

ROLES = ["QA", "Dev", "PM", "SRE", "PJ"]


def _get_default(role: str) -> str:
    from agent.prompts import ROLE_PROMPTS
    return ROLE_PROMPTS.get(role, "")


def _ensure_all(db: Session):
    """Seed any missing role rows from built-in defaults."""
    existing = {r.role for r in db.query(RolePromptTemplate).all()}
    for role in ROLES:
        if role not in existing:
            db.add(RolePromptTemplate(
                role=role,
                content=_get_default(role),
                updated_at=datetime.utcnow(),
            ))
    db.commit()


def _to_dict(t: RolePromptTemplate) -> dict:
    return {
        "role":       t.role,
        "content":    t.content,
        "updated_at": t.updated_at.isoformat() + "Z" if t.updated_at else None,
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/role-prompts")
def list_role_prompts(db: Session = Depends(get_db)):
    _ensure_all(db)
    rows = db.query(RolePromptTemplate).order_by(RolePromptTemplate.role).all()
    # Return in the canonical ROLES order
    by_role = {r.role: r for r in rows}
    return [_to_dict(by_role[role]) for role in ROLES if role in by_role]


@router.get("/role-prompts/{role}")
def get_role_prompt(role: str, db: Session = Depends(get_db)):
    if role not in ROLES:
        raise HTTPException(400, f"role must be one of: {', '.join(ROLES)}")
    _ensure_all(db)
    row = db.query(RolePromptTemplate).filter(RolePromptTemplate.role == role).first()
    return _to_dict(row)


class UpdateRequest(BaseModel):
    content: str


@router.put("/role-prompts/{role}")
def update_role_prompt(role: str, body: UpdateRequest, db: Session = Depends(get_db)):
    if role not in ROLES:
        raise HTTPException(400, f"role must be one of: {', '.join(ROLES)}")
    _ensure_all(db)
    row = db.query(RolePromptTemplate).filter(RolePromptTemplate.role == role).first()
    row.content    = body.content.strip()
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _to_dict(row)


@router.post("/role-prompts/{role}/reset")
def reset_role_prompt(role: str, db: Session = Depends(get_db)):
    """Reset a role template back to the built-in default."""
    if role not in ROLES:
        raise HTTPException(400, f"role must be one of: {', '.join(ROLES)}")
    _ensure_all(db)
    row = db.query(RolePromptTemplate).filter(RolePromptTemplate.role == role).first()
    row.content    = _get_default(role)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _to_dict(row)
