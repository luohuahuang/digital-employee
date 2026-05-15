"""Permission configuration API.

Manages two configurable permission tables:
  - tool_risk_config: per-tool risk level (L1 / L2 / L3)
  - ranking_ceiling_config: per-ranking max auto-execute level (L1 / L2 / L3)

These replace the hardcoded TOOL_RISK_LEVEL dict in config.py and
_RANKING_CEILING dict in agent.py at runtime.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from web.db.database import get_db
from web.db.models import ToolRiskConfig, RankingCeilingConfig

router = APIRouter(tags=["permissions"])

VALID_LEVELS = {"L1", "L2", "L3"}

# Friendly display names for tools shown in the UI
TOOL_DISPLAY = {
    "read_requirement_doc":  "Read Requirement Doc",
    "search_knowledge_base": "Search Knowledge Base",
    "write_output_file":     "Write Output File",
    "search_confluence":     "Search Confluence",
    "search_jira":           "Search Jira",
    "get_jira_issue":        "Get Jira Issue",
    "get_gitlab_mr_diff":    "Get GitLab MR Diff",
    "save_to_memory":        "Save to Memory",
    "create_defect_mock":    "Create Defect (Mock)",
    "save_confluence_page":  "Save Confluence Page",
    "merge_branch_to_main":  "Merge Branch KB → Main",
}

_CEILING_DEFAULTS = {"Intern": "L1", "Junior": "L1", "Senior": "L2", "Lead": "L3"}


def _ensure_tools(db: Session):
    """Seed any tool rows that are missing (e.g. after a new tool is added to config.py)."""
    from config import TOOL_RISK_LEVEL
    existing = {r.tool_name for r in db.query(ToolRiskConfig).all()}
    for tool, level in TOOL_RISK_LEVEL.items():
        if tool not in existing:
            db.add(ToolRiskConfig(tool_name=tool, risk_level=level, updated_at=datetime.utcnow()))
    db.commit()


def _ensure_rankings(db: Session):
    """Seed any ranking rows that are missing."""
    existing = {r.ranking for r in db.query(RankingCeilingConfig).all()}
    for ranking, ceiling in _CEILING_DEFAULTS.items():
        if ranking not in existing:
            db.add(RankingCeilingConfig(ranking=ranking, ceiling=ceiling, updated_at=datetime.utcnow()))
    db.commit()


@router.get("/permissions")
def get_permissions(db: Session = Depends(get_db)):
    """Return full permission config: tool risk levels + ranking ceilings."""
    _ensure_tools(db)
    _ensure_rankings(db)

    tools = [
        {
            "tool_name":    r.tool_name,
            "display_name": TOOL_DISPLAY.get(r.tool_name, r.tool_name),
            "risk_level":   r.risk_level,
            "updated_at":   r.updated_at.isoformat() + "Z" if r.updated_at else None,
        }
        for r in db.query(ToolRiskConfig).order_by(ToolRiskConfig.tool_name).all()
    ]

    rankings = [
        {
            "ranking":    r.ranking,
            "ceiling":    r.ceiling,
            "updated_at": r.updated_at.isoformat() + "Z" if r.updated_at else None,
        }
        for r in db.query(RankingCeilingConfig).all()
    ]

    return {"tools": tools, "rankings": rankings}


@router.put("/permissions/tools/{tool_name}")
def update_tool_risk(tool_name: str, body: dict, db: Session = Depends(get_db)):
    """Update the risk level of a single tool."""
    level = (body.get("risk_level") or "").upper()
    if level not in VALID_LEVELS:
        raise HTTPException(400, f"risk_level must be one of {VALID_LEVELS}")

    row = db.query(ToolRiskConfig).filter(ToolRiskConfig.tool_name == tool_name).first()
    if not row:
        raise HTTPException(404, f"Tool '{tool_name}' not found in permission config")
    row.risk_level = level
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"tool_name": tool_name, "risk_level": level}


@router.put("/permissions/rankings/{ranking}")
def update_ranking_ceiling(ranking: str, body: dict, db: Session = Depends(get_db)):
    """Update the permission ceiling of a ranking tier."""
    ceiling = (body.get("ceiling") or "").upper()
    if ceiling not in VALID_LEVELS:
        raise HTTPException(400, f"ceiling must be one of {VALID_LEVELS}")

    row = db.query(RankingCeilingConfig).filter(RankingCeilingConfig.ranking == ranking).first()
    if not row:
        raise HTTPException(404, f"Ranking '{ranking}' not found in permission config")
    row.ceiling = ceiling
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"ranking": ranking, "ceiling": ceiling}


@router.post("/permissions/reset")
def reset_permissions(db: Session = Depends(get_db)):
    """Reset all permission configs to built-in defaults."""
    from config import TOOL_RISK_LEVEL

    for tool, level in TOOL_RISK_LEVEL.items():
        row = db.query(ToolRiskConfig).filter(ToolRiskConfig.tool_name == tool).first()
        if row:
            row.risk_level = level
            row.updated_at = datetime.utcnow()

    for ranking, ceiling in _CEILING_DEFAULTS.items():
        row = db.query(RankingCeilingConfig).filter(RankingCeilingConfig.ranking == ranking).first()
        if row:
            row.ceiling = ceiling
            row.updated_at = datetime.utcnow()

    db.commit()
    return {"status": "reset"}
