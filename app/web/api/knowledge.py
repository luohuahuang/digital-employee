"""Knowledge base management endpoints (upload, list, merge)."""
import os
import shutil
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session
from web.db.database import get_db
from web.db.models import Agent
from config import KNOWLEDGE_DIR, CHROMA_DB_PATH, EMBEDDING_API_KEY, EMBEDDING_MODEL, MAIN_KB_COLLECTION

router = APIRouter(tags=["knowledge"])

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}


@router.get("/agents/{agent_id}/knowledge")
def get_kb_status(agent_id: str, db: Session = Depends(get_db)):
    """Return knowledge base status for an agent: main + branch chunk counts."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    result = {"main": {}, "branch": {}}
    try:
        import chromadb
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        ef = OpenAIEmbeddingFunction(api_key=EMBEDDING_API_KEY, model_name=EMBEDDING_MODEL)

        # Main KB
        try:
            main_col = client.get_collection(name=MAIN_KB_COLLECTION, embedding_function=ef)
            existing = main_col.get(include=["metadatas"])
            sources = {}
            for meta in existing.get("metadatas", []):
                src = meta.get("source", "unknown")
                sources[src] = sources.get(src, 0) + 1
            result["main"] = {"total_chunks": main_col.count(), "sources": sources}
        except Exception:
            result["main"] = {"total_chunks": 0, "sources": {}}

        # Branch KB
        branch_name = f"knowledge_{agent_id}"
        try:
            branch_col = client.get_collection(name=branch_name, embedding_function=ef)
            existing = branch_col.get(include=["metadatas"])
            sources = {}
            for meta in existing.get("metadatas", []):
                src = meta.get("source", "unknown")
                sources[src] = sources.get(src, 0) + 1
            result["branch"] = {"total_chunks": branch_col.count(), "sources": sources}
        except Exception:
            result["branch"] = {"total_chunks": 0, "sources": {}}

    except Exception as e:
        result["error"] = str(e)

    return result


@router.post("/agents/{agent_id}/knowledge/upload")
async def upload_knowledge_file(
    agent_id: str,
    target: str = "branch",   # "main" or "branch"
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a .txt/.md/.pdf file to main or branch KB."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Only {ALLOWED_EXTENSIONS} files are supported")

    # Save file to a temp upload dir
    upload_dir = os.path.join(KNOWLEDGE_DIR, "_uploads", agent_id if target == "branch" else "_main")
    os.makedirs(upload_dir, exist_ok=True)
    dest_path = os.path.join(upload_dir, file.filename)

    with open(dest_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Embed and index
    collection_name = f"knowledge_{agent_id}" if target == "branch" else MAIN_KB_COLLECTION
    try:
        _embed_file(dest_path, collection_name)
        return {"message": f"File '{file.filename}' uploaded and indexed into {target} KB.", "collection": collection_name}
    except Exception as e:
        raise HTTPException(500, f"Embedding failed: {e}")


class MergeRequest(BaseModel):
    sources: list[str]   # List of source identifiers to merge from branch to main


@router.post("/agents/{agent_id}/knowledge/merge")
def merge_branch_to_main(agent_id: str, payload: MergeRequest, db: Session = Depends(get_db)):
    """
    Merge selected sources from agent branch KB to main KB.
    This promotes branch-specific knowledge to be shared with all agents.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    if not EMBEDDING_API_KEY:
        raise HTTPException(400, "EMBEDDING_API_KEY not set — cannot re-embed for merge")

    try:
        import chromadb
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        ef = OpenAIEmbeddingFunction(api_key=EMBEDDING_API_KEY, model_name=EMBEDDING_MODEL)

        branch_col = client.get_collection(
            name=f"knowledge_{agent_id}", embedding_function=ef
        )
        main_col = client.get_or_create_collection(
            name=MAIN_KB_COLLECTION,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

        merged_sources = []
        for source in payload.sources:
            # Get all chunks for this source from branch
            existing = branch_col.get(
                where={"source": source},
                include=["documents", "metadatas", "embeddings"],
            )
            if not existing or not existing.get("ids"):
                continue

            ids = existing["ids"]
            docs = existing["documents"]
            metas = existing["metadatas"]

            # Delete old chunks for same source in main (update semantics)
            try:
                old = main_col.get(where={"source": source})
                if old and old.get("ids"):
                    main_col.delete(ids=old["ids"])
            except Exception:
                pass

            # Add to main (re-use same IDs prefixed with "main::")
            new_ids = [f"main::{iid}" for iid in ids]
            batch_size = 100
            for start in range(0, len(docs), batch_size):
                main_col.add(
                    ids=new_ids[start:start + batch_size],
                    documents=docs[start:start + batch_size],
                    metadatas=metas[start:start + batch_size],
                )

            merged_sources.append({"source": source, "chunks": len(ids)})

        return {
            "message": f"Merged {len(merged_sources)} source(s) to Main KB",
            "merged": merged_sources,
        }

    except Exception as e:
        raise HTTPException(500, f"Merge failed: {e}")


# ── Internal helpers ───────────────────────────────────────────────────────────

def _embed_file(filepath: str, collection_name: str):
    """Embed a single file into the specified ChromaDB collection."""
    import hashlib
    import chromadb
    from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 50

    def split_text(text):
        lines = text.split("\n")
        chunks, current, length = [], [], 0
        for line in lines:
            current.append(line)
            length += len(line) + 1
            if length >= CHUNK_SIZE:
                chunks.append("\n".join(current))
                current = current[-3:] if len(current) > 3 else current[:]
                length = sum(len(l) + 1 for l in current)
        if current:
            chunks.append("\n".join(current))
        return [c.strip() for c in chunks if c.strip()]

    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        text = "\n\n".join(f"[Page {i+1}]\n{p.extract_text() or ''}" for i, p in enumerate(reader.pages))
    else:
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()

    if not text.strip():
        raise ValueError("File is empty")

    with open(filepath, "rb") as f:
        file_hash = hashlib.md5(f.read()).hexdigest()

    filename = os.path.basename(filepath)
    chunks = split_text(text)

    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    ef = OpenAIEmbeddingFunction(api_key=EMBEDDING_API_KEY, model_name=EMBEDDING_MODEL)
    col = client.get_or_create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    # Delete old chunks for same filename
    try:
        old = col.get(where={"source": filename})
        if old and old.get("ids"):
            col.delete(ids=old["ids"])
    except Exception:
        pass

    ids = [f"{collection_name}::{filename}::chunk-{i}" for i in range(len(chunks))]
    metas = [{"source": filename, "chunk_index": i, "file_hash": file_hash} for i in range(len(chunks))]

    batch_size = 100
    for start in range(0, len(chunks), batch_size):
        col.add(
            documents=chunks[start:start + batch_size],
            ids=ids[start:start + batch_size],
            metadatas=metas[start:start + batch_size],
        )
