"""
Tool: Save Confluence page to local knowledge base (lazy load cache).

Risk Level: L2 (requires Mentor confirmation before execution)
Reason: Writes to local vector database, affects all subsequent knowledge base search results.

Workflow:
  1. Use page_id to call Confluence API to fetch complete page content
  2. Clean HTML → plain text
  3. Chunk (same strategy as setup_kb.py, CHUNK_SIZE=500)
  4. Call OpenAI Embedding API for vectorization
  5. Write to local ChromaDB (knowledge_main / knowledge_{agent_id} collection)
     - Record in metadata: source="confluence:<title>", page_id, page_url
     - If same page_id already exists, delete old chunks first then rewrite (supports updates)

Prerequisites: Configure both Confluence and OpenAI variables in .env
"""
import re

import requests

from config import (
    CHROMA_DB_PATH,
    CONFLUENCE_API_TOKEN,
    CONFLUENCE_AUTH_TYPE,
    CONFLUENCE_BASE_URL,
    CONFLUENCE_USERNAME,
    EMBEDDING_API_KEY,
    EMBEDDING_MODEL,
    MAIN_KB_COLLECTION,
)

# Confluence REST API endpoint to get page content
_CONTENT_ENDPOINT = "/rest/api/content/{page_id}"
_EXPAND = "body.storage,space,version,ancestors"

CHUNK_SIZE    = 500
CHUNK_OVERLAP = 50


def save_confluence_page(page_id: str, agent_id: str = None) -> str:
    """
    Cache the content of a specified Confluence page to local knowledge base.

    Args:
        page_id: Confluence page ID (numeric string), can be obtained from search_confluence results

    Returns:
        Description of operation result, including number of chunks written and source identifier.
    """
    # ── Pre-execution Checks ──────────────────────────────────────────────────────────────
    if not CONFLUENCE_BASE_URL or not CONFLUENCE_API_TOKEN:
        return (
            "[Confluence Not Configured] Please set in .env:\n"
            "  CONFLUENCE_BASE_URL / CONFLUENCE_API_TOKEN\n"
            "  (Data Center PAT mode does not require CONFLUENCE_USERNAME)"
        )
    if not EMBEDDING_API_KEY:
        return "[Error] EMBEDDING_API_KEY not set, cannot generate embeddings to write to knowledge base."

    # ── Fetch Page Content ──────────────────────────────────────────────────────────
    url = f"{CONFLUENCE_BASE_URL.rstrip('/')}{_CONTENT_ENDPOINT.format(page_id=page_id)}"
    auth_kwargs = (
        {"headers": {"Authorization": f"Bearer {CONFLUENCE_API_TOKEN}"}}
        if CONFLUENCE_AUTH_TYPE == "pat"
        else {"auth": (CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN)}
    )

    try:
        response = requests.get(
            url,
            params={"expand": _EXPAND},
            timeout=20,
            **auth_kwargs,
        )
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        if status == 404:
            return f"[Error] page_id={page_id} not found, please confirm ID is correct and you have access permission."
        if status == 401:
            return "[Error] Confluence authentication failed, please check CONFLUENCE_API_TOKEN and CONFLUENCE_AUTH_TYPE."
        return f"[Error] Confluence API returned HTTP {status}: {e}"
    except Exception as e:
        return f"[Error] Failed to fetch page: {e}"

    data      = response.json()
    title     = data.get("title", f"page-{page_id}")
    space     = data.get("space", {}).get("name", "")
    web_link  = CONFLUENCE_BASE_URL.rstrip("/") + data.get("_links", {}).get("webui", "")

    # storage format is Confluence-specific XML/HTML, needs cleaning
    storage_body = data.get("body", {}).get("storage", {}).get("value", "")
    plain_text   = _storage_to_text(storage_body)

    if not plain_text.strip():
        return f"[Warning] Page '{title}' content is empty, not written to knowledge base."

    # ── Chunk ─────────────────────────────────────────────────────────────────
    chunks = _split_text(plain_text)
    source_label = f"confluence:{title}"

    # ── Write to ChromaDB ─────────────────────────────────────────────────────
    try:
        import chromadb
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        embedding_fn = OpenAIEmbeddingFunction(
            api_key=EMBEDDING_API_KEY,
            model_name=EMBEDDING_MODEL,
        )
        collection_name = f"knowledge_{agent_id}" if agent_id else MAIN_KB_COLLECTION
        collection = client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

        # Delete old chunks for this page_id (supports re-caching after page update)
        existing = collection.get(where={"page_id": page_id})
        if existing and existing.get("ids"):
            collection.delete(ids=existing["ids"])
            old_count = len(existing["ids"])
        else:
            old_count = 0

        # Write new chunks
        ids       = [f"confluence::{page_id}::chunk-{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "source":    source_label,
                "page_id":   page_id,
                "page_url":  web_link,
                "space":     space,
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]

        batch_size = 100
        for start in range(0, len(chunks), batch_size):
            collection.add(
                documents=chunks[start:start + batch_size],
                ids=ids[start:start + batch_size],
                metadatas=metadatas[start:start + batch_size],
            )

    except Exception as e:
        return f"[Error] Failed to write to local knowledge base: {e}"

    update_note = f" (replaced {old_count} old chunks)" if old_count else ""
    return (
        f"✅ Confluence page cached to local knowledge base{update_note}\n"
        f"  Title: {title}\n"
        f"  Space: {space}\n"
        f"  Link: {web_link}\n"
        f"  Chunks: {len(chunks)}\n"
        f"  KB Identifier: {source_label}\n"
        f"  For future retrieval, use search_knowledge_base directly, no need to access Confluence again."
    )


# ── Internal Helper Functions ──────────────────────────────────────────────────────────────

def _storage_to_text(storage_xml: str) -> str:
    """
    Convert Confluence storage format (XML/HTML mix) to plain text.
    Preserve paragraph line breaks, remove all tags.
    """
    if not storage_xml:
        return ""
    # Insert line breaks before and after block-level tags, preserving paragraph structure
    block_tags = r"</?(p|h[1-6]|li|tr|th|td|div|br|ac:task-body)[^>]*>"
    text = re.sub(block_tags, "\n", storage_xml, flags=re.IGNORECASE)
    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    text = (text
            .replace("&amp;",  "&")
            .replace("&lt;",   "<")
            .replace("&gt;",   ">")
            .replace("&nbsp;", " ")
            .replace("&#39;",  "'")
            .replace("&quot;", '"'))
    # Compress excess blank lines (preserve paragraphing)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Sliding window chunking strategy same as setup_kb.py."""
    lines = text.split("\n")
    chunks, current, length = [], [], 0

    for line in lines:
        current.append(line)
        length += len(line) + 1
        if length >= chunk_size:
            chunks.append("\n".join(current))
            overlap_lines = current[-3:] if len(current) > 3 else current[:]
            current  = overlap_lines
            length   = sum(len(l) + 1 for l in current)

    if current:
        chunks.append("\n".join(current))

    return [c.strip() for c in chunks if c.strip()]
