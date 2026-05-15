"""
Knowledge base initialization script — incremental mode.

Chunks .txt / .md / .pdf files in the knowledge/ directory and writes to ChromaDB.
On subsequent runs, only files that are new or have changed content are re-embedded;
unchanged files are skipped entirely, saving OpenAI API calls.

Change detection strategy:
  - Compute MD5 hash of each file's raw bytes
  - Store hash in every chunk's metadata as `file_hash`
  - On re-run: compare current hash against stored hash
      unchanged  → skip (no API call)
      modified   → delete old chunks, re-embed
      new        → embed and add
      deleted    → delete orphaned chunks from collection

Usage:
    cd digital-qa-employee
    python knowledge/setup_kb.py          # incremental update (default)
    python knowledge/setup_kb.py --full   # force full rebuild
"""
import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CHROMA_DB_PATH, EMBEDDING_MODEL, EMBEDDING_API_KEY, KNOWLEDGE_DIR

CHUNK_SIZE    = 500
CHUNK_OVERLAP = 50
SUPPORTED_EXTS = {".txt", ".md", ".pdf"}


# ── Text utilities ─────────────────────────────────────────────────────────────

def split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Sliding window chunking by newline boundaries."""
    lines = text.split("\n")
    chunks, current, length = [], [], 0

    for line in lines:
        current.append(line)
        length += len(line) + 1
        if length >= chunk_size:
            chunks.append("\n".join(current))
            overlap_lines = current[-3:] if len(current) > 3 else current[:]
            current = overlap_lines
            length = sum(len(l) + 1 for l in current)

    if current:
        chunks.append("\n".join(current))

    return [c.strip() for c in chunks if c.strip()]


def _read_pdf(filepath: str) -> str:
    """Extract text from PDF using pypdf, page by page."""
    from pypdf import PdfReader
    reader = PdfReader(filepath)
    pages = []
    for i, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(f"[Page {i + 1}]\n{page_text}")
    return "\n\n".join(pages)


def _file_hash(filepath: str) -> str:
    """Compute MD5 hash of file bytes for change detection."""
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def _read_text(filepath: str) -> str:
    """Read file content as plain text (supports .txt, .md, .pdf)."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        return _read_pdf(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


# ── Core build logic ───────────────────────────────────────────────────────────

def build_knowledge_base(full_rebuild: bool = False) -> None:
    """
    Build or incrementally update the ChromaDB knowledge base.

    Args:
        full_rebuild: If True, delete the entire collection and re-embed all files.
                      If False (default), only process new or modified files.
    """
    import chromadb
    from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

    if not EMBEDDING_API_KEY:
        print("[Error] EMBEDDING_API_KEY not set. Embedding requires the OpenAI API.")
        print("Add to .env: EMBEDDING_API_KEY=sk-xxxxxxxx")
        return

    print(f"ChromaDB path  : {CHROMA_DB_PATH}")
    print(f"Embedding model: {EMBEDDING_MODEL} (OpenAI API)")
    print(f"Mode           : {'full rebuild' if full_rebuild else 'incremental'}")
    print()

    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    embedding_fn = OpenAIEmbeddingFunction(
        api_key=EMBEDDING_API_KEY,
        model_name=EMBEDDING_MODEL,
    )

    if full_rebuild:
        try:
            client.delete_collection("knowledge_main")
            print("Old knowledge base cleared.")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name="knowledge_main",
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    # ── Build stored-hash index from existing chunks ──────────────────────────
    # stored_hashes: filename -> hash (taken from the first chunk of each file)
    stored_hashes: dict[str, str] = {}
    stored_ids_by_file: dict[str, list[str]] = {}

    if not full_rebuild:
        existing = collection.get(include=["metadatas"])
        for doc_id, meta in zip(existing.get("ids", []), existing.get("metadatas", [])):
            src = meta.get("source", "")
            fhash = meta.get("file_hash", "")
            if src:
                if src not in stored_hashes and fhash:
                    stored_hashes[src] = fhash
                stored_ids_by_file.setdefault(src, []).append(doc_id)

    # ── Report Confluence-cached entries (read-only, never modified here) ────
    confluence_entries = {
        src: ids
        for src, ids in stored_ids_by_file.items()
        if src.startswith("confluence:")
    }
    if confluence_entries:
        for src, ids in sorted(confluence_entries.items()):
            print(f"  ~ {src}: {len(ids)} chunks (Confluence cache, preserved)")

    # ── Scan knowledge directory ──────────────────────────────────────────────
    all_files = sorted(
        f for f in os.listdir(KNOWLEDGE_DIR)
        if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS
        and not f.startswith("_")
    )

    if not all_files:
        print(f"[Warning] No supported files found in knowledge/ ({', '.join(SUPPORTED_EXTS)}).")
        return

    added = modified = skipped = removed = 0

    for filename in all_files:
        filepath = os.path.join(KNOWLEDGE_DIR, filename)
        current_hash = _file_hash(filepath)

        # Unchanged: skip entirely — zero API calls
        if not full_rebuild and stored_hashes.get(filename) == current_hash:
            print(f"  = {filename}: unchanged, skipped")
            skipped += 1
            continue

        # Modified: delete old chunks before re-embedding
        if filename in stored_ids_by_file:
            collection.delete(ids=stored_ids_by_file[filename])
            status_label = "updated"
            modified += 1
        else:
            status_label = "new"
            added += 1

        # Read and chunk
        try:
            text = _read_text(filepath)
        except Exception as e:
            print(f"  x {filename}: read failed ({e})")
            continue

        if not text.strip():
            print(f"  x {filename}: empty content, skipped")
            continue

        chunks = split_text(text)
        ids = [f"{filename}::chunk-{i}" for i in range(len(chunks))]
        metadatas = [
            {"source": filename, "chunk_index": i, "file_hash": current_hash}
            for i in range(len(chunks))
        ]

        # Batch write (ChromaDB limit ~5000 per call)
        batch_size = 100
        for start in range(0, len(chunks), batch_size):
            collection.add(
                documents=chunks[start:start + batch_size],
                ids=ids[start:start + batch_size],
                metadatas=metadatas[start:start + batch_size],
            )

        print(f"  + {filename}: {len(chunks)} chunks ({status_label})")

    # ── Remove orphaned chunks for deleted files ──────────────────────────────
    # Skip Confluence-cached entries (source starts with "confluence:") —
    # they are managed by save_confluence_page, not by local files.
    current_fileset = set(all_files)
    for stored_file, chunk_ids in stored_ids_by_file.items():
        if stored_file.startswith("confluence:"):
            continue  # Confluence cache: never treat as orphan
        if stored_file not in current_fileset:
            collection.delete(ids=chunk_ids)
            print(f"  - {stored_file}: deleted from KB (file no longer exists)")
            removed += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    confluenced = len(confluence_entries) if not full_rebuild else 0
    print(f"Done.  added={added}  updated={modified}  skipped={skipped}  removed={removed}  confluence_cached={confluenced}")
    if skipped > 0:
        print(f"Tip: {skipped} file(s) unchanged — no OpenAI API calls made for them.")
    print("Run main.py to start the Digital QA Engineer.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build / update the QA knowledge base")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force full rebuild (delete existing collection and re-embed all files)",
    )
    args = parser.parse_args()
    build_knowledge_base(full_rebuild=args.full)
