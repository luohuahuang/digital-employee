"""
Lightweight test runner for test_suggester and test_semantic_memory.
Works without pytest — uses pure Python unittest + simple monkeypatching.
"""
import sys
import os
import json
import tempfile
import pathlib
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0


def ok(name):
    global PASS
    PASS += 1
    print(f"  ✅  {name}")


def fail(name, exc):
    global FAIL
    FAIL += 1
    print(f"  ❌  {name}")
    traceback.print_exc()


# ─────────────────────────────── SUGGESTER TESTS ──────────────────────────────

from eval.suggester import build_suggester_prompt

def t_prompt_contains_current_prompt():
    p = build_suggester_prompt("You are a QA agent.", "Scenario", "Input", "Output", ["kw"], {})
    assert "You are a QA agent." in p

def t_prompt_lists_missed_keywords():
    p = build_suggester_prompt("Prompt", "S", "I", "O", ["foo", "bar"], {})
    assert '"foo"' in p and '"bar"' in p

def t_prompt_no_keywords_shows_none():
    p = build_suggester_prompt("Prompt", "S", "I", "O", [], {})
    assert "none" in p.lower()

def t_prompt_includes_judge_failures():
    judge = {
        "clarity":  {"score": 1, "reasoning": "Too vague", "evidence": "e"},
        "coverage": {"score": 3, "reasoning": "Perfect",  "evidence": ""},
    }
    p = build_suggester_prompt("Prompt", "S", "I", "O", [], judge)
    assert "clarity" in p and "Too vague" in p
    assert "Perfect" not in p

def t_prompt_truncates_long_output():
    long_output = "x" * 1500 + "UNIQUE_TAIL_BEYOND_LIMIT" + "y" * 3000
    p = build_suggester_prompt("Prompt", "S", "I", long_output, [], {})
    assert "x" * 1500 in p
    assert "UNIQUE_TAIL_BEYOND_LIMIT" not in p

def t_build_prompt_is_deterministic():
    kwargs = dict(current_prompt="P", exam_scenario="S", input_message="I",
                  agent_output="O", missed_keywords=["kw"],
                  judge_results={"c": {"score": 2, "reasoning": "ok", "evidence": "e"}})
    assert build_suggester_prompt(**kwargs) == build_suggester_prompt(**kwargs)

SUGGESTER_TESTS = [
    t_prompt_contains_current_prompt,
    t_prompt_lists_missed_keywords,
    t_prompt_no_keywords_shows_none,
    t_prompt_includes_judge_failures,
    t_prompt_truncates_long_output,
    t_build_prompt_is_deterministic,
]


# ─────────────────────────────── SEMANTIC MEMORY TESTS ────────────────────────

class _FakeCollection:
    def __init__(self):
        self._docs = {}

    def count(self):
        return len(self._docs)

    def upsert(self, ids, documents, metadatas):
        for i, doc, meta in zip(ids, documents, metadatas):
            self._docs[i] = {"document": doc, "metadata": meta}

    def delete(self, ids):
        for i in ids: self._docs.pop(i, None)

    def get(self):
        return {"ids": list(self._docs.keys())}

    def query(self, query_texts, n_results, include):
        items = list(self._docs.values())[:n_results]
        return {
            "documents": [[it["document"] for it in items]],
            "metadatas": [[it["metadata"] for it in items]],
            "distances": [[0.1 * (i + 1) for i in range(len(items))]],
        }


import tools.semantic_memory as sm
import tools.memory_manager as mm

_ORIG_GET_COLLECTION = sm._get_collection

def _patch_sm(col):
    sm._get_collection = lambda agent_id: col

def _unpatch_sm():
    sm._get_collection = _ORIG_GET_COLLECTION


def t_save_and_search():
    col = _FakeCollection()
    _patch_sm(col)
    try:
        sm.save_to_index("notes", "risk", "Payment flow is high risk", "a1")
        sm.save_to_index("notes", "pattern", "Idempotency bugs", "a1")
        results = sm.search("payment risks", "a1", n_results=5)
        assert len(results) == 2
        assert all("category" in r and "text" in r and "score" in r for r in results)
    finally:
        _unpatch_sm()

def t_search_empty_collection():
    col = _FakeCollection()
    _patch_sm(col)
    try:
        assert sm.search("anything", "empty", n_results=5) == []
    finally:
        _unpatch_sm()

def t_search_returns_empty_on_no_collection():
    _patch_sm(None)
    try:
        assert sm.search("query", "a1", n_results=5) == []
    finally:
        _unpatch_sm()

def t_delete_from_index():
    col = _FakeCollection()
    _patch_sm(col)
    try:
        sm.save_to_index("notes", "del_me", "Will be removed", "a1")
        assert col.count() == 1
        sm.delete_from_index("notes", "del_me", "a1")
        assert col.count() == 0
    finally:
        _unpatch_sm()

def t_rebuild_index():
    col = _FakeCollection()
    _patch_sm(col)
    try:
        memory = {
            "active_context":   {"sprint": {"value": "Sprint 42", "updated": "2026-05-01"}},
            "notes":         {"risk":   {"value": "DB is risky", "updated": "2026-05-01"}},
            "user_preferences": {"proj":   {"value": "SHOP",       "updated": "2026-05-01"}},
            "recent_work":      [{"date": "2026-05-01", "label": "T1", "content": "Analyzed"}],
            "session_summaries":[{"date": "2026-05-01", "content": "Reviewed"}],
        }
        count = sm.rebuild_index(memory, "a1")
        assert count == 5
        assert col.count() == 5
    finally:
        _unpatch_sm()

def t_rebuild_empty_memory():
    col = _FakeCollection()
    _patch_sm(col)
    try:
        assert sm.rebuild_index({}, "a1") == 0
    finally:
        _unpatch_sm()

def t_save_noop_on_empty_text():
    col = _FakeCollection()
    _patch_sm(col)
    try:
        sm.save_to_index("notes", "key", "", "a1")
        assert col.count() == 0
    finally:
        _unpatch_sm()


# memory_manager JSON round-trips
_ORIG_MEMORY_FILE = mm.MEMORY_FILE

def t_save_and_load_qa_note():
    with tempfile.TemporaryDirectory() as td:
        mem_file = os.path.join(td, "mem.json")
        mm.MEMORY_FILE = mem_file
        # Disable semantic side-effect
        _orig = getattr(sm, 'save_to_index', None)
        sm.save_to_index = lambda *a, **kw: None
        try:
            r = mm.save_to_memory("db_risk", "DB migration is high risk", "notes")
            assert "Saved" in r
            ctx = mm.load_memory_context(agent_id=None, query=None)
            assert "DB migration is high risk" in ctx
        finally:
            mm.MEMORY_FILE = _ORIG_MEMORY_FILE
            if _orig: sm.save_to_index = _orig

def t_recent_work_rolling():
    with tempfile.TemporaryDirectory() as td:
        mm.MEMORY_FILE = os.path.join(td, "mem.json")
        _orig = getattr(sm, 'save_to_index', None)
        sm.save_to_index = lambda *a, **kw: None
        try:
            for i in range(25):
                mm.save_to_memory(f"t-{i}", f"Content {i}", "recent_work")
            data = mm._load_raw(mm.MEMORY_FILE)
            assert len(data["recent_work"]) == mm._MAX_RECENT_WORK
        finally:
            mm.MEMORY_FILE = _ORIG_MEMORY_FILE
            if _orig: sm.save_to_index = _orig

def t_load_empty_returns_empty_string():
    with tempfile.TemporaryDirectory() as td:
        mm.MEMORY_FILE = os.path.join(td, "nonexistent.json")
        try:
            assert mm.load_memory_context() == ""
        finally:
            mm.MEMORY_FILE = _ORIG_MEMORY_FILE

def t_invalid_category_returns_error():
    with tempfile.TemporaryDirectory() as td:
        mm.MEMORY_FILE = os.path.join(td, "mem.json")
        try:
            r = mm.save_to_memory("k", "v", "invalid_category")
            assert "Error" in r or "Unknown" in r
        finally:
            mm.MEMORY_FILE = _ORIG_MEMORY_FILE

def t_load_with_query_uses_semantic():
    with tempfile.TemporaryDirectory() as td:
        mm.MEMORY_FILE = os.path.join(td, "mem.json")
        _orig_save = getattr(sm, 'save_to_index', None)
        sm.save_to_index = lambda *a, **kw: None
        mm.save_to_memory("risk", "Payment is high risk", "notes")

        _orig_search  = getattr(sm, 'search', None)
        _orig_rebuild = getattr(sm, 'rebuild_index', None)
        sm.search        = lambda q, aid, n_results=5: [{"category": "notes", "key": "risk", "text": "Payment is high risk", "score": 0.92}]
        sm.rebuild_index = lambda m, aid: 1
        try:
            ctx = mm.load_memory_context(agent_id=None, query="payment")
            assert "semantically matched" in ctx
            assert "Payment is high risk" in ctx
        finally:
            mm.MEMORY_FILE = _ORIG_MEMORY_FILE
            if _orig_save:   sm.save_to_index  = _orig_save
            if _orig_search: sm.search         = _orig_search
            if _orig_rebuild:sm.rebuild_index  = _orig_rebuild

def t_load_with_query_fallback_on_empty_results():
    with tempfile.TemporaryDirectory() as td:
        mm.MEMORY_FILE = os.path.join(td, "mem.json")
        _orig_save = getattr(sm, 'save_to_index', None)
        sm.save_to_index = lambda *a, **kw: None
        mm.save_to_memory("sprint", "Sprint 42 focus", "active_context")

        _orig_search  = getattr(sm, 'search', None)
        _orig_rebuild = getattr(sm, 'rebuild_index', None)
        sm.search        = lambda *a, **kw: []
        sm.rebuild_index = lambda *a, **kw: 0
        try:
            ctx = mm.load_memory_context(agent_id=None, query="something")
            assert "Sprint 42" in ctx
            assert "semantically matched" not in ctx
        finally:
            mm.MEMORY_FILE = _ORIG_MEMORY_FILE
            if _orig_save:   sm.save_to_index  = _orig_save
            if _orig_search: sm.search         = _orig_search
            if _orig_rebuild:sm.rebuild_index  = _orig_rebuild

def t_load_with_query_fallback_on_exception():
    with tempfile.TemporaryDirectory() as td:
        mm.MEMORY_FILE = os.path.join(td, "mem.json")
        _orig_save = getattr(sm, 'save_to_index', None)
        sm.save_to_index = lambda *a, **kw: None
        mm.save_to_memory("note", "Fallback test value", "notes")

        _orig_search  = getattr(sm, 'search', None)
        _orig_rebuild = getattr(sm, 'rebuild_index', None)
        def _raise(*a, **kw): raise RuntimeError("ChromaDB unavailable")
        sm.search        = _raise
        sm.rebuild_index = _raise
        try:
            ctx = mm.load_memory_context(agent_id=None, query="anything")
            assert "Fallback test value" in ctx
        finally:
            mm.MEMORY_FILE = _ORIG_MEMORY_FILE
            if _orig_save:   sm.save_to_index  = _orig_save
            if _orig_search: sm.search         = _orig_search
            if _orig_rebuild:sm.rebuild_index  = _orig_rebuild


SEMANTIC_TESTS = [
    t_save_and_search,
    t_search_empty_collection,
    t_search_returns_empty_on_no_collection,
    t_delete_from_index,
    t_rebuild_index,
    t_rebuild_empty_memory,
    t_save_noop_on_empty_text,
    t_save_and_load_qa_note,
    t_recent_work_rolling,
    t_load_empty_returns_empty_string,
    t_invalid_category_returns_error,
    t_load_with_query_uses_semantic,
    t_load_with_query_fallback_on_empty_results,
    t_load_with_query_fallback_on_exception,
]


# ─────────────────────────────── RUNNER ───────────────────────────────────────

def run_suite(name, tests):
    print(f"\n{'─'*60}")
    print(f"  {name}")
    print(f"{'─'*60}")
    for t in tests:
        try:
            t()
            ok(t.__name__)
        except Exception:
            fail(t.__name__, None)


if __name__ == "__main__":
    run_suite("Suggester — build_suggester_prompt", SUGGESTER_TESTS)
    run_suite("Semantic Memory + Memory Manager", SEMANTIC_TESTS)

    print(f"\n{'═'*60}")
    total = PASS + FAIL
    print(f"  Results: {PASS}/{total} passed   {'✅ ALL PASS' if FAIL == 0 else f'❌ {FAIL} FAILED'}")
    print(f"{'═'*60}\n")
    sys.exit(0 if FAIL == 0 else 1)
