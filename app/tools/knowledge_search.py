"""
Tool: Semantic search knowledge base (RAG) — main + branch collections.

Risk Level: L1 (self-execution, read-only)
Tech Stack: ChromaDB (local) + OpenAI Embedding API (text-embedding-3-small)

Search strategy:
  - Always queries de_knowledge_main (shared foundation)
  - If agent_id provided, also queries knowledge_{agent_id} (branch)
  - Results from both collections are merged and re-ranked by relevance
  - Source label distinguishes [Main] vs [Branch] in output

Before first run, execute:
    python knowledge/setup_kb.py
"""
import os

from config import CHROMA_DB_PATH, EMBEDDING_MODEL, EMBEDDING_API_KEY, KNOWLEDGE_TOP_K, MAIN_KB_COLLECTION

_collection_cache: dict = {}


def _get_collection(collection_name: str):
    """Get (or initialize) a ChromaDB collection by name, lazy loaded."""
    global _collection_cache
    if collection_name in _collection_cache:
        return _collection_cache[collection_name]
    try:
        import chromadb
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        if not EMBEDDING_API_KEY:
            return None
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        embedding_fn = OpenAIEmbeddingFunction(
            api_key=EMBEDDING_API_KEY,
            model_name=EMBEDDING_MODEL,
        )
        col = client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        _collection_cache[collection_name] = col
        return col
    except Exception:
        return None


def search_knowledge_base(query: str, agent_id: str = None) -> str:
    """
    Semantically search the knowledge base.
    Always searches main KB; also searches agent branch KB if agent_id provided.

    Args:
        query:    Natural language query
        agent_id: Optional agent ID to also search its branch collection

    Returns:
        Formatted relevant knowledge chunks with source labels ([Main] / [Branch])
    """
    if not EMBEDDING_API_KEY:
        return "[Knowledge Base Not Ready] EMBEDDING_API_KEY not set."

    collections_to_search = []

    main_col = _get_collection(MAIN_KB_COLLECTION)
    if main_col:
        collections_to_search.append((main_col, "Main"))

    if agent_id:
        branch_name = f"knowledge_{agent_id}"
        branch_col = _get_collection(branch_name)
        if branch_col:
            collections_to_search.append((branch_col, "Branch"))

    if not collections_to_search:
        return "[Knowledge Base Not Ready] Please first run `python knowledge/setup_kb.py` to build index."

    try:
        all_results = []
        for col, label in collections_to_search:
            try:
                results = col.query(
                    query_texts=[query],
                    n_results=KNOWLEDGE_TOP_K,
                    include=["documents", "metadatas", "distances"],
                )
                docs = results["documents"][0]
                metas = results["metadatas"][0]
                distances = results["distances"][0]
                for doc, meta, dist in zip(docs, metas, distances):
                    all_results.append({
                        "doc": doc,
                        "meta": meta,
                        "distance": dist,
                        "label": label,
                    })
            except Exception:
                pass

        if not all_results:
            return f"[Knowledge Base] No content found related to '{query}'."

        # Sort by relevance (ascending distance = higher relevance)
        all_results.sort(key=lambda x: x["distance"])
        top_results = all_results[:KNOWLEDGE_TOP_K]

        max_relevance = round((1 - top_results[0]["distance"]) * 100, 1)
        quality_hint = (
            "⚠️ Highest relevance below 75%, local content may be insufficient, consider supplementing with Confluence search"
            if max_relevance < 75 else
            "✅ Local content relevance is good"
        )

        output_parts = [f"【Knowledge Base Search Results: {query}】{quality_hint}\n"]
        for i, r in enumerate(top_results, 1):
            source = r["meta"].get("source", "Unknown Source")
            relevance = round((1 - r["distance"]) * 100, 1)
            output_parts.append(
                f"── Chunk {i} [{r['label']}] (Source: {source}, Relevance: {relevance}%) ──\n{r['doc']}\n"
            )

        return "\n".join(output_parts)

    except Exception as e:
        return f"[Error] Knowledge base query failed: {e}"
