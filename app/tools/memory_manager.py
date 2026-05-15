"""
Tool: Persistent cross-session memory manager.

Risk Level: L1 (self-execution; writes only to local memory file)

The agent uses this tool to save facts that are worth remembering across sessions:
  - Ongoing project context (sprint, focus features, team conventions)
  - Recent work (tickets analyzed, test cases generated, MRs reviewed)
  - QA notes (known flaky areas, risk patterns, team conventions)
  - User preferences (default project, output style, etc.)

Memory is stored in memory/agent_memory.json and automatically injected
into the system prompt at the start of every new session.

Usage pattern:
  - save_to_memory is called by the agent proactively during conversation
  - load_memory_context() is called by main.py at session start (not a tool)
"""
import copy
import json
import os
from datetime import datetime

from config import MEMORY_FILE

# Maximum entries to keep per rolling list (recent_work, session_summaries)
_MAX_RECENT_WORK     = 20
_MAX_SESSION_SUMMARIES = 5

# Valid category names and their descriptions
CATEGORIES = {
    "active_context":    "Current sprint, focus features, ongoing tasks",
    "recent_work":       "Rolling list: tickets analyzed, test cases generated, MRs reviewed",
    "notes":             "Persistent knowledge: risk areas, team conventions, known issues",
    "user_preferences":  "User preferences: default project, formatting style, etc.",
    "session_summary":   "End-of-session summary (auto-pruned to last 5)",
}

_EMPTY_MEMORY: dict = {
    "active_context":     {},
    "recent_work":        [],
    "notes":              {},
    "user_preferences":   {},
    "session_summaries":  [],
}


# ── Public tool function ───────────────────────────────────────────────────────

def save_to_memory(key: str, value: str, category: str = "notes", agent_id: str = None) -> str:
    """
    Save a fact to persistent memory so it is available in future sessions.

    Args:
        key:      Short identifier for the fact.
                  For "recent_work" and "session_summary", key is used as a label/title.
                  Examples: "default_project", "voucher_risk_areas", "sprint_42_focus"
        value:    The fact or note to save. Keep it concise (1-3 sentences).
        category: One of:
                    "active_context"   — current sprint / feature focus
                    "recent_work"      — log a completed task (rolling, last 20)
                    "notes"            — persistent knowledge / risk patterns
                    "user_preferences" — user settings and preferences
                    "session_summary"  — end-of-session summary (rolling, last 5)

    Returns:
        Confirmation message with what was saved.
    """
    if category not in CATEGORIES:
        return (
            f"[Error] Unknown category '{category}'. "
            f"Valid options: {', '.join(CATEGORIES.keys())}"
        )

    mem_file = os.path.join(os.path.dirname(MEMORY_FILE), f"{agent_id}.json") if agent_id else MEMORY_FILE
    memory = _load_raw(mem_file)
    today  = datetime.now().strftime("%Y-%m-%d")

    if category in ("recent_work", "session_summary"):
        # Rolling list with timestamp
        entry = {"date": today, "label": key, "content": value}
        list_key = "recent_work" if category == "recent_work" else "session_summaries"
        memory.setdefault(list_key, []).append(entry)
        # Prune to max length (keep most recent)
        max_len = _MAX_RECENT_WORK if category == "recent_work" else _MAX_SESSION_SUMMARIES
        memory[list_key] = memory[list_key][-max_len:]
    else:
        # Key-value store with last-updated timestamp
        memory.setdefault(category, {})[key] = {
            "value":   value,
            "updated": today,
        }

    _save_raw(memory, mem_file)

    # Mirror to semantic index (best-effort; never blocks or raises)
    try:
        from tools.semantic_memory import save_to_index
        if category in ("recent_work", "session_summary"):
            list_key = "recent_work" if category == "recent_work" else "session_summaries"
            idx_key  = f"{list_key}_{len(memory.get(list_key, []))}"
            save_to_index(category, idx_key, f"{key}: {value}", agent_id)
        else:
            save_to_index(category, key, f"{key}: {value}", agent_id)
    except Exception:
        pass

    return (
        f"✅ Saved to memory [{category}] → {key}\n"
        f"   This will be available in all future sessions."
    )


# ── Called by main.py / agent.py at session start (not exposed as agent tool) ──

def load_memory_context(agent_id: str = None, query: str = None) -> str:
    """
    Load persistent memory and format it as a context string for injection
    into the system prompt. Returns empty string if memory is empty.

    Args:
        agent_id: Which agent's memory to load (None = terminal mode default).
        query:    Current user message used for semantic retrieval.
                  If provided and ChromaDB is available, returns only the most
                  relevant memory fragments (top-5 by cosine similarity).
                  Falls back to full JSON context if semantic search fails.
    """
    mem_file = os.path.join(os.path.dirname(MEMORY_FILE), f"{agent_id}.json") if agent_id else MEMORY_FILE
    memory = _load_raw(mem_file)

    # ── Semantic retrieval path ────────────────────────────────────────────────
    if query:
        try:
            from tools.semantic_memory import search, rebuild_index
            hits = search(query, agent_id, n_results=5)
            if not hits:
                # Index may be empty (first use, or pre-existing agent): rebuild from JSON
                rebuild_index(memory, agent_id)
                hits = search(query, agent_id, n_results=5)
            if hits:
                lines = [f"  • [{h['category']}] {h['text']} (relevance: {h['score']:.2f})" for h in hits]
                header = "═══ Relevant Memory (semantically matched to current query) ═══"
                footer = "═══ End of Memory ═══"
                return "\n\n" + header + "\n" + "\n".join(lines) + "\n" + footer
        except Exception:
            pass   # Fall through to full JSON context below

    sections = []

    # User preferences
    prefs = memory.get("user_preferences", {})
    if prefs:
        pref_lines = [
            f"  - {k}: {v['value']}" for k, v in prefs.items()
            if isinstance(v, dict) and v.get("value")
        ]
        if pref_lines:
            sections.append("User Preferences:\n" + "\n".join(pref_lines))

    # Active context
    ctx = memory.get("active_context", {})
    if ctx:
        ctx_lines = [
            f"  - {k}: {v['value']}" for k, v in ctx.items()
            if isinstance(v, dict) and v.get("value")
        ]
        if ctx_lines:
            sections.append("Active Project Context:\n" + "\n".join(ctx_lines))

    # Notes
    notes = memory.get("notes", {})
    if notes:
        note_lines = [
            f"  - {k}: {v['value']}" for k, v in notes.items()
            if isinstance(v, dict) and v.get("value")
        ]
        if note_lines:
            sections.append("Knowledge & Notes:\n" + "\n".join(note_lines))

    # Recent work (last 10)
    recent = memory.get("recent_work", [])[-10:]
    if recent:
        work_lines = [
            f"  - [{e.get('date', '')}] {e.get('label', '')}: {e.get('content', '')}"
            for e in reversed(recent)
        ]
        sections.append("Recent Work (last 10 entries):\n" + "\n".join(work_lines))

    # Session summaries (last 3)
    summaries = memory.get("session_summaries", [])[-3:]
    if summaries:
        sum_lines = [
            f"  - [{e.get('date', '')}] {e.get('content', '')}"
            for e in reversed(summaries)
        ]
        sections.append("Recent Session Summaries:\n" + "\n".join(sum_lines))

    if not sections:
        return ""

    header = "═══ Persistent Memory (from previous sessions) ═══"
    footer = "═══ End of Persistent Memory ═══"
    return "\n\n" + header + "\n" + "\n\n".join(sections) + "\n" + footer


# ── Internal helpers ───────────────────────────────────────────────────────────

def _load_raw(memory_file: str = None) -> dict:
    """Load raw memory dict from JSON file, returning empty structure if missing."""
    if memory_file is None:
        memory_file = MEMORY_FILE
    if not os.path.exists(memory_file):
        return copy.deepcopy(_EMPTY_MEMORY)
    try:
        with open(memory_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Ensure all expected keys exist
        for k, v in _EMPTY_MEMORY.items():
            data.setdefault(k, type(v)())
        return data
    except (json.JSONDecodeError, OSError):
        return copy.deepcopy(_EMPTY_MEMORY)


def _save_raw(memory: dict, memory_file: str = None) -> None:
    """Write memory dict to JSON file, creating directory if needed."""
    if memory_file is None:
        memory_file = MEMORY_FILE
    os.makedirs(os.path.dirname(memory_file), exist_ok=True)
    with open(memory_file, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)
