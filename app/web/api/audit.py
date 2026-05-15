"""Audit log REST endpoints.

V2 additions (Observability P0–P3):
  GET /api/audit/trace/{trace_id}  — waterfall of all events in one chat turn (P0)
  GET /api/audit/summary           — now includes:
    health_score / p95_duration_ms / error_rate_trend (P1)
    avg_quality_score               (P2)
    kb_stats                        (P3)
"""
import json
import math
from datetime import datetime, timedelta
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from web.db.database import get_db
from web.db.models import AuditLog

router = APIRouter(tags=["audit"])


# ── /audit  (paginated event list) ────────────────────────────────────────────

@router.get("/audit")
def list_audit(
    agent_id: str = Query(None),
    start: str = Query(None),       # ISO date string, e.g. "2026-04-01"
    end: str = Query(None),
    tool: str = Query(None),
    event_type: str = Query(None),  # "tool_call" | "l2_decision" | "llm_call" | "quality_score"
    trace_id: str = Query(None),    # filter by trace_id
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)

    if agent_id:
        q = q.filter(AuditLog.agent_id == agent_id)
    if tool:
        q = q.filter(AuditLog.tool_name == tool)
    if event_type:
        q = q.filter(AuditLog.event_type == event_type)
    if trace_id:
        q = q.filter(AuditLog.trace_id == trace_id)
    if start:
        q = q.filter(AuditLog.created_at >= datetime.fromisoformat(start))
    if end:
        end_dt = datetime.fromisoformat(end) + timedelta(days=1)
        q = q.filter(AuditLog.created_at < end_dt)

    total = q.count()
    items = (
        q.order_by(desc(AuditLog.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [_row_to_dict(r) for r in items],
    }


# ── /audit/trace/{trace_id}  (P0: chain waterfall) ────────────────────────────

@router.get("/audit/trace/{trace_id}")
def get_trace(trace_id: str, db: Session = Depends(get_db)):
    """Return all audit events in a single chat turn, ordered chronologically.

    Each event carries node_name so the caller can render a LangGraph waterfall:
      agent (llm_call) → tools (tool_call × N) → agent (llm_call) → …
    """
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.trace_id == trace_id)
        .order_by(AuditLog.created_at)
        .all()
    )
    if not rows:
        from fastapi import HTTPException
        raise HTTPException(404, f"No events found for trace_id={trace_id}")

    total_duration_ms = sum(r.duration_ms or 0 for r in rows)
    total_input  = sum(r.input_tokens  or 0 for r in rows)
    total_output = sum(r.output_tokens or 0 for r in rows)

    return {
        "trace_id": trace_id,
        "event_count": len(rows),
        "total_duration_ms": total_duration_ms,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "events": [_row_to_dict(r) for r in rows],
    }


# ── /audit/summary  (aggregated stats dashboard) ──────────────────────────────

@router.get("/audit/summary")
def audit_summary(
    agent_id: str = Query(None),
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)
    q = db.query(AuditLog).filter(AuditLog.created_at >= since)
    if agent_id:
        q = q.filter(AuditLog.agent_id == agent_id)

    rows = q.all()

    # ── Core event groups ──────────────────────────────────────────────────────
    tool_calls     = [r for r in rows if r.event_type == "tool_call"]
    l2_rows        = [r for r in rows if r.event_type == "l2_decision"]
    llm_rows       = [r for r in rows if r.event_type == "llm_call"]
    quality_rows   = [r for r in rows if r.event_type == "quality_score"]
    kb_rows        = [r for r in tool_calls if r.tool_name == "search_knowledge_base"]

    total_calls   = len(tool_calls)
    success_count = sum(1 for r in tool_calls if r.success)
    success_rate  = round(success_count / total_calls, 4) if total_calls else 1.0

    durations = [r.duration_ms for r in tool_calls if r.duration_ms is not None]
    avg_ms    = int(sum(durations) / len(durations)) if durations else 0

    # ── P1: P95 latency ────────────────────────────────────────────────────────
    p95_ms = _percentile(durations, 95) if durations else 0

    # ── P1: error rate trend (last 24h vs prior 24h) ──────────────────────────
    cutoff_24h = datetime.utcnow() - timedelta(hours=24)
    cutoff_48h = datetime.utcnow() - timedelta(hours=48)
    recent_calls = [r for r in tool_calls if r.created_at >= cutoff_24h]
    prior_calls  = [r for r in tool_calls if cutoff_48h <= r.created_at < cutoff_24h]

    recent_err = sum(1 for r in recent_calls if not r.success)
    prior_err  = sum(1 for r in prior_calls  if not r.success)
    recent_err_rate = recent_err / len(recent_calls) if recent_calls else 0.0
    prior_err_rate  = prior_err  / len(prior_calls)  if prior_calls  else 0.0
    error_trend     = round(recent_err_rate - prior_err_rate, 4)  # positive = worsening

    # ── P1: health score (composite) ─────────────────────────────────────────
    # success_rate: 0-1, weight 0.5
    # p95_score: 1.0 if p95 < 3s, grades down to 0 at 30s, weight 0.2
    # error_trend_score: 1.0 if no worsening, weight 0.2
    # quality_score_avg: 0-1 from judge, weight 0.1
    p95_score = max(0.0, 1.0 - max(0.0, (p95_ms - 3000) / 27000))
    trend_score = max(0.0, 1.0 - (error_trend * 10))  # +10% error → score 0
    quality_scores = _parse_quality_scores(quality_rows)
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 1.0

    health_score = round(
        success_rate   * 0.5 +
        p95_score      * 0.2 +
        trend_score    * 0.2 +
        avg_quality    * 0.1,
        3,
    )

    # ── Top tools ──────────────────────────────────────────────────────────────
    tool_counts: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_ms": 0, "errors": 0})
    for r in tool_calls:
        tn = r.tool_name or "unknown"
        tool_counts[tn]["count"] += 1
        if r.duration_ms:
            tool_counts[tn]["total_ms"] += r.duration_ms
        if not r.success:
            tool_counts[tn]["errors"] += 1

    top_tools = sorted(
        [
            {
                "name": name,
                "count": v["count"],
                "avg_ms": int(v["total_ms"] / v["count"]) if v["count"] else 0,
                "error_count": v["errors"],
            }
            for name, v in tool_counts.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )[:10]

    # ── Calls per day ──────────────────────────────────────────────────────────
    day_counts: dict[str, int] = defaultdict(int)
    for r in tool_calls:
        day = r.created_at.strftime("%Y-%m-%d")
        day_counts[day] += 1

    calls_per_day = []
    for i in range(days - 1, -1, -1):
        d = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        calls_per_day.append({"date": d, "count": day_counts.get(d, 0)})

    # ── L2 decisions ──────────────────────────────────────────────────────────
    l2_approved = sum(1 for r in l2_rows if r.l2_approved)
    l2_rejected = sum(1 for r in l2_rows if not r.l2_approved)

    # ── Active agents ─────────────────────────────────────────────────────────
    active_agents = len({r.agent_id for r in rows})

    # ── Token usage ───────────────────────────────────────────────────────────
    total_input  = sum((r.input_tokens  or 0) for r in llm_rows)
    total_output = sum((r.output_tokens or 0) for r in llm_rows)
    estimated_cost_usd = round(
        total_input  / 1_000_000 * 3.0 +
        total_output / 1_000_000 * 15.0,
        4,
    )

    # ── P3: KB retrieval analytics ────────────────────────────────────────────
    kb_stats = _compute_kb_stats(kb_rows)

    return {
        "period_days": days,
        "total_tool_calls": total_calls,
        "success_rate": success_rate,
        "avg_duration_ms": avg_ms,
        "top_tools": top_tools,
        "calls_per_day": calls_per_day,
        "l2_decisions": {"approved": l2_approved, "rejected": l2_rejected},
        "active_agents": active_agents,
        "tokens": {
            "input":  total_input,
            "output": total_output,
            "estimated_cost_usd": estimated_cost_usd,
        },
        # ── V2 observability ────────────────────────────────────────────
        "health": {
            "score":            health_score,   # 0.0–1.0 composite
            "p95_duration_ms":  p95_ms,
            "error_rate_trend": error_trend,    # negative=improving, positive=worsening
        },
        "quality": {
            "avg_score":   round(avg_quality, 3),
            "sample_count": len(quality_scores),
            "scores_per_day": _quality_per_day(quality_rows, days),
        },
        "kb_stats": kb_stats,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _percentile(values: list[int], p: int) -> int:
    """Return the p-th percentile of a sorted list."""
    if not values:
        return 0
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    f, c = int(k), math.ceil(k)
    if f == c:
        return s[int(k)]
    return int(s[f] * (c - k) + s[c] * (k - f))


def _parse_quality_scores(quality_rows) -> list[float]:
    """Extract numeric scores from quality_score audit entries."""
    scores = []
    for r in quality_rows:
        try:
            data = json.loads(r.extra_data_json or "{}")
            s = data.get("score")
            if s is not None:
                scores.append(float(s))
        except Exception:
            pass
    return scores


def _quality_per_day(quality_rows, days: int) -> list[dict]:
    """Average quality score per day for trend chart."""
    day_scores: dict[str, list] = defaultdict(list)
    for r in quality_rows:
        day = r.created_at.strftime("%Y-%m-%d")
        try:
            data = json.loads(r.extra_data_json or "{}")
            s = data.get("score")
            if s is not None:
                day_scores[day].append(float(s))
        except Exception:
            pass

    result = []
    for i in range(days - 1, -1, -1):
        d = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        scores = day_scores.get(d, [])
        result.append({
            "date": d,
            "avg_score": round(sum(scores) / len(scores), 3) if scores else None,
            "count": len(scores),
        })
    return result


def _compute_kb_stats(kb_rows) -> dict:
    """P3: Aggregate KB retrieval statistics from extra_data_json."""
    if not kb_rows:
        return {
            "total_searches": 0,
            "low_relevance_count": 0,
            "low_relevance_rate": 0.0,
            "avg_top_score": None,
        }

    top_scores = []
    low_relevance_count = 0

    for r in kb_rows:
        try:
            data = json.loads(r.extra_data_json or "{}")
            top_score = data.get("top_score")
            if top_score is not None:
                top_scores.append(float(top_score))
            if data.get("low_relevance"):
                low_relevance_count += 1
        except Exception:
            pass

    return {
        "total_searches": len(kb_rows),
        "low_relevance_count": low_relevance_count,
        "low_relevance_rate": round(low_relevance_count / len(kb_rows), 3) if kb_rows else 0.0,
        "avg_top_score": round(sum(top_scores) / len(top_scores), 1) if top_scores else None,
    }


def _row_to_dict(r: AuditLog) -> dict:
    return {
        "id": r.id,
        "agent_id": r.agent_id,
        "agent_name": r.agent_name,
        "conversation_id": r.conversation_id,
        "event_type": r.event_type,
        "tool_name": r.tool_name,
        "tool_args": _safe_json(r.tool_args_json),
        "result_preview": r.result_preview,
        "duration_ms": r.duration_ms,
        "success": r.success,
        "error_msg": r.error_msg,
        "l2_approved": r.l2_approved,
        "input_tokens":  r.input_tokens,
        "output_tokens": r.output_tokens,
        "trace_id":      r.trace_id,
        "node_name":     r.node_name,
        "extra_data":    _safe_json(r.extra_data_json),
        "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
    }


def _safe_json(s: str | None):
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        return {"raw": s}
