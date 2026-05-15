"""
Agent state definition for Digital QA Employee.

LangGraph's core is a "state machine": each node reads state and produces new state segments,
the framework handles merging. This defines context across the entire conversation.

Corresponds to design document: §5.2 Five Core Characteristics (Auditable), §5.3 Schema.
"""
from __future__ import annotations

from typing import Annotated
from typing_extensions import TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # ── Core Message List ──────────────────────────────────────────────────────
    # add_messages: new messages append rather than overwrite, preserving complete conversation history
    messages: Annotated[list, add_messages]

    # ── Task Context ─────────────────────────────────────────────────────────
    task_id: str            # Test question/task ID, used for audit association (e.g., "tc-design-001")
    task_description: str   # Natural language description of this task

    # ── Human Approval State (Human-in-the-loop)────────────────────────────────────
    # When pending_approval=True, graph pauses and awaits Mentor input
    pending_approval: bool

    # ── Escalation State ───────────────────────────────────────────────────────────
    # Set to True when digital employee encounters situation beyond capability boundary, triggers escalation logic
    escalated: bool
    escalation_reason: str  # Escalation reason, visible to Mentor
