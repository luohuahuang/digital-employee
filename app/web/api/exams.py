"""
Exam run API.

Endpoints
---------
GET    /api/exams                         — list available YAML exam files + metadata
POST   /api/exams                         — create a new exam YAML file
GET    /api/exams/{filename}              — get single exam
PUT    /api/exams/{filename}              — update exam YAML
DELETE /api/exams/{filename}              — delete exam YAML

POST /api/agents/{id}/exam-runs           — trigger run(s); returns run IDs immediately
GET  /api/agents/{id}/exam-runs           — run history for one agent
GET  /api/exam-runs/compare               — cross-agent comparison (agent_ids=a,b,c)
GET  /api/exam-runs/{run_id}              — single run (for status polling)
PATCH /api/exam-runs/{run_id}/mentor      — submit Mentor scores; recalculates total
"""
from __future__ import annotations

import json
import os
import time
import yaml
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from web.db.database import get_db, SessionLocal
from web.db.models import ExamRun, Agent, PromptVersion, PromptSuggestion

router = APIRouter(tags=["exams"])

# Resolve exams/ directory relative to this file's location
EXAMS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "exams")
)
DRAFTS_DIR = os.path.join(EXAMS_DIR, "drafts")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _list_exam_files() -> list[dict]:
    if not os.path.isdir(EXAMS_DIR):
        return []
    result = []
    for fname in sorted(os.listdir(EXAMS_DIR)):
        if not fname.endswith(".yaml"):
            continue
        try:
            with open(os.path.join(EXAMS_DIR, fname), encoding="utf-8") as f:
                data = yaml.safe_load(f)
            result.append({
                "file":             fname,
                "id":               data.get("id", fname),
                "role":             data.get("role", ""),
                "skill":            data.get("skill"),
                "difficulty":       data.get("difficulty"),
                "scenario":         data.get("scenario", ""),
                "pass_threshold":   data.get("pass_threshold", 75),
                "mentor_criteria":  data.get("mentor_criteria", []),
                "expected_keywords": data.get("expected_keywords", []),
            })
        except Exception:
            result.append({"file": fname, "id": fname, "mentor_criteria": [], "expected_keywords": []})
    return result


def _run_to_dict(r: ExamRun) -> dict:
    return {
        "id":              r.id,
        "agent_id":        r.agent_id,
        "agent_name":      r.agent_name,
        "exam_file":       r.exam_file,
        "exam_id":         r.exam_id,
        "skill":           r.skill,
        "difficulty":      r.difficulty,
        "status":          r.status,
        "auto_score":      r.auto_score,
        "auto_weight":     r.auto_weight,
        "mentor_score":    r.mentor_score,
        "mentor_weight":   r.mentor_weight,
        "total_score":     r.total_score,
        "threshold":       r.threshold,
        "passed":          r.passed,
        "missed_keywords": _safe_json(r.missed_keywords_json, []),
        "mentor_criteria":   _safe_json(r.mentor_criteria_json, []),
        "mentor_scores":     _safe_json(r.mentor_scores_json, {}),
        "prompt_version_num": r.prompt_version_num,
        "judge_results":   _safe_json(r.judge_results_json, {}),
        "rules_result":    _safe_json(r.rules_result_json, []),
        "output":          r.output,
        "elapsed_sec":     r.elapsed_sec,
        "error_msg":       r.error_msg,
        "created_at":      r.created_at.isoformat() + "Z" if r.created_at else None,
    }


def _safe_json(s, default):
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/exams")
def list_exams():
    """Return available exam YAML files with their metadata."""
    return _list_exam_files()


class RunRequest(BaseModel):
    exam_file: str  # filename (e.g. "tc_design_001.yaml") or "all"


@router.post("/agents/{agent_id}/exam-runs", status_code=201)
def start_exam_run(
    agent_id: str,
    body: RunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Create one ExamRun row per target exam (status="running") and kick off
    background tasks.  Returns immediately with the list of run IDs so the
    client can poll for status.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    # Capture active prompt version at exam run time
    active_pv = db.query(PromptVersion).filter(
        PromptVersion.agent_id == agent_id,
        PromptVersion.is_active == True,
    ).first()

    all_exams = _list_exam_files()
    if body.exam_file == "all":
        targets = all_exams
    else:
        targets = [e for e in all_exams if e["file"] == body.exam_file]
    if not targets:
        raise HTTPException(404, f"Exam not found: {body.exam_file}")

    run_ids: list[str] = []
    for meta in targets:
        run = ExamRun(
            agent_id=agent_id,
            agent_name=agent.name,
            exam_file=meta["file"],
            exam_id=meta.get("id"),
            skill=meta.get("skill"),
            difficulty=meta.get("difficulty"),
            status="running",
            mentor_criteria_json=json.dumps(meta.get("mentor_criteria", []), ensure_ascii=False),
            prompt_version_id=active_pv.id if active_pv else None,
            prompt_version_num=active_pv.version if active_pv else None,
            created_at=datetime.utcnow(),
        )
        db.add(run)
        db.flush()
        run_ids.append(run.id)
    db.commit()

    specialization = agent.specialization or ""
    agent_name = agent.name
    for run_id in run_ids:
        background_tasks.add_task(_run_exam_task, run_id, agent_id, agent_name, specialization)

    return {"run_ids": run_ids, "count": len(run_ids)}


@router.get("/agents/{agent_id}/exam-runs")
def list_agent_runs(
    agent_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    runs = (
        db.query(ExamRun)
        .filter(ExamRun.agent_id == agent_id)
        .order_by(desc(ExamRun.created_at))
        .limit(limit)
        .all()
    )
    return [_run_to_dict(r) for r in runs]


# NOTE: /compare and /version-matrix must be declared BEFORE /{run_id} to avoid
# FastAPI matching these literal strings as run_id path parameters.

@router.get("/agents/{agent_id}/exam-runs/version-matrix")
def version_matrix(agent_id: str, db: Session = Depends(get_db)):
    """
    Return a matrix of exam × prompt-version scores for one agent.

    Shape:
      {
        "versions": [1, 2, 3],
        "exams": [
          {
            "exam_id": "qa-tc-001",
            "skill": "test_case_design",
            "difficulty": "L1",
            "scores": {
              "1": {"total": 45.0, "passed": false, "run_id": "..."},
              "2": {"total": 78.0, "passed": true,  "run_id": "..."},
              "3": {"total": 95.0, "passed": true,  "run_id": "..."}
            }
          }
        ]
      }
    For each (exam, version) pair, only the most recent completed run is used.
    """
    runs = (
        db.query(ExamRun)
        .filter(
            ExamRun.agent_id == agent_id,
            ExamRun.status == "done",
            ExamRun.prompt_version_num.isnot(None),
        )
        .order_by(ExamRun.created_at)
        .all()
    )

    # latest run per (exam_id, version)
    latest: dict[tuple, ExamRun] = {}
    for r in runs:
        key = (r.exam_id, r.prompt_version_num)
        latest[key] = r  # later rows overwrite earlier ones

    versions: set[int] = set()
    exams_map: dict[str, dict] = {}
    for (exam_id, ver), r in latest.items():
        versions.add(ver)
        if exam_id not in exams_map:
            exams_map[exam_id] = {
                "exam_id":   exam_id,
                "exam_file": r.exam_file,
                "skill":     r.skill,
                "difficulty": r.difficulty,
                "scores":    {},
            }
        exams_map[exam_id]["scores"][str(ver)] = {
            "total":   r.total_score,
            "auto":    r.auto_score,
            "passed":  r.passed,
            "run_id":  r.id,
        }

    return {
        "versions": sorted(versions),
        "exams":    sorted(exams_map.values(), key=lambda x: x["exam_id"]),
    }



@router.get("/exam-runs/compare")
def compare_agents(
    agent_ids: str = Query(..., description="Comma-separated agent IDs"),
    db: Session = Depends(get_db),
):
    """Return all completed runs for the given agents (used to build comparison view)."""
    ids = [i.strip() for i in agent_ids.split(",") if i.strip()]
    rows = (
        db.query(ExamRun)
        .filter(ExamRun.agent_id.in_(ids), ExamRun.status == "done")
        .order_by(ExamRun.created_at)
        .all()
    )
    return [_run_to_dict(r) for r in rows]


@router.get("/exam-runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(ExamRun).filter(ExamRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    return _run_to_dict(run)


class MentorScores(BaseModel):
    scores: dict[str, float]   # {criterion_text: 0.0–1.0}


@router.patch("/exam-runs/{run_id}/mentor")
def submit_mentor_scores(
    run_id: str,
    body: MentorScores,
    db: Session = Depends(get_db),
):
    """Submit Mentor scores for each criterion; recalculates total_score and passed."""
    run = db.query(ExamRun).filter(ExamRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status != "done":
        raise HTTPException(400, "Run has not completed yet")

    criteria = _safe_json(run.mentor_criteria_json, [])
    if not criteria:
        raise HTTPException(400, "This exam has no mentor criteria")

    mentor_weight = run.mentor_weight or 0.4
    auto_weight   = run.auto_weight   or 0.6

    m_score = (sum(body.scores.values()) / len(criteria)) * 100
    total   = round((run.auto_score or 0) * auto_weight + m_score * mentor_weight, 1)
    passed  = total >= (run.threshold or 75)

    run.mentor_score      = round(m_score, 1)
    run.mentor_scores_json = json.dumps(body.scores, ensure_ascii=False)
    run.total_score        = total
    run.passed             = passed
    db.commit()
    db.refresh(run)
    return _run_to_dict(run)


# ── Exam CRUD ──────────────────────────────────────────────────────────────────

class ExamPayload(BaseModel):
    id: str
    role: str = ""
    skill: str = ""
    difficulty: str = "L1"
    scenario: str = ""
    input_message: str
    expected_keywords: list[str] = []
    mentor_criteria: list[str] = []
    auto_score_weight: float = 0.6
    mentor_score_weight: float = 0.4
    pass_threshold: int = 75


def _payload_to_yaml(p: ExamPayload) -> str:
    data: dict = {
        "id": p.id,
    }
    if p.role:
        data["role"] = p.role
    data.update({
        "skill": p.skill,
        "difficulty": p.difficulty,
        "scenario": p.scenario,
        "input": {"message": p.input_message},
    })
    if p.expected_keywords:
        data["expected_keywords"] = p.expected_keywords
    if p.mentor_criteria:
        data["mentor_criteria"] = p.mentor_criteria
    data["auto_score_weight"] = p.auto_score_weight
    data["mentor_score_weight"] = p.mentor_score_weight
    data["pass_threshold"] = p.pass_threshold
    return yaml.dump(data, allow_unicode=True, sort_keys=False)


def _load_exam_file(filename: str) -> dict:
    """Load a single exam YAML; raise 404 if missing."""
    if not filename.endswith(".yaml") or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Invalid filename")
    path = os.path.join(EXAMS_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(404, f"Exam not found: {filename}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data


@router.get("/exams/{filename}")
def get_exam(filename: str):
    """Return full YAML content of a single exam file."""
    data = _load_exam_file(filename)
    return {
        "file": filename,
        "id": data.get("id", filename),
        "role": data.get("role", ""),
        "skill": data.get("skill", ""),
        "difficulty": data.get("difficulty", "L1"),
        "scenario": data.get("scenario", ""),
        "input_message": data.get("input", {}).get("message", ""),
        "expected_keywords": data.get("expected_keywords", []),
        "mentor_criteria": data.get("mentor_criteria", []),
        "auto_score_weight": data.get("auto_score_weight", 0.6),
        "mentor_score_weight": data.get("mentor_score_weight", 0.4),
        "pass_threshold": data.get("pass_threshold", 75),
    }


@router.post("/exams", status_code=201)
def create_exam(payload: ExamPayload):
    """Create a new exam YAML file. Filename is derived from the exam id."""
    os.makedirs(EXAMS_DIR, exist_ok=True)
    filename = payload.id.replace(" ", "_") + ".yaml"
    path = os.path.join(EXAMS_DIR, filename)
    if os.path.exists(path):
        raise HTTPException(409, f"Exam already exists: {filename}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_payload_to_yaml(payload))
    return {"file": filename, **payload.model_dump()}


@router.put("/exams/{filename}")
def update_exam(filename: str, payload: ExamPayload):
    """Overwrite an existing exam YAML file."""
    if not filename.endswith(".yaml") or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Invalid filename")
    path = os.path.join(EXAMS_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(404, f"Exam not found: {filename}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_payload_to_yaml(payload))
    return {"file": filename, **payload.model_dump()}


@router.delete("/exams/{filename}", status_code=204)
def delete_exam(filename: str):
    """Delete an exam YAML file."""
    if not filename.endswith(".yaml") or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Invalid filename")
    path = os.path.join(EXAMS_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(404, f"Exam not found: {filename}")
    os.remove(path)


# ── Exam Draft endpoints ────────────────────────────────────────────────────

@router.get("/exam-drafts")
def list_exam_drafts():
    """Return list of all pending exam drafts."""
    if not os.path.isdir(DRAFTS_DIR):
        return []
    result = []
    for fname in sorted(os.listdir(DRAFTS_DIR)):
        if not fname.endswith(".yaml"):
            continue
        try:
            with open(os.path.join(DRAFTS_DIR, fname), encoding="utf-8") as f:
                data = yaml.safe_load(f)
            result.append({
                "file":         fname,
                "id":           data.get("id", fname),
                "skill":        data.get("skill", ""),
                "difficulty":   data.get("difficulty", ""),
                "scenario":     data.get("scenario", ""),
                "role":         data.get("role", "QA"),
            })
        except Exception:
            result.append({"file": fname, "id": fname, "error": "Failed to parse"})
    return result


@router.post("/exam-drafts/{exam_id}/publish")
def publish_exam_draft(exam_id: str):
    """
    Publish an exam draft to the main exams directory.
    Validates the draft, copies it to exams/{exam_id}.yaml, and optionally deletes the draft.
    """
    # Sanitize exam_id to prevent directory traversal
    if "/" in exam_id or "\\" in exam_id or exam_id.startswith("."):
        raise HTTPException(400, "Invalid exam_id")

    draft_path = os.path.join(DRAFTS_DIR, f"{exam_id}.yaml")
    if not os.path.isfile(draft_path):
        raise HTTPException(404, f"Draft not found: {exam_id}")

    # Validate YAML
    try:
        with open(draft_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        raise HTTPException(400, f"Invalid YAML in draft: {e}")

    # Check required fields
    required_fields = ["id", "skill", "difficulty", "input"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(400, f"Missing required field: {field}")

    # Check if exam already exists in main directory
    target_path = os.path.join(EXAMS_DIR, f"{exam_id}.yaml")
    if os.path.isfile(target_path):
        raise HTTPException(409, f"Exam already exists: {exam_id}")

    # Copy draft to main exams directory
    try:
        with open(draft_path, encoding="utf-8") as f:
            content = f.read()
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(500, f"Failed to publish exam: {e}")

    # Delete draft after successful publish
    try:
        os.remove(draft_path)
    except Exception:
        pass  # Best-effort delete

    return {
        "success": True,
        "exam_id": exam_id,
        "file": f"exams/{exam_id}.yaml",
    }


@router.delete("/exam-drafts/{exam_id}")
def delete_exam_draft(exam_id: str):
    """Delete an exam draft."""
    if "/" in exam_id or "\\" in exam_id or exam_id.startswith("."):
        raise HTTPException(400, "Invalid exam_id")

    draft_path = os.path.join(DRAFTS_DIR, f"{exam_id}.yaml")
    if not os.path.isfile(draft_path):
        raise HTTPException(404, f"Draft not found: {exam_id}")

    try:
        os.remove(draft_path)
    except Exception as e:
        raise HTTPException(500, f"Failed to delete draft: {e}")

    return {"success": True, "exam_id": exam_id}


# ── Background task ────────────────────────────────────────────────────────────

def _run_exam_task(
    run_id: str,
    agent_id: str,
    agent_name: str,
    specialization: str,
) -> None:
    """
    Runs synchronously in a thread-pool worker (FastAPI BackgroundTasks).
    Builds a fresh LangGraph agent, invokes it with the exam prompt,
    auto-scores the output, then persists the result.
    """
    db = SessionLocal()
    try:
        run = db.query(ExamRun).filter(ExamRun.id == run_id).first()
        if not run:
            return

        # Load the YAML
        exam_path = os.path.join(EXAMS_DIR, run.exam_file)
        try:
            with open(exam_path, encoding="utf-8") as f:
                exam = yaml.safe_load(f)
        except Exception as exc:
            run.status    = "error"
            run.error_msg = f"Cannot load exam file: {exc}"
            db.commit()
            return

        user_message     = exam["input"]["message"]
        expected_kws     = exam.get("expected_keywords", [])
        auto_weight      = float(exam.get("auto_score_weight", 0.6))
        mentor_weight    = float(exam.get("mentor_score_weight", 0.4))
        threshold        = int(exam.get("pass_threshold", 75))
        mentor_criteria  = exam.get("mentor_criteria", [])
        criteria         = exam.get("criteria", [])          # rubric-based criteria for judge
        rules            = exam.get("rules", [])             # hard rules for layer-1 check
        scenario         = exam.get("scenario", "")

        try:
            from langchain_core.messages import HumanMessage
            from agent.agent import build_agent
            from eval.evaluator import auto_score
            from eval.judge import evaluate_rules, evaluate_criteria, judge_to_score

            app    = build_agent()
            config = {
                "configurable": {
                    "thread_id":      f"exam-{run_id}",
                    "agent_id":       agent_id,
                    "agent_name":     agent_name,
                    "specialization": specialization,
                }
            }
            initial_state = {
                "messages":          [HumanMessage(content=user_message)],
                "task_id":           f"exam-{run_id}",
                "task_description":  user_message,
                "pending_approval":  False,
                "escalated":         False,
                "escalation_reason": "",
            }

            t0           = time.time()
            final_state  = app.invoke(initial_state, config=config)
            elapsed      = round(time.time() - t0, 2)

            last_msg = final_state["messages"][-1]
            output   = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

            # ── Layer 1: Rule checks ──────────────────────────────────────────
            rules_result = evaluate_rules(output, rules)

            # ── Layer 2: LLM-as-Judge ─────────────────────────────────────────
            judge_results = {}
            judge_score   = None
            if criteria:
                judge_results = evaluate_criteria(
                    output       = output,
                    criteria     = criteria,
                    scenario     = scenario,
                    input_message= user_message,
                )
                if judge_results:
                    judge_score = judge_to_score(judge_results, criteria)

            # ── Auto score (keyword matching) ─────────────────────────────────
            a_score, missed = auto_score(output, expected_kws)

            # ── Final score calculation ───────────────────────────────────────
            passed: bool | None

            if judge_score is not None:
                # Judge ran successfully → pre-fill mentor_score; passed is resolved
                m_score = judge_score
                total   = round(a_score * auto_weight + m_score * mentor_weight, 1)
                passed  = total >= threshold
            elif mentor_criteria:
                # Legacy mode: no rubric criteria, human must score manually
                m_score = None
                total   = round(a_score * auto_weight, 1)
                passed  = None          # pending until mentor fills in
            else:
                # No judge criteria and no mentor criteria → auto only
                m_score = None
                total   = round(a_score * (auto_weight + mentor_weight), 1)
                passed  = total >= threshold

            run.status               = "done"
            run.auto_score           = a_score
            run.auto_weight          = auto_weight
            run.mentor_score         = m_score
            run.mentor_weight        = mentor_weight
            run.total_score          = total
            run.threshold            = threshold
            run.passed               = passed
            run.missed_keywords_json = json.dumps(missed, ensure_ascii=False)
            run.judge_results_json   = json.dumps(judge_results, ensure_ascii=False)
            run.rules_result_json    = json.dumps(rules_result,  ensure_ascii=False)
            run.output               = output
            run.elapsed_sec          = elapsed

        except Exception as exc:
            run.status    = "error"
            run.error_msg = str(exc)[:500]

        db.commit()
    finally:
        db.close()


# ── Prompt Improvement Suggestion endpoints ────────────────────────────────────

@router.post("/exam-runs/{run_id}/suggest")
def suggest_prompt_improvement(run_id: str, db: Session = Depends(get_db)):
    """
    Generate (or return cached) prompt improvement suggestions for a completed run.

    - Loads the failed run + the active prompt version at the time of the run.
    - Calls eval/suggester.py to produce diagnosis + suggestions + patched_prompt.
    - Caches result in prompt_suggestions table; subsequent calls return the cached row.
    """
    run = db.query(ExamRun).filter(ExamRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status != "done":
        raise HTTPException(400, "Run has not completed yet")

    # Return cached suggestion if already generated
    existing = db.query(PromptSuggestion).filter(PromptSuggestion.run_id == run_id).first()
    if existing:
        return _suggestion_to_dict(existing)

    # Load the prompt that was active during this run
    current_prompt = ""
    if run.prompt_version_id:
        pv = db.query(PromptVersion).filter(PromptVersion.id == run.prompt_version_id).first()
        if pv:
            current_prompt = pv.content
    if not current_prompt:
        # Fallback: load current active base prompt
        pv = db.query(PromptVersion).filter(
            PromptVersion.agent_id == run.agent_id,
            PromptVersion.type == "base",
            PromptVersion.is_active == True,
        ).first()
        current_prompt = pv.content if pv else ""

    if not current_prompt:
        # Final fallback: use the built-in system prompt (agent has no saved prompt version yet)
        from agent.prompts import QA_SYSTEM_PROMPT
        current_prompt = QA_SYSTEM_PROMPT

    # Load exam YAML for scenario + input_message
    exam_data = {}
    try:
        path = os.path.join(EXAMS_DIR, run.exam_file)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                exam_data = yaml.safe_load(f) or {}
    except Exception:
        pass

    exam_scenario   = exam_data.get("scenario", run.exam_id or "")
    input_message   = exam_data.get("input", {}).get("message", "")
    missed_keywords = _safe_json(run.missed_keywords_json, [])
    judge_results   = _safe_json(run.judge_results_json, {})
    agent_output    = run.output or ""

    from eval.suggester import generate_suggestions
    result = generate_suggestions(
        current_prompt  = current_prompt,
        exam_scenario   = exam_scenario,
        input_message   = input_message,
        agent_output    = agent_output,
        missed_keywords = missed_keywords,
        judge_results   = judge_results,
    )

    import uuid as _uuid
    suggestion = PromptSuggestion(
        id                = str(_uuid.uuid4()),
        run_id            = run_id,
        agent_id          = run.agent_id,
        prompt_version_id = run.prompt_version_id,
        diagnosis         = result.get("diagnosis", ""),
        suggestions_json  = json.dumps(result.get("suggestions", []), ensure_ascii=False),
        patched_prompt    = result.get("patched_prompt", current_prompt),
        applied           = False,
        created_at        = datetime.utcnow(),
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    return _suggestion_to_dict(suggestion)


@router.post("/exam-runs/{run_id}/suggest/apply")
def apply_prompt_suggestion(run_id: str, db: Session = Depends(get_db)):
    """
    Apply a cached suggestion by creating a new PromptVersion with the patched_prompt.
    Returns the new PromptVersion so the frontend can navigate to the Prompt editor.
    """
    suggestion = db.query(PromptSuggestion).filter(PromptSuggestion.run_id == run_id).first()
    if not suggestion:
        raise HTTPException(404, "No suggestion found — call POST /suggest first")
    if suggestion.applied:
        raise HTTPException(400, "Suggestion already applied")
    if not suggestion.patched_prompt:
        raise HTTPException(400, "Suggestion has no patched prompt")

    # Increment version number
    last = db.query(PromptVersion).filter(
        PromptVersion.agent_id == suggestion.agent_id,
        PromptVersion.type == "base",
    ).order_by(PromptVersion.version.desc()).first()
    new_version_num = (last.version + 1) if last else 1

    # Deactivate current active version
    db.query(PromptVersion).filter(
        PromptVersion.agent_id == suggestion.agent_id,
        PromptVersion.type == "base",
        PromptVersion.is_active == True,
    ).update({"is_active": False})

    import uuid as _uuid
    new_pv = PromptVersion(
        id        = str(_uuid.uuid4()),
        agent_id  = suggestion.agent_id,
        type      = "base",
        version   = new_version_num,
        content   = suggestion.patched_prompt,
        note      = f"Auto-applied from exam run suggestion (run {run_id[:8]}…)",
        is_active = True,
        created_at = datetime.utcnow(),
    )
    db.add(new_pv)

    suggestion.applied            = True
    suggestion.applied_version_id = new_pv.id
    db.commit()
    db.refresh(new_pv)

    return {
        "version_id":  new_pv.id,
        "version_num": new_pv.version,
        "agent_id":    suggestion.agent_id,
        "note":        new_pv.note,
    }


def _suggestion_to_dict(s: PromptSuggestion) -> dict:
    return {
        "id":                 s.id,
        "run_id":             s.run_id,
        "agent_id":           s.agent_id,
        "prompt_version_id":  s.prompt_version_id,
        "diagnosis":          s.diagnosis,
        "suggestions":        _safe_json(s.suggestions_json, []),
        "patched_prompt":     s.patched_prompt,
        "applied":            s.applied,
        "applied_version_id": s.applied_version_id,
        "created_at":         s.created_at.isoformat() + "Z" if s.created_at else None,
    }
