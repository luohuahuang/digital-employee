"""Agent CRUD API endpoints."""
import json
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from web.db.database import get_db
from web.db.models import Agent, Conversation

router = APIRouter(prefix="/agents", tags=["agents"])


VALID_RANKINGS = {"Intern", "Junior", "Senior", "Lead"}


class AgentCreate(BaseModel):
    name: str
    product_line: str
    avatar_emoji: str = "🤖"
    description: str = ""
    specialization: str = ""
    default_jira_project: str = ""
    confluence_spaces: list[str] = []
    ranking: str = "Intern"
    role: str = "QA"


class AgentUpdate(BaseModel):
    name: str | None = None
    product_line: str | None = None
    avatar_emoji: str | None = None
    description: str | None = None
    specialization: str | None = None
    default_jira_project: str | None = None
    confluence_spaces: list[str] | None = None
    ranking: str | None = None
    role: str | None = None
    is_active: bool | None = None


def _agent_to_dict(agent: Agent) -> dict:
    return {
        "id": agent.id,
        "name": agent.name,
        "product_line": agent.product_line,
        "avatar_emoji": agent.avatar_emoji,
        "description": agent.description,
        "specialization": agent.specialization,
        "default_jira_project": agent.default_jira_project,
        "confluence_spaces": json.loads(agent.confluence_spaces or "[]"),
        "ranking": agent.ranking or "Intern",
        "role": agent.role or "QA",
        "created_at": agent.created_at.isoformat() + "Z" if agent.created_at else None,
        "offboarded_at": agent.offboarded_at.isoformat() + "Z" if agent.offboarded_at else None,
        "is_active": agent.is_active,
    }


@router.get("")
def list_agents(db: Session = Depends(get_db)):
    """Return only active (non-offboarded) agents."""
    agents = db.query(Agent).filter(Agent.is_active == True).order_by(Agent.created_at).all()
    return [_agent_to_dict(a) for a in agents]


# NOTE: /offboarded must be declared BEFORE /{agent_id} to avoid route conflict.
@router.get("/offboarded")
def list_offboarded(db: Session = Depends(get_db)):
    """Return all offboarded agents, newest first."""
    agents = (
        db.query(Agent)
        .filter(Agent.is_active == False)
        .order_by(Agent.offboarded_at.desc())
        .all()
    )
    return [_agent_to_dict(a) for a in agents]


@router.post("", status_code=201)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    if payload.ranking not in VALID_RANKINGS:
        raise HTTPException(400, f"ranking must be one of {sorted(VALID_RANKINGS)}")
    agent = Agent(
        id=str(uuid.uuid4()),
        name=payload.name,
        product_line=payload.product_line,
        avatar_emoji=payload.avatar_emoji,
        description=payload.description,
        specialization=payload.specialization,
        default_jira_project=payload.default_jira_project,
        confluence_spaces=json.dumps(payload.confluence_spaces),
        ranking=payload.ranking,
        role=payload.role,
        created_at=datetime.utcnow(),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return _agent_to_dict(agent)


@router.get("/{agent_id}")
def get_agent(agent_id: str, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")
    return _agent_to_dict(agent)


@router.put("/{agent_id}")
def update_agent(agent_id: str, payload: AgentUpdate, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        if field == "confluence_spaces":
            setattr(agent, field, json.dumps(value))
        else:
            setattr(agent, field, value)
    db.commit()
    db.refresh(agent)
    return _agent_to_dict(agent)


@router.patch("/{agent_id}/offboard", status_code=200)
def offboard_agent(agent_id: str, db: Session = Depends(get_db)):
    """Soft-delete: mark agent as inactive, record offboarded_at timestamp."""
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.is_active == True).first()
    if not agent:
        raise HTTPException(404, "Active agent not found")
    agent.is_active = False
    agent.offboarded_at = datetime.utcnow()
    db.commit()
    db.refresh(agent)
    return _agent_to_dict(agent)


@router.delete("/{agent_id}", status_code=204)
def delete_agent(agent_id: str, db: Session = Depends(get_db)):
    """Hard delete — only used to permanently remove an offboarded agent."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")
    db.delete(agent)
    db.commit()


@router.patch("/{agent_id}/ranking")
def update_ranking(agent_id: str, body: dict, db: Session = Depends(get_db)):
    ranking = body.get("ranking", "")
    if ranking not in VALID_RANKINGS:
        raise HTTPException(400, f"ranking must be one of {sorted(VALID_RANKINGS)}")
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")
    agent.ranking = ranking
    db.commit()
    db.refresh(agent)
    return _agent_to_dict(agent)


@router.get("/{agent_id}/conversations")
def list_conversations(agent_id: str, db: Session = Depends(get_db)):
    convs = (
        db.query(Conversation)
        .filter(Conversation.agent_id == agent_id)
        .order_by(Conversation.created_at.desc())
        .all()
    )
    return [{"id": c.id, "title": c.title, "created_at": c.created_at.isoformat() + "Z"} for c in convs]
