"""
Semantic Memory Index — ChromaDB-backed vector store for agent memory.

Design:
  - JSON file remains the source of truth (backward compat, human-readable, simple)
  - This module maintains a ChromaDB collection as a semantic search index on top of the JSON
  - save_to_index()  — called by memory_manager.save_to_memory after each write
  - search()        — called by memory_manager.load_memory_context when a query is given
  - rebuild_index() — rebuilds the full index from a JSON memory dict (migration / repair)

Collection name: agent_memory_{agent_id}  (or "agent_memory_default" for terminal mode)

Graceful degradation:
  Every public function catches all exceptions and returns a safe default.
  If OpenAI embeddings are unavailable, callers fall back to full JSON context.
"""
from __future__ import annotations

import hashlib
from typing import Any

from config import CHROMA_DB_PATH, EMBEDDING_API_KEY, EMBEDDING_MODEL


def _collection_name(agent_id: str | None) -> str:
    safe = (agent_id or "default").replace("-", "_")[:40]
    return f"agent_memory_{safe}"


def _get_collection(agent_id: str | None):
    """Return (or create) the ChromaDB collection for this agent. Returns None on failure."""
    try:
        import chromadb
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        ef = OpenAIEmbeddingFunction(api_key=EMBEDDING_API_KEY, model_name=EMBEDDING_MODEL)
        return client.get_or_create_collection(
            name=_collection_name(agent_id),
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    except Exception:
        return None


def _entry_id(category: str, key: str) -> str:
    """Stable document ID derived from category + key."""
    return hashlib.md5(f"{category}::{key}".encode()).hexdigest()


def save_to_index(category: str, key: str, text: str, agent_id: str | None) -> None:
    """
    Upsert a single memory entry into the semantic index.
    Silently no-ops if ChromaDB or embeddings are unavailable.
    """
    if not text:
        return
    try:
        col = _get_collection(agent_id)
        if col is None:
            return
        doc_id = _entry_id(category, key)
        col.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[{"category": category, "key": key}],
        )
    except Exception:
        pass


def delete_from_index(category: str, key: str, agent_id: str | None) -> None:
    """Remove a single memory entry from the index (e.g. after rolling-list pruning)."""
    try:
        col = _get_collection(agent_id)
        if col is None:
            return
        col.delete(ids=[_entry_id(category, key)])
    except Exception:
        pass


def search(query: str, agent_id: str | None, n_results: int = 5) -> list[dict]:
    """
    Semantic search over this agent's memory index.

    Returns list of {category, key, text, score} sorted by relevance.
    Returns empty list on any failure (caller falls back to full JSON).
    """
    if not query:
        return []
    try:
        col = _get_collection(agent_id)
        if col is None:
            return []
        count = col.count()
        if count == 0:
            return []
        actual_n = min(n_results, count)
        results = col.query(query_texts=[query], n_results=actual_n, include=["documents", "metadatas", "distances"])
        out = []
        docs      = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metadatas, distances):
            out.append({
                "category": meta.get("category", ""),
                "key":      meta.get("key", ""),
                "text":     doc,
                "score":    round(1.0 - dist, 3),   # cosine similarity
            })
        return out
    except Exception:
        return []


def rebuild_index(memory: dict[str, Any], agent_id: str | None) -> int:
    """
    Rebuild the full semantic index from a raw memory dict.
    Called on first migration or after a manual memory edit.
    Returns the number of entries indexed, or 0 on failure.
    """
    try:
        col = _get_collection(agent_id)
        if col is None:
            return 0

        # Wipe existing index for this agent
        existing_ids = col.get()["ids"]
        if existing_ids:
            col.delete(ids=existing_ids)

        entries: list[tuple[str, str, str]] = []   # (doc_id, text, category, key)

        # Key-value categories
        for cat in ("active_context", "notes", "user_preferences"):
            for key, val in memory.get(cat, {}).items():
                if isinstance(val, dict) and val.get("value"):
                    text = f"[{cat}] {key}: {val['value']}"
                    entries.append((_entry_id(cat, key), text, cat, key))

        # Rolling lists
        for i, entry in enumerate(memory.get("recent_work", [])):
            key  = f"rw_{i}_{entry.get('date', '')}"
            text = f"[recent_work] {entry.get('label', '')}: {entry.get('content', '')}"
            entries.append((_entry_id("recent_work", key), text, "recent_work", key))

        for i, entry in enumerate(memory.get("session_summaries", [])):
            key  = f"ss_{i}_{entry.get('date', '')}"
            text = f"[session_summary] {entry.get('content', '')}"
            entries.append((_entry_id("session_summary", key), text, "session_summary", key))

        if not entries:
            return 0

        ids       = [e[0] for e in entries]
        documents = [e[1] for e in entries]
        metadatas = [{"category": e[2], "key": e[3]} for e in entries]

        col.upsert(ids=ids, documents=documents, metadatas=metadatas)
        return len(entries)
    except Exception:
        return 0
