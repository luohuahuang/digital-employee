"""
Audit Logger — writes a trail of every tool call and L2 decision.

Storage strategy:
  - Web mode   → SQLite via SQLAlchemy (web/de_team.db)
  - Terminal   → JSONL append-only file  (logs/audit.jsonl)

The caller does not need to know which backend is active; log_tool_call()
and log_l2_decision() detect the environment automatically.

All writes are best-effort: a logging failure must never crash the agent.

V2 Observability fields:
  trace_id       — UUID shared by all entries in one chat turn (P0 chain tracing)
  node_name      — LangGraph node that emitted the entry ("agent"|"tools"|"human_review")
  extra_data_json — JSON blob for structured extra metrics, e.g. KB retrieval stats (P3),
                    quality score (P2)
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime

# ── JSONL path (terminal mode) ─────────────────────────────────────────────────
_LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
AUDIT_JSONL = os.path.join(_LOGS_DIR, "audit.jsonl")

_RESULT_PREVIEW_LEN = 300


# ── Public API ─────────────────────────────────────────────────────────────────

def log_tool_call(
    *,
    agent_id: str,
    agent_name: str = "",
    conversation_id: str | None = None,
    tool_name: str,
    tool_args: dict,
    result: str,
    duration_ms: int,
    success: bool = True,
    error_msg: str | None = None,
    trace_id: str | None = None,
    node_name: str | None = None,
    extra_data: dict | None = None,
) -> None:
    """Record a completed tool execution (L1 or L2)."""
    entry = {
        "id": str(uuid.uuid4()),
        "agent_id": agent_id or "unknown",
        "agent_name": agent_name or agent_id or "unknown",
        "conversation_id": conversation_id,
        "event_type": "tool_call",
        "tool_name": tool_name,
        "tool_args_json": json.dumps(tool_args, ensure_ascii=False),
        "result_preview": result[:_RESULT_PREVIEW_LEN] if result else None,
        "duration_ms": duration_ms,
        "success": success,
        "error_msg": error_msg,
        "l2_approved": None,
        "trace_id": trace_id,
        "node_name": node_name,
        "extra_data_json": json.dumps(extra_data, ensure_ascii=False) if extra_data else None,
        "created_at": datetime.utcnow().isoformat(),
    }
    _write(entry)


def log_llm_call(
    *,
    agent_id: str,
    agent_name: str = "",
    conversation_id: str | None = None,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    duration_ms: int = 0,
    trace_id: str | None = None,
    node_name: str | None = None,
) -> None:
    """Record an LLM call with token usage."""
    entry = {
        "id": str(uuid.uuid4()),
        "agent_id": agent_id or "unknown",
        "agent_name": agent_name or agent_id or "unknown",
        "conversation_id": conversation_id,
        "event_type": "llm_call",
        "tool_name": model,
        "tool_args_json": "{}",
        "result_preview": None,
        "duration_ms": duration_ms,
        "success": True,
        "error_msg": None,
        "l2_approved": None,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "trace_id": trace_id,
        "node_name": node_name,
        "extra_data_json": None,
        "created_at": datetime.utcnow().isoformat(),
    }
    _write(entry)


def log_l2_decision(
    *,
    agent_id: str,
    agent_name: str = "",
    conversation_id: str | None = None,
    tool_name: str,
    tool_args: dict,
    approved: bool,
    trace_id: str | None = None,
) -> None:
    """Record a Mentor approve/reject decision for an L2 tool."""
    entry = {
        "id": str(uuid.uuid4()),
        "agent_id": agent_id or "unknown",
        "agent_name": agent_name or agent_id or "unknown",
        "conversation_id": conversation_id,
        "event_type": "l2_decision",
        "tool_name": tool_name,
        "tool_args_json": json.dumps(tool_args, ensure_ascii=False),
        "result_preview": None,
        "duration_ms": None,
        "success": approved,
        "error_msg": None,
        "l2_approved": approved,
        "trace_id": trace_id,
        "node_name": "human_review",
        "extra_data_json": None,
        "created_at": datetime.utcnow().isoformat(),
    }
    _write(entry)


def log_quality_score(
    *,
    agent_id: str,
    agent_name: str = "",
    conversation_id: str | None = None,
    score: float,
    verdict: str,
    reasoning: str = "",
    trace_id: str | None = None,
) -> None:
    """Record an LLM-as-Judge quality score for a completed chat turn (P2)."""
    extra = {"score": score, "verdict": verdict, "reasoning": reasoning[:200]}
    entry = {
        "id": str(uuid.uuid4()),
        "agent_id": agent_id or "unknown",
        "agent_name": agent_name or agent_id or "unknown",
        "conversation_id": conversation_id,
        "event_type": "quality_score",
        "tool_name": "llm_judge",
        "tool_args_json": "{}",
        "result_preview": f"{score:.2f} ({verdict})",
        "duration_ms": None,
        "success": True,
        "error_msg": None,
        "l2_approved": None,
        "trace_id": trace_id,
        "node_name": "quality_judge",
        "extra_data_json": json.dumps(extra, ensure_ascii=False),
        "created_at": datetime.utcnow().isoformat(),
    }
    _write(entry)


# ── Internal ───────────────────────────────────────────────────────────────────

def _write(entry: dict) -> None:
    """Try SQLite first; fall back to JSONL; swallow all errors."""
    try:
        _write_sqlite(entry)
    except Exception:
        try:
            _write_jsonl(entry)
        except Exception:
            pass  # Logging must never crash the agent


def _write_sqlite(entry: dict) -> None:
    """Write to the web SQLite DB (only available when web server is running)."""
    # Import lazily so terminal mode doesn't need FastAPI/SQLAlchemy installed
    from web.db.database import SessionLocal
    from web.db.models import AuditLog

    db = SessionLocal()
    try:
        row = AuditLog(
            id=entry["id"],
            agent_id=entry["agent_id"],
            agent_name=entry["agent_name"],
            conversation_id=entry["conversation_id"],
            event_type=entry["event_type"],
            tool_name=entry["tool_name"],
            tool_args_json=entry["tool_args_json"],
            result_preview=entry["result_preview"],
            duration_ms=entry["duration_ms"],
            success=entry["success"],
            error_msg=entry["error_msg"],
            l2_approved=entry["l2_approved"],
            input_tokens=entry.get("input_tokens"),
            output_tokens=entry.get("output_tokens"),
            trace_id=entry.get("trace_id"),
            node_name=entry.get("node_name"),
            extra_data_json=entry.get("extra_data_json"),
            created_at=datetime.fromisoformat(entry["created_at"]),
        )
        db.add(row)
        db.commit()
    finally:
        db.close()


def _write_jsonl(entry: dict) -> None:
    """Fallback: append a JSON line to logs/audit.jsonl."""
    os.makedirs(_LOGS_DIR, exist_ok=True)
    with open(AUDIT_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
