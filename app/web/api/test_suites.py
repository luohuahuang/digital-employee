"""
Test Suite API endpoints.

Endpoints:
---------
GET    /agents/{agent_id}/test-suites              — list suites for agent
POST   /agents/{agent_id}/test-suites              — create suite with cases
GET    /test-suites/{suite_id}                     — get suite with all cases
PUT    /test-suites/{suite_id}                     — update suite metadata
DELETE /test-suites/{suite_id}                     — delete suite + its cases
POST   /test-suites/{suite_id}/cases               — add a case to suite
PUT    /test-suites/{suite_id}/cases/{case_id}     — update a case
DELETE /test-suites/{suite_id}/cases/{case_id}     — delete a case
GET    /test-suites/{suite_id}/export/markdown     — markdown export
GET    /test-suites/{suite_id}/export/xmind        — XMind file export
"""
import json
import io
import zipfile
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from web.db.database import get_db
from web.db.models import TestSuite, TestCase, Agent

router = APIRouter(tags=["test_suites"])


# ── Pydantic Models ────────────────────────────────────────────────────────────

class TestCaseInput(BaseModel):
    title: str
    category: str = ""
    preconditions: str = ""
    steps: list[str]
    expected: str
    priority: str = "P1"


class TestSuiteCreateInput(BaseModel):
    name: str
    description: str = ""
    component: str = ""
    source_type: str = "manual"
    source_ref: str = ""
    jira_key: str = ""
    cases: list[TestCaseInput]


class TestCaseOutput(BaseModel):
    id: str
    title: str
    category: str
    preconditions: str
    steps: list[str]
    expected: str
    priority: str
    order_index: int
    created_at: str
    updated_at: str


class TestSuiteOutput(BaseModel):
    id: str
    agent_id: str
    agent_name: str
    name: str
    description: str
    component: str
    source_type: str
    source_ref: str
    jira_key: str
    case_count: int
    created_at: str
    updated_at: str


class TestSuiteDetailOutput(TestSuiteOutput):
    cases: list[TestCaseOutput]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _case_to_dict(c: TestCase) -> dict:
    """Convert TestCase model to dict."""
    try:
        steps = json.loads(c.steps) if c.steps and isinstance(c.steps, str) else c.steps or []
    except Exception:
        steps = []
    return {
        "id": c.id,
        "title": c.title,
        "category": c.category,
        "preconditions": c.preconditions,
        "steps": steps,
        "expected": c.expected,
        "priority": c.priority,
        "order_index": c.order_index,
        "created_at": c.created_at.isoformat() + "Z" if c.created_at else None,
        "updated_at": c.updated_at.isoformat() + "Z" if c.updated_at else None,
    }


def _suite_to_dict(s: TestSuite, include_cases: bool = False) -> dict:
    """Convert TestSuite model to dict."""
    result = {
        "id": s.id,
        "agent_id": s.agent_id,
        "agent_name": s.agent_name,
        "name": s.name,
        "description": s.description,
        "component": getattr(s, "component", "") or "",
        "source_type": s.source_type,
        "source_ref": s.source_ref,
        "jira_key": s.jira_key,
        "case_count": len(s.__dict__.get("_cases", [])),
        "created_at": s.created_at.isoformat() + "Z" if s.created_at else None,
        "updated_at": s.updated_at.isoformat() + "Z" if s.updated_at else None,
    }
    return result


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/test-suites")
def list_all_suites(
    component: str = Query(None),
    source_type: str = Query(None),
    search: str = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """List all test suites across all agents, with optional filters."""
    q = db.query(TestSuite).order_by(desc(TestSuite.created_at))
    if component:
        q = q.filter(TestSuite.component == component)
    if source_type:
        q = q.filter(TestSuite.source_type == source_type)
    if search:
        q = q.filter(TestSuite.name.ilike(f"%{search}%"))
    suites = q.limit(limit).all()
    result = []
    for s in suites:
        case_count = db.query(TestCase).filter(TestCase.suite_id == s.id).count()
        d = _suite_to_dict(s)
        d["case_count"] = case_count
        result.append(d)
    return result


@router.get("/test-suites/components")
def list_components(db: Session = Depends(get_db)):
    """Return sorted list of distinct non-empty component values."""
    from sqlalchemy import distinct
    rows = db.query(distinct(TestSuite.component)).filter(
        TestSuite.component != None, TestSuite.component != ""
    ).all()
    return sorted([r[0] for r in rows if r[0]])


@router.get("/agents/{agent_id}/test-suites")
def list_suites(
    agent_id: str,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """List test suites for an agent (newest first)."""
    suites = (
        db.query(TestSuite)
        .filter(TestSuite.agent_id == agent_id)
        .order_by(desc(TestSuite.created_at))
        .limit(limit)
        .all()
    )
    # Compute case counts
    result = []
    for s in suites:
        case_count = db.query(TestCase).filter(TestCase.suite_id == s.id).count()
        suite_dict = _suite_to_dict(s)
        suite_dict["case_count"] = case_count
        result.append(suite_dict)
    return result


@router.post("/agents/{agent_id}/test-suites", status_code=201)
def create_suite(
    agent_id: str,
    body: TestSuiteCreateInput,
    db: Session = Depends(get_db),
):
    """Create a new test suite with cases."""
    import uuid

    # Verify agent exists
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    # Create suite
    suite_id = str(uuid.uuid4())
    suite = TestSuite(
        id=suite_id,
        agent_id=agent_id,
        agent_name=agent.name,
        name=body.name,
        description=body.description,
        component=body.component,
        source_type=body.source_type,
        source_ref=body.source_ref,
        jira_key=body.jira_key,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(suite)
    db.flush()

    # Create cases
    case_count = 0
    for i, case_input in enumerate(body.cases):
        case_id = str(uuid.uuid4())
        case = TestCase(
            id=case_id,
            suite_id=suite_id,
            title=case_input.title,
            category=case_input.category,
            preconditions=case_input.preconditions,
            steps=json.dumps(case_input.steps, ensure_ascii=False),
            expected=case_input.expected,
            priority=case_input.priority,
            order_index=i,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(case)
        case_count += 1

    db.commit()
    db.refresh(suite)

    return {
        **_suite_to_dict(suite),
        "case_count": case_count,
    }


@router.get("/test-suites/{suite_id}")
def get_suite(suite_id: str, db: Session = Depends(get_db)):
    """Get a suite with all its test cases."""
    suite = db.query(TestSuite).filter(TestSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(404, "Suite not found")

    cases = db.query(TestCase).filter(TestCase.suite_id == suite_id).order_by(TestCase.order_index).all()

    result = _suite_to_dict(suite)
    result["case_count"] = len(cases)
    result["cases"] = [_case_to_dict(c) for c in cases]

    return result


@router.put("/test-suites/{suite_id}")
def update_suite(
    suite_id: str,
    body: dict,
    db: Session = Depends(get_db),
):
    """Update suite metadata (name, description)."""
    suite = db.query(TestSuite).filter(TestSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(404, "Suite not found")

    if "name" in body:
        suite.name = body["name"]
    if "description" in body:
        suite.description = body["description"]

    suite.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(suite)

    cases = db.query(TestCase).filter(TestCase.suite_id == suite_id).all()
    result = _suite_to_dict(suite)
    result["case_count"] = len(cases)

    return result


@router.delete("/test-suites/{suite_id}", status_code=204)
def delete_suite(suite_id: str, db: Session = Depends(get_db)):
    """Delete a suite and all its cases."""
    suite = db.query(TestSuite).filter(TestSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(404, "Suite not found")

    # Delete all cases
    db.query(TestCase).filter(TestCase.suite_id == suite_id).delete()

    # Delete suite
    db.delete(suite)
    db.commit()


@router.post("/test-suites/{suite_id}/cases")
def add_case(
    suite_id: str,
    body: TestCaseInput,
    db: Session = Depends(get_db),
):
    """Add a test case to a suite."""
    import uuid

    suite = db.query(TestSuite).filter(TestSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(404, "Suite not found")

    # Get max order_index
    max_order = db.query(TestCase.order_index).filter(TestCase.suite_id == suite_id).order_by(TestCase.order_index.desc()).first()
    next_order = (max_order[0] + 1) if max_order and max_order[0] is not None else 0

    case_id = str(uuid.uuid4())
    case = TestCase(
        id=case_id,
        suite_id=suite_id,
        title=body.title,
        category=body.category,
        preconditions=body.preconditions,
        steps=json.dumps(body.steps, ensure_ascii=False),
        expected=body.expected,
        priority=body.priority,
        order_index=next_order,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(case)
    db.commit()
    db.refresh(case)

    return _case_to_dict(case)


@router.put("/test-suites/{suite_id}/cases/{case_id}")
def update_case(
    suite_id: str,
    case_id: str,
    body: dict,
    db: Session = Depends(get_db),
):
    """Update a test case."""
    case = db.query(TestCase).filter(
        TestCase.id == case_id,
        TestCase.suite_id == suite_id,
    ).first()
    if not case:
        raise HTTPException(404, "Case not found")

    if "title" in body:
        case.title = body["title"]
    if "category" in body:
        case.category = body["category"]
    if "preconditions" in body:
        case.preconditions = body["preconditions"]
    if "steps" in body:
        case.steps = json.dumps(body["steps"], ensure_ascii=False)
    if "expected" in body:
        case.expected = body["expected"]
    if "priority" in body:
        case.priority = body["priority"]

    case.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(case)

    return _case_to_dict(case)


@router.delete("/test-suites/{suite_id}/cases/{case_id}", status_code=204)
def delete_case(
    suite_id: str,
    case_id: str,
    db: Session = Depends(get_db),
):
    """Delete a test case."""
    case = db.query(TestCase).filter(
        TestCase.id == case_id,
        TestCase.suite_id == suite_id,
    ).first()
    if not case:
        raise HTTPException(404, "Case not found")

    db.delete(case)
    db.commit()


@router.get("/test-suites/{suite_id}/export/markdown")
def export_markdown(suite_id: str, db: Session = Depends(get_db)):
    """Export suite as markdown text."""
    from fastapi.responses import PlainTextResponse

    suite = db.query(TestSuite).filter(TestSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(404, "Suite not found")

    cases = db.query(TestCase).filter(TestCase.suite_id == suite_id).order_by(TestCase.order_index).all()

    # Build markdown
    lines = [f"# {suite.name}"]
    if suite.source_ref or suite.jira_key:
        sources = []
        if suite.source_ref:
            sources.append(f"Source: {suite.source_ref}")
        if suite.jira_key:
            sources.append(f"Jira: {suite.jira_key}")
        lines.append(" | ".join(sources))
    lines.append("")

    if suite.description:
        lines.append(f"{suite.description}")
        lines.append("")

    # Group cases by category
    by_category = {}
    for case in cases:
        cat = case.category or "General"
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(case)

    for category in sorted(by_category.keys()):
        lines.append(f"## {category}")
        lines.append("")

        for case in by_category[category]:
            # Extract steps
            try:
                steps = json.loads(case.steps) if isinstance(case.steps, str) else case.steps or []
            except Exception:
                steps = []

            lines.append(f"### TC-{case.order_index + 1:03d} [{case.priority}] {case.title}")
            if case.preconditions:
                lines.append(f"**Preconditions:** {case.preconditions}")
            lines.append("**Steps:**")
            for i, step in enumerate(steps, 1):
                lines.append(f"{i}. {step}")
            lines.append(f"**Expected:** {case.expected}")
            lines.append("")

    content = "\n".join(lines)
    return PlainTextResponse(content, media_type="text/markdown")


@router.get("/test-suites/{suite_id}/export/xmind")
def export_xmind(suite_id: str, db: Session = Depends(get_db)):
    """Export suite as XMind file."""
    from fastapi.responses import StreamingResponse

    suite = db.query(TestSuite).filter(TestSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(404, "Suite not found")

    cases = db.query(TestCase).filter(TestCase.suite_id == suite_id).order_by(TestCase.order_index).all()

    # Group by category
    by_category = {}
    for case in cases:
        cat = case.category or "General"
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(case)

    # Build XMind structure
    children_attached = []
    for category in sorted(by_category.keys()):
        category_node = {
            "id": f"cat-{len(children_attached)}",
            "title": category,
            "children": {
                "attached": []
            }
        }

        for case in by_category[category]:
            try:
                steps = json.loads(case.steps) if isinstance(case.steps, str) else case.steps or []
            except Exception:
                steps = []

            # Format steps + expected as note
            note_lines = [f"Steps: {', '.join(steps[:3])}"] if steps else []
            if case.expected:
                note_lines.append(f"Expected: {case.expected}")
            note = "\n".join(note_lines)

            case_node = {
                "id": f"tc-{case.id[:8]}",
                "title": f"{case.priority} {case.title}",
                "note": note or "No details"
            }
            category_node["children"]["attached"].append(case_node)

        children_attached.append(category_node)

    # XMind root structure
    root_topic = {
        "id": "root",
        "title": suite.name,
        "children": {
            "attached": children_attached
        }
    }

    sheet = {
        "id": "root-sheet",
        "title": "Sheet 1",
        "rootTopic": root_topic
    }

    # Create in-memory ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        # content.json
        content_data = [sheet]
        z.writestr("content.json", json.dumps(content_data, ensure_ascii=False, indent=2))

        # metadata.json
        metadata = {
            "creator": {
                "name": "Digital QA Employee",
                "version": "2.0"
            }
        }
        z.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))

    zip_buffer.seek(0)

    filename = f"{suite.name.replace(' ', '_')}.xmind"
    return StreamingResponse(
        iter([zip_buffer.getvalue()]),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
