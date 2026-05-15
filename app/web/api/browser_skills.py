"""
Browser Skills API — CRUD for test execution skills.

Endpoints:
----------
GET    /browser-skills               — list all (optional ?type=environment|extra)
POST   /browser-skills               — create
GET    /browser-skills/{id}          — get one
PUT    /browser-skills/{id}          — update
DELETE /browser-skills/{id}          — delete
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from web.db.database import engine

router = APIRouter(tags=["browser_skills"])


def _now():
    return datetime.now(timezone.utc).isoformat()


class SkillPayload(BaseModel):
    name: str
    skill_type: str   # "environment" | "extra"
    content: str


@router.get("/browser-skills")
def list_skills(type: str = None):
    with engine.connect() as conn:
        if type:
            rows = conn.execute(
                text("SELECT * FROM browser_skills WHERE skill_type=:t ORDER BY name"),
                {"t": type},
            ).mappings().fetchall()
        else:
            rows = conn.execute(
                text("SELECT * FROM browser_skills ORDER BY skill_type, name")
            ).mappings().fetchall()
    return [dict(r) for r in rows]


@router.post("/browser-skills")
def create_skill(body: SkillPayload):
    if body.skill_type not in ("environment", "extra"):
        raise HTTPException(status_code=400, detail="skill_type must be 'environment' or 'extra'")
    new_id = str(uuid.uuid4())
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO browser_skills (id, name, skill_type, content, created_at, updated_at)
                VALUES (:id, :name, :type, :content, :now, :now)
            """),
            {"id": new_id, "name": body.name, "type": body.skill_type,
             "content": body.content, "now": now},
        )
    return {"id": new_id}


@router.get("/browser-skills/{skill_id}")
def get_skill(skill_id: str):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM browser_skills WHERE id=:id"), {"id": skill_id}
        ).mappings().fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Skill not found")
    return dict(row)


@router.put("/browser-skills/{skill_id}")
def update_skill(skill_id: str, body: SkillPayload):
    if body.skill_type not in ("environment", "extra"):
        raise HTTPException(status_code=400, detail="skill_type must be 'environment' or 'extra'")
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE browser_skills
                SET name=:name, skill_type=:type, content=:content, updated_at=:now
                WHERE id=:id
            """),
            {"name": body.name, "type": body.skill_type,
             "content": body.content, "now": _now(), "id": skill_id},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Skill not found")
    return {"ok": True}


@router.delete("/browser-skills/{skill_id}")
def delete_skill(skill_id: str):
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM browser_skills WHERE id=:id"), {"id": skill_id}
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Skill not found")
    return {"ok": True}
