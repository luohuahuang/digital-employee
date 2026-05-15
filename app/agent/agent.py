"""
Core Agent for Digital Employee, built on LangGraph.

Graph structure:
  ┌─────────────────────────────────────────┐
  │  START                                  │
  │    ↓                                    │
  │  [agent] ← LLM reasoning node           │
  │    ↓ Tool calls?                        │
  │  [check_risk] ← Risk level check        │
  │    ↓ L1 (autonomous)                    │
  │  [tools] ← Execute tools                │
  │    ↓ L2 (needs approval)                │
  │  [human_review] ← Await Mentor approval │
  │    ↓                                    │
  │  Back to [agent] for continued reasoning │
  │    ↓ No tool calls                      │
  │  END                                    │
  └─────────────────────────────────────────┘

Corresponds to design document: §5.6 Collaboration Structure (Human-in-the-loop), §6.2 T1 Permission Hierarchy.
"""
from __future__ import annotations

from typing import Literal

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.runnables import RunnableConfig

from config import (
    ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENAI_BASE_URL,
    MODEL_NAME, LLM_PROVIDER, AGENT_ID, AGENT_VERSION, TOOL_RISK_LEVEL,
)
from agent.state import AgentState
from agent.prompts import build_system_prompt
from tools.memory_manager import load_memory_context
from agent.llm_client import call_llm
from tools import get_tool_definitions, execute_tool


# ── Node: LLM Reasoning ────────────────────────────────────────────────────────────

def agent_node(state: AgentState, config: RunnableConfig = None) -> dict:
    """
    Call LLM to reason and decide next action (invoke tool or output conclusion).
    Supports Anthropic/OpenAI via llm_client adapter layer without modifying this node.
    """
    cfg = (config or {}).get("configurable", {})
    agent_id = cfg.get("agent_id")
    conversation_id = cfg.get("thread_id")
    agent_name = cfg.get("agent_name", "")
    specialization = cfg.get("specialization", "")
    ranking = cfg.get("ranking", "Intern")
    base_prompt = cfg.get("base_prompt", "")

    # Extract latest user message to drive semantic memory retrieval
    from langchain_core.messages import HumanMessage as _HM
    _last_user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, _HM) and isinstance(m.content, str)),
        None,
    )
    system_prompt = build_system_prompt(
        AGENT_ID, AGENT_VERSION,
        load_memory_context(agent_id=agent_id, query=_last_user_query),
        specialization=specialization,
        ranking=ranking,
        base_prompt=base_prompt,
    )

    import time as _time
    from tools.audit_logger import log_llm_call

    # token_callback is injected by the WebSocket handler for streaming output
    token_callback = cfg.get("token_callback")
    # trace_id groups all audit entries in one chat turn (P0 chain tracing)
    trace_id = cfg.get("trace_id")

    _t0 = _time.time()
    response = call_llm(
        system_prompt=system_prompt,
        messages=state["messages"],
        tool_definitions=get_tool_definitions(),
        model=MODEL_NAME,
        provider=LLM_PROVIDER,
        anthropic_api_key=ANTHROPIC_API_KEY,
        openai_api_key=OPENAI_API_KEY,
        openai_base_url=OPENAI_BASE_URL,
        token_callback=token_callback,
    )
    log_llm_call(
        agent_id=agent_id or AGENT_ID,
        agent_name=agent_name,
        conversation_id=conversation_id,
        model=MODEL_NAME,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        duration_ms=int((_time.time() - _t0) * 1000),
        trace_id=trace_id,
        node_name="agent",
    )

    ai_message = response.to_ai_message()
    text_content = response.text

    # Escalation detection: LLM output contains "recommend Mentor confirmation" or "beyond capability"
    escalated = any(kw in text_content for kw in ["recommend Mentor confirmation", "beyond capability", "needs escalation"])

    return {
        "messages": [ai_message],
        "escalated": escalated,
        "escalation_reason": text_content[:200] if escalated else "",
    }


# ── Node: Risk Check + Tool Execution ─────────────────────────────────────────────────

def tools_node(state: AgentState, config: RunnableConfig = None) -> dict:
    """
    Execute L1 (autonomous) tool calls and return results.
    L2 tools do not reach this node (intercepted by routing, redirected to human_review).
    """
    from langchain_core.messages import ToolMessage

    cfg = (config or {}).get("configurable", {})
    agent_id = cfg.get("agent_id")
    conversation_id = cfg.get("thread_id")
    agent_name = cfg.get("agent_name", "")
    trace_id = cfg.get("trace_id")

    last_msg = state["messages"][-1]
    tool_messages = []

    for tc in last_msg.tool_calls:
        result = execute_tool(
            tc["name"], tc["args"],
            agent_id=agent_id,
            conversation_id=conversation_id,
            agent_name=agent_name,
            trace_id=trace_id,
            node_name="tools",
        )
        tool_messages.append(
            ToolMessage(content=str(result), tool_call_id=tc["id"])
        )

    return {"messages": tool_messages}


def human_review_node(state: AgentState, config: RunnableConfig = None) -> dict:
    """
    L2 tools require Mentor approval.
    LangGraph will interrupt BEFORE this node (interrupt_before=["human_review"]).
    External code (main.py / chat.py) handles the approval dialog, then resumes
    the graph with app.stream(None, ...).  This node runs on resumption.

    IMPORTANT: Must execute ALL tool_calls in the last AI message — not just the
    L2 ones.  The router sends the batch here whenever any L2 tool is present,
    which means L1 tools in the same batch never reach the tools_node.  If we
    only run L2 tools here, the L1 tool_use blocks end up without corresponding
    tool_result blocks, causing an Anthropic API 400 error on the next LLM call.
    """
    cfg = (config or {}).get("configurable", {})
    agent_id = cfg.get("agent_id")
    conversation_id = cfg.get("thread_id")
    agent_name = cfg.get("agent_name", "")
    trace_id = cfg.get("trace_id")

    last_msg = state["messages"][-1]

    from langchain_core.messages import ToolMessage
    tool_messages = []
    for tc in last_msg.tool_calls:          # ← ALL calls, not just L2
        result = execute_tool(
            tc["name"], tc["args"],
            agent_id=agent_id,
            conversation_id=conversation_id,
            agent_name=agent_name,
            trace_id=trace_id,
            node_name="human_review",
        )
        tool_messages.append(
            ToolMessage(content=str(result), tool_call_id=tc["id"])
        )

    return {"messages": tool_messages, "pending_approval": False}


# ── Ranking → permission ceiling ──────────────────────────────────────────────────────
# Intern/Junior can auto-execute up to L1; Senior up to L2; Lead up to L3.
_RANKING_CEILING = {"Intern": 1, "Junior": 1, "Senior": 2, "Lead": 3}
_RISK_NUM = {"L1": 1, "L2": 2, "L3": 3}


# ── Routing Function ──────────────────────────────────────────────────────────────────

def route_after_agent(state: AgentState, config: RunnableConfig = None) -> Literal["tools", "human_review", "__end__"]:
    """
    Decide next step after LLM reasoning:
      - No tool calls → End
      - All tool risk levels ≤ agent ranking ceiling → Execute directly
      - Any tool risk level > agent ranking ceiling → Route to human_review (await Mentor)
    """
    last_msg = state["messages"][-1]
    if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
        return END

    cfg = (config or {}).get("configurable", {})
    ranking = cfg.get("ranking", "Intern")

    # Use DB-backed config if injected; fall back to hardcoded constants
    tool_risk = cfg.get("tool_risk_level") or TOOL_RISK_LEVEL
    ranking_ceilings = cfg.get("ranking_ceilings") or {}
    ceiling_str = ranking_ceilings.get(ranking)
    ceiling = _RISK_NUM.get(ceiling_str, _RANKING_CEILING.get(ranking, 1))

    for tc in last_msg.tool_calls:
        risk = _RISK_NUM.get(tool_risk.get(tc["name"], "L1"), 1)
        if risk > ceiling:
            return "human_review"

    return "tools"


# ── Build Graph ────────────────────────────────────────────────────────────────────

def build_agent():
    """
    Assemble complete QA Agent graph and return executable CompiledGraph.
    checkpointer=MemorySaver() gives each conversation independent thread state and supports interrupt/resume.
    """
    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("human_review", human_review_node)

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent)
    graph.add_edge("tools", "agent")       # After tool execution, return to LLM for continued reasoning
    graph.add_edge("human_review", "agent")

    # interrupt_before="human_review": Pause before reaching this node, awaiting external approval injection
    checkpointer = MemorySaver()
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review"],
    )


def run_agent(user_message: str, thread_id: str = "default") -> str:
    """
    Convenience interface: take user message, return final text output.
    Suitable for single-turn conversations (eval script calls).
    """
    from langchain_core.messages import HumanMessage

    app = build_agent()
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "task_id": thread_id,
        "task_description": user_message,
        "pending_approval": False,
        "escalated": False,
        "escalation_reason": "",
    }

    final_state = app.invoke(initial_state, config=config)
    last_msg = final_state["messages"][-1]
    return last_msg.content if hasattr(last_msg, "content") else str(last_msg)
