"""
Tests for tools/semantic_memory.py and the updated memory_manager.py.

Strategy:
  - Test semantic_memory with a lightweight in-memory stub collection (no real ChromaDB/API).
  - Test memory_manager save/load round-trips fully (no LLM, no embeddings needed for JSON path).
  - Test that load_memory_context falls back to full JSON when semantic search returns nothing.
"""
import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_memory_file(tmp_path, data: dict) -> str:
    """Write a memory JSON file and return its path."""
    p = str(tmp_path / "test_agent.json")
    with open(p, "w") as f:
        json.dump(data, f)
    return p


# ── semantic_memory module (unit tests with mocked ChromaDB) ──────────────────

class _FakeCollection:
    """Minimal in-memory stub that mimics the ChromaDB collection API."""
    def __init__(self):
        self._docs = {}   # id -> {document, metadata}

    def count(self):
        return len(self._docs)

    def upsert(self, ids, documents, metadatas):
        for i, doc, meta in zip(ids, documents, metadatas):
            self._docs[i] = {"document": doc, "metadata": meta}

    def delete(self, ids):
        for i in ids:
            self._docs.pop(i, None)

    def get(self):
        return {"ids": list(self._docs.keys())}

    def query(self, query_texts, n_results, include):
        # Return all docs (no real ranking — stub just returns them in insertion order)
        items = list(self._docs.values())[:n_results]
        return {
            "documents": [[it["document"] for it in items]],
            "metadatas": [[it["metadata"] for it in items]],
            "distances": [[0.1 * (i + 1) for i in range(len(items))]],
        }


def test_save_to_index_and_search(monkeypatch):
    import tools.semantic_memory as sm
    col = _FakeCollection()
    monkeypatch.setattr(sm, "_get_collection", lambda agent_id: col)

    sm.save_to_index("notes", "risk_area", "Payment flow is high risk", "agent-1")
    sm.save_to_index("notes", "pattern",   "Idempotency bugs are common", "agent-1")

    results = sm.search("payment risks", "agent-1", n_results=5)
    assert len(results) == 2
    assert all("category" in r and "text" in r and "score" in r for r in results)


def test_search_returns_empty_when_collection_empty(monkeypatch):
    import tools.semantic_memory as sm
    col = _FakeCollection()
    monkeypatch.setattr(sm, "_get_collection", lambda agent_id: col)

    results = sm.search("anything", "empty-agent", n_results=5)
    assert results == []


def test_search_returns_empty_on_collection_failure(monkeypatch):
    import tools.semantic_memory as sm
    monkeypatch.setattr(sm, "_get_collection", lambda agent_id: None)

    results = sm.search("query", "agent-1", n_results=5)
    assert results == []


def test_delete_from_index(monkeypatch):
    import tools.semantic_memory as sm
    col = _FakeCollection()
    monkeypatch.setattr(sm, "_get_collection", lambda agent_id: col)

    sm.save_to_index("notes", "to_delete", "Will be removed", "agent-1")
    assert col.count() == 1
    sm.delete_from_index("notes", "to_delete", "agent-1")
    assert col.count() == 0


def test_rebuild_index(monkeypatch):
    import tools.semantic_memory as sm
    col = _FakeCollection()
    monkeypatch.setattr(sm, "_get_collection", lambda agent_id: col)

    memory = {
        "active_context":   {"sprint": {"value": "Sprint 42 focused on checkout", "updated": "2026-05-01"}},
        "notes":         {"risk": {"value": "DB migration is risky", "updated": "2026-05-01"}},
        "user_preferences": {"project": {"value": "Default project is SHOP", "updated": "2026-05-01"}},
        "recent_work":      [{"date": "2026-05-01", "label": "SHOP-123", "content": "Analyzed cart MR"}],
        "session_summaries": [{"date": "2026-05-01", "content": "Reviewed checkout flow"}],
    }
    count = sm.rebuild_index(memory, "agent-1")
    assert count == 5
    assert col.count() == 5


def test_rebuild_index_empty_memory(monkeypatch):
    import tools.semantic_memory as sm
    col = _FakeCollection()
    monkeypatch.setattr(sm, "_get_collection", lambda agent_id: col)

    count = sm.rebuild_index({}, "agent-1")
    assert count == 0


def test_save_to_index_noop_on_empty_text(monkeypatch):
    import tools.semantic_memory as sm
    col = _FakeCollection()
    monkeypatch.setattr(sm, "_get_collection", lambda agent_id: col)

    sm.save_to_index("notes", "key", "", "agent-1")
    assert col.count() == 0


# ── memory_manager JSON round-trip (no embeddings needed) ─────────────────────

def test_save_and_load_qa_note(tmp_path, monkeypatch):
    """save_to_memory writes JSON; load_memory_context (no query) reads it back."""
    from tools import memory_manager as mm

    mem_file = str(tmp_path / "agent_test.json")
    monkeypatch.setattr(mm, "MEMORY_FILE", mem_file)
    # Disable semantic indexing side-effect
    monkeypatch.setattr("tools.memory_manager.save_to_index", lambda *a, **kw: None, raising=False)

    result = mm.save_to_memory(
        key="db_risk",
        value="DB migration is high risk during peak traffic",
        category="notes",
        agent_id=None,
    )
    assert "Saved" in result

    context = mm.load_memory_context(agent_id=None, query=None)
    assert "DB migration is high risk" in context


def test_save_recent_work_rolling(tmp_path, monkeypatch):
    from tools import memory_manager as mm
    mem_file = str(tmp_path / "agent_rw.json")
    monkeypatch.setattr(mm, "MEMORY_FILE", mem_file)
    monkeypatch.setattr("tools.memory_manager.save_to_index", lambda *a, **kw: None, raising=False)

    for i in range(25):
        mm.save_to_memory(key=f"ticket-{i}", value=f"Analyzed issue {i}", category="recent_work")

    data = mm._load_raw(mem_file)
    assert len(data["recent_work"]) == mm._MAX_RECENT_WORK   # capped at 20


def test_load_memory_empty_file(tmp_path, monkeypatch):
    from tools import memory_manager as mm
    monkeypatch.setattr(mm, "MEMORY_FILE", str(tmp_path / "nonexistent.json"))
    ctx = mm.load_memory_context(agent_id=None, query=None)
    assert ctx == ""


def test_load_memory_invalid_category(tmp_path, monkeypatch):
    from tools import memory_manager as mm
    mem_file = str(tmp_path / "agent_bad.json")
    monkeypatch.setattr(mm, "MEMORY_FILE", mem_file)

    result = mm.save_to_memory(key="k", value="v", category="invalid_category")
    assert "Error" in result or "Unknown" in result


# ── load_memory_context with semantic path ─────────────────────────────────────

def test_load_memory_with_query_uses_semantic(tmp_path, monkeypatch):
    """When query is given and semantic search succeeds, return semantic results."""
    from tools import memory_manager as mm

    mem_file = str(tmp_path / "agent_sem.json")
    monkeypatch.setattr(mm, "MEMORY_FILE", mem_file)

    # Populate some memory
    monkeypatch.setattr("tools.memory_manager.save_to_index", lambda *a, **kw: None, raising=False)
    mm.save_to_memory("risk_area", "Payment is high risk", "notes")

    # Mock semantic search to return a result
    fake_hits = [
        {"category": "notes", "key": "risk_area", "text": "notes risk_area: Payment is high risk", "score": 0.92}
    ]
    monkeypatch.setattr("tools.memory_manager.search", lambda q, aid, n_results=5: fake_hits, raising=False)
    monkeypatch.setattr("tools.memory_manager.rebuild_index", lambda m, aid: 1, raising=False)

    ctx = mm.load_memory_context(agent_id=None, query="payment risks")
    assert "semantically matched" in ctx
    assert "Payment is high risk" in ctx


def test_load_memory_with_query_falls_back_to_json_on_empty_results(tmp_path, monkeypatch):
    """When semantic search returns nothing, fall back to full JSON context."""
    from tools import memory_manager as mm

    mem_file = str(tmp_path / "agent_fallback.json")
    monkeypatch.setattr(mm, "MEMORY_FILE", mem_file)
    monkeypatch.setattr("tools.memory_manager.save_to_index", lambda *a, **kw: None, raising=False)
    mm.save_to_memory("sprint", "Sprint 42 focus: voucher redemption", "active_context")

    # Semantic search always returns nothing
    monkeypatch.setattr("tools.memory_manager.search",        lambda *a, **kw: [],  raising=False)
    monkeypatch.setattr("tools.memory_manager.rebuild_index", lambda *a, **kw: 0,  raising=False)

    ctx = mm.load_memory_context(agent_id=None, query="something")
    # Should fall back to full JSON dump which includes the active_context entry
    assert "Sprint 42" in ctx
    assert "semantically matched" not in ctx


def test_load_memory_with_query_falls_back_on_exception(tmp_path, monkeypatch):
    """When semantic search raises, fall back gracefully."""
    from tools import memory_manager as mm

    mem_file = str(tmp_path / "agent_exc.json")
    monkeypatch.setattr(mm, "MEMORY_FILE", mem_file)
    monkeypatch.setattr("tools.memory_manager.save_to_index", lambda *a, **kw: None, raising=False)
    mm.save_to_memory("note", "Fallback test value", "notes")

    def _raise(*a, **kw):
        raise RuntimeError("ChromaDB unavailable")

    monkeypatch.setattr("tools.memory_manager.search", _raise, raising=False)
    monkeypatch.setattr("tools.memory_manager.rebuild_index", _raise, raising=False)

    ctx = mm.load_memory_context(agent_id=None, query="anything")
    assert "Fallback test value" in ctx
