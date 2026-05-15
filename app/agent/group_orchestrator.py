"""
Group Chat Orchestrator — Multi-Agent LangGraph.

Graph structure (Supervisor Pattern):
  START → supervisor → agent_<id> → supervisor → ... → END

Termination (double-guard as specified):
  1. Supervisor LLM declares is_resolved=True
  2. turn_count >= MAX_TURNS (6)
  3. All agents PASS in the current round

Design notes:
  - Each agent runs an agentic tool loop (L1 tools only; L2 excluded — no HITL in group chat)
  - Sequential ordering: supervisor picks one agent at a time
  - Fresh thread_id per user message → no cross-message state bleed
  - history_context (previous turns, formatted string) is separate from
    messages (current orchestration run only), so the supervisor can cleanly
    track "who spoke in THIS round"
"""
from __future__ import annotations

import json
import operator
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage

from config import (
    ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENAI_BASE_URL,
    MODEL_NAME, LLM_PROVIDER,
)
from agent.llm_client import call_llm

MAX_TURNS = 6
_PASS_WORDS = {"PASS", "PASS.", "PASS\n"}


# ── State ──────────────────────────────────────────────────────────────────────

class GroupChatState(TypedDict):
    # Current-run messages only (starts with the user message, agents append).
    # operator.add is the reducer: returns current + new on each node update.
    messages:                Annotated[list[dict], operator.add]

    # Formatted string of the group's previous conversation turns (from DB).
    # Injected once at run start; read-only inside the graph.
    history_context:         str

    # Static list of participant metadata (id, name, product_line, specialization, avatar_emoji)
    participants:            list[dict]

    # Incremented by supervisor on each call; enforces MAX_TURNS hard limit
    turn_count:              int

    # Agent ID chosen by supervisor for the next turn; None triggers END
    next_speaker:            str | None

    # Supervisor LLM declares question resolved
    is_resolved:             bool

    # Agent IDs that returned PASS this round (overwritten via read+append pattern)
    agents_passed_this_round: list[str]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _format_current_run(messages: list[dict]) -> str:
    """Format current-run messages (user + agent responses so far) into readable text."""
    lines = []
    for m in messages:
        if m["role"] == "user":
            lines.append(f"[User]: {m['content']}")
        elif m.get("is_pass"):
            lines.append(f"[{m.get('emoji', '🤖')} {m['speaker']}]: (passed — nothing to add from this domain)")
        else:
            lines.append(f"[{m.get('emoji', '🤖')} {m['speaker']}]: {m['content']}")
    return "\n\n".join(lines) if lines else ""


def _full_context(state: GroupChatState) -> str:
    """Combine historical context with current-run messages."""
    parts = []
    if state["history_context"]:
        parts.append("═══ Previous conversation ═══\n" + state["history_context"])
    current = _format_current_run(state["messages"])
    if current:
        parts.append("═══ Current question ═══\n" + current)
    return "\n\n".join(parts)


def _is_pass(text: str) -> bool:
    stripped = text.strip().upper()
    return stripped in _PASS_WORDS or stripped.startswith("PASS\n") or stripped.startswith("PASS ")


# ── Supervisor Node ────────────────────────────────────────────────────────────

def _supervisor_node(state: GroupChatState) -> dict:
    """
    LLM-powered supervisor: decides which agent speaks next OR declares done.
    Hard guards run first (no LLM call needed).
    """
    # Hard guard 1: turn limit
    if state["turn_count"] >= MAX_TURNS:
        return {"is_resolved": True, "next_speaker": None, "turn_count": state["turn_count"] + 1}

    # Hard guard 2: all agents passed
    if len(state["participants"]) > 0 and \
       len(state["agents_passed_this_round"]) >= len(state["participants"]):
        return {"is_resolved": True, "next_speaker": None, "turn_count": state["turn_count"] + 1}

    participants_info = "\n".join(
        f"  id={p['id']}  name={p['name']}  domain={p.get('product_line', 'general')}"
        for p in state["participants"]
    )

    already_spoke = {m["agent_id"] for m in state["messages"] if m.get("role") == "agent"}
    passed_names  = [p["name"] for p in state["participants"]
                     if p["id"] in state["agents_passed_this_round"]]
    spoke_names   = [p["name"] for p in state["participants"] if p["id"] in already_spoke]

    context = _full_context(state)

    system = f"""You are the supervisor of a QA group chat. Orchestrate the agents to answer the user's question.

Participants:
{participants_info}

Conversation:
{context}

Turn: {state['turn_count']}/{MAX_TURNS}
Already spoke this round: {', '.join(spoke_names) or 'none'}
Passed (nothing to add): {', '.join(passed_names) or 'none'}

Rules:
- Route to the agent most relevant to the LATEST user question based on their domain.
- Prefer agents who have NOT spoken yet if equally relevant.
- Set is_resolved=true when the question is fully and sufficiently answered.
- Set is_resolved=true if remaining agents are unlikely to add useful domain-specific input.

Reply with ONLY valid JSON — no markdown, no explanation:
{{"next_speaker": "<agent_id or null>", "is_resolved": <true/false>}}"""

    response = call_llm(
        system_prompt=system,
        messages=[HumanMessage(content="Make your routing decision.")],
        tool_definitions=[],
        model=MODEL_NAME,
        provider=LLM_PROVIDER,
        anthropic_api_key=ANTHROPIC_API_KEY,
        openai_api_key=OPENAI_API_KEY,
        openai_base_url=OPENAI_BASE_URL,
        max_tokens=128,
    )

    try:
        text = response.text.strip()
        # Strip markdown code fences if the LLM adds them anyway
        if "```" in text:
            text = text.split("```")[1].lstrip("json").strip()
        decision    = json.loads(text)
        next_speaker = decision.get("next_speaker") or None
        is_resolved  = bool(decision.get("is_resolved", False))
    except Exception:
        # Fallback: pick first participant who hasn't spoken yet
        remaining   = [p["id"] for p in state["participants"] if p["id"] not in already_spoke]
        next_speaker = remaining[0] if remaining else None
        is_resolved  = next_speaker is None

    return {
        "next_speaker": next_speaker,
        "is_resolved":  is_resolved,
        "turn_count":   state["turn_count"] + 1,
    }


# ── L1-only tool definitions (pre-filtered; no HITL needed in group chat) ──────

def _get_l1_tool_definitions() -> list[dict]:
    """Return only L1 tools — safe to auto-execute in group chat without Mentor approval."""
    from tools import get_tool_definitions
    from config import TOOL_RISK_LEVEL
    return [t for t in get_tool_definitions() if TOOL_RISK_LEVEL.get(t["name"], "L1") == "L1"]


_L1_TOOLS = _get_l1_tool_definitions()   # computed once at import time


# ── Agent Node ─────────────────────────────────────────────────────────────────

_MAX_TOOL_ITERS = 5   # Safety cap on the per-agent tool loop


def _make_agent_node(participant: dict):
    """
    Factory: returns a LangGraph node function for the given participant.

    Each agent runs an agentic loop:
      call LLM (with L1 tools) → if tool_calls → execute → append results → repeat
    until the LLM produces a plain-text answer (or MAX iterations reached).
    """
    from langchain_core.messages import ToolMessage
    from tools import execute_tool

    def agent_node(state: GroupChatState) -> dict:
        context    = _full_context(state)
        spec       = participant.get("specialization", "")
        spec_block = f"\n\n【Domain Specialization】\n{spec}" if spec else ""
        domain     = participant.get("product_line", "general")
        name       = participant["name"]

        system = f"""You are {name}, a QA engineer specializing in the {domain} domain.
You are participating in a group QA discussion with other domain specialists.{spec_block}

Your responsibility: contribute ONLY from your domain ({domain}) perspective.
You have access to tools — use them to research the question before answering.
For example: call get_jira_issue to look up a ticket, search_jira to find related issues,
search_knowledge_base for internal rules, get_gitlab_mr_diff to analyse code changes.

Focus on: test coverage gaps, edge cases, risk areas specific to {domain}.

If you have NOTHING relevant to add from your domain (the question is completely outside
your area, or it has already been fully covered), reply with exactly the single word: PASS

Otherwise, research first, then provide your domain-specific analysis (under 400 words)."""

        prompt = f"Full conversation context:\n{context}\n\nYour turn as {name}:"

        # ── Agentic tool loop ──────────────────────────────────────────────────
        # Uses for…else: the else block runs only when the loop exhausts all
        # iterations WITHOUT a break, meaning the LLM never returned a pure-text
        # response.  In that case we force one final text-only call so content
        # is never empty.
        loop_messages: list = [HumanMessage(content=prompt)]
        response = None

        for _ in range(_MAX_TOOL_ITERS):
            response = call_llm(
                system_prompt=system,
                messages=loop_messages,
                tool_definitions=_L1_TOOLS,
                model=MODEL_NAME,
                provider=LLM_PROVIDER,
                anthropic_api_key=ANTHROPIC_API_KEY,
                openai_api_key=OPENAI_API_KEY,
                openai_base_url=OPENAI_BASE_URL,
                max_tokens=2048,
            )

            if not response.tool_calls:
                break   # LLM produced a text-only response → done

            # LLM called tools — execute them and continue the loop
            loop_messages.append(response.to_ai_message())
            for tc in response.tool_calls:
                result = execute_tool(
                    tc["name"], tc["args"],
                    agent_id=participant["id"],
                    conversation_id=None,
                    agent_name=name,
                )
                loop_messages.append(
                    ToolMessage(content=str(result), tool_call_id=tc["id"])
                )
        else:
            # Loop exhausted all iterations: all tool results are in loop_messages
            # but the LLM never produced a final text.  Append an explicit instruction
            # so the model understands it must now write a text summary.
            loop_messages.append(
                HumanMessage(content=(
                    f"You have completed your research. Based on all the information gathered above, "
                    f"please now write your final {domain}-domain analysis in plain text. "
                    f"Do not call any more tools."
                ))
            )
            response = call_llm(
                system_prompt=system,
                messages=loop_messages,
                tool_definitions=[],
                model=MODEL_NAME,
                provider=LLM_PROVIDER,
                anthropic_api_key=ANTHROPIC_API_KEY,
                openai_api_key=OPENAI_API_KEY,
                openai_base_url=OPENAI_BASE_URL,
                max_tokens=2048,
            )
        # ── End loop ───────────────────────────────────────────────────────────

        content = response.text.strip() if response else ""

        # Second-chance: if content is still empty (model returned nothing),
        # make one more explicit text-only request before falling back.
        if not content:
            retry = call_llm(
                system_prompt=system,
                messages=loop_messages + [
                    HumanMessage(content=(
                        f"Please write your {domain} QA analysis now in plain text."
                    ))
                ],
                tool_definitions=[],
                model=MODEL_NAME,
                provider=LLM_PROVIDER,
                anthropic_api_key=ANTHROPIC_API_KEY,
                openai_api_key=OPENAI_API_KEY,
                openai_base_url=OPENAI_BASE_URL,
                max_tokens=2048,
            )
            content = retry.text.strip() if retry else ""

        content = content or f"(No analysis available from {name} — please retry)"
        is_pass = _is_pass(content)

        new_msg = {
            "role":     "agent",
            "agent_id": participant["id"],
            "speaker":  name,
            "emoji":    participant.get("avatar_emoji", "🤖"),
            "content":  "" if is_pass else content,
            "is_pass":  is_pass,
        }

        updates: dict = {"messages": [new_msg]}
        if is_pass:
            updates["agents_passed_this_round"] = (
                state.get("agents_passed_this_round", []) + [participant["id"]]
            )
        return updates

    return agent_node


# ── Routing ────────────────────────────────────────────────────────────────────

def _make_route(participants: list[dict]):
    valid_ids = {p["id"] for p in participants}

    def route_supervisor(state: GroupChatState) -> str:
        if state.get("is_resolved"):
            return END
        if state.get("turn_count", 0) > MAX_TURNS:
            return END
        nxt = state.get("next_speaker")
        if nxt and nxt in valid_ids:
            return nxt
        return END

    return route_supervisor


# ── Builder ────────────────────────────────────────────────────────────────────

def build_group_orchestrator(participants: list[dict]):
    """
    Build and compile a group chat LangGraph for the given participants.

    Args:
        participants: list of dicts with keys:
            id, name, product_line, specialization, avatar_emoji, ranking
    """
    graph = StateGraph(GroupChatState)

    graph.add_node("supervisor", _supervisor_node)

    for p in participants:
        graph.add_node(p["id"], _make_agent_node(p))
        graph.add_edge(p["id"], "supervisor")

    graph.add_conditional_edges("supervisor", _make_route(participants))
    graph.add_edge(START, "supervisor")

    return graph.compile(checkpointer=MemorySaver())
