"""WebSocket chat endpoint + conversation management.

Key design: LangGraph's app.stream() is a *synchronous* generator that makes
blocking LLM API calls. Running it directly inside an async FastAPI handler
blocks the entire asyncio event loop, which means all ws.send_json() calls
are queued and only flushed in a single burst at the very end — the user sees
no streaming at all.

Fix: _astream() runs the synchronous generator inside a thread-pool worker and
bridges events back to the async side via an asyncio.Queue. The event loop
stays free between LLM calls, so WebSocket frames are flushed in real time.
"""
import asyncio
import json
import uuid
from starlette.websockets import WebSocketDisconnect as _WSD
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from web.db.database import get_db
from web.db.models import Agent, Conversation, Message, PromptVersion, ToolRiskConfig, RankingCeilingConfig
from config import (
    ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENAI_BASE_URL,
    MODEL_NAME, LLM_PROVIDER,
)
from agent.llm_client import call_llm

router = APIRouter(tags=["chat"])

# In-memory store for LangGraph app instances (per agent_id)
_agent_apps: dict = {}


async def _send(ws, payload: dict) -> bool:
    """Send a JSON payload over WebSocket, silently ignoring a closed connection.

    Returns True on success, False if the connection is already gone.
    Prevents the common double-fault where an error handler tries to send
    an error message to an already-closed socket and raises RuntimeError.
    """
    try:
        await ws.send_json(payload)
        return True
    except (_WSD, RuntimeError):
        # RuntimeError: "Cannot call 'send' once a close message has been sent."
        return False


def _get_or_build_app(agent_id: str):
    if agent_id not in _agent_apps:
        from agent.agent import build_agent
        _agent_apps[agent_id] = build_agent()
    return _agent_apps[agent_id]


async def _astream(app, state, config):
    """
    Async generator that wraps LangGraph's synchronous app.stream().

    Yields tuples of (tag, payload):
      ("ok",    event_dict)  — a LangGraph node update event
      ("token", text_delta)  — a streaming text token from the LLM

    Both types are multiplexed through a single asyncio.Queue so the event
    loop is never blocked and tokens arrive in real time.
    """
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _token_cb(delta: str):
        loop.call_soon_threadsafe(queue.put_nowait, ("token", delta))

    # Inject the token callback into the LangGraph config so agent_node
    # can pass it through to call_llm → _call_anthropic streaming.
    patched_config = dict(config)
    patched_config["configurable"] = {**config.get("configurable", {}), "token_callback": _token_cb}

    def _worker():
        try:
            for event in app.stream(state, config=patched_config, stream_mode="updates"):
                loop.call_soon_threadsafe(queue.put_nowait, ("ok", event))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("err", exc))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, ("eof", None))

    worker_task = asyncio.create_task(asyncio.to_thread(_worker))

    try:
        while True:
            tag, payload = await queue.get()
            if tag == "eof":
                break
            elif tag == "err":
                raise payload
            else:
                yield tag, payload   # caller receives (tag, payload) now
    finally:
        await worker_task


# ── REST endpoints ─────────────────────────────────────────────────────────────

@router.post("/agents/{agent_id}/conversations", status_code=201)
def create_conversation(agent_id: str, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")
    conv = Conversation(
        id=str(uuid.uuid4()),
        agent_id=agent_id,
        title="New Conversation",
        created_at=datetime.utcnow(),
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {"id": conv.id, "title": conv.title, "agent_id": agent_id}


@router.patch("/conversations/{conv_id}")
def rename_conversation(conv_id: str, body: dict, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(404, "Conversation not found")
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "title is required")
    conv.title = title[:100]
    db.commit()
    return {"id": conv.id, "title": conv.title}


@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: str, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(404, "Conversation not found")
    db.query(Message).filter(Message.conversation_id == conv_id).delete()
    db.delete(conv)
    db.commit()


@router.post("/conversations/{conv_id}/save-to-kb", status_code=200)
def save_conversation_to_kb(conv_id: str, db: Session = Depends(get_db)):
    """
    Summarise a conversation with a single LLM call and save the result
    to the agent's branch knowledge base (knowledge_{agent_id}).
    """
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(404, "Conversation not found")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv_id)
        .order_by(Message.created_at)
        .all()
    )
    if not messages:
        raise HTTPException(400, "Conversation has no messages to summarise")

    agent = db.query(Agent).filter(Agent.id == conv.agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    # ── Build readable transcript ─────────────────────────────────────────
    lines = []
    for m in messages:
        role = "User" if m.role == "user" else "Assistant"
        if m.content:
            lines.append(f"[{role}]: {m.content}")
    transcript = "\n\n".join(lines)

    # ── LLM call: generate structured KB entry ────────────────────────────
    from config import (
        ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENAI_BASE_URL,
        MODEL_NAME, LLM_PROVIDER,
    )
    from agent.llm_client import call_llm
    from langchain_core.messages import HumanMessage

    system = (
        "You are a QA knowledge base editor. "
        "Given a conversation transcript, produce a concise knowledge base article "
        "that captures the key findings, decisions, and QA insights discussed. "
        "Format:\n"
        "TITLE: <one-line title>\n\n"
        "<body — structured prose or bullet points, max 600 words>"
    )
    response = call_llm(
        system_prompt=system,
        messages=[HumanMessage(content=f"Conversation transcript:\n\n{transcript}")],
        tool_definitions=[],
        model=MODEL_NAME,
        provider=LLM_PROVIDER,
        anthropic_api_key=ANTHROPIC_API_KEY,
        openai_api_key=OPENAI_API_KEY,
        openai_base_url=OPENAI_BASE_URL,
        max_tokens=1024,
    )

    summary = response.text.strip()
    if not summary:
        raise HTTPException(500, "LLM returned empty summary")

    # Parse title from first line
    first_line = summary.splitlines()[0]
    title = first_line.removeprefix("TITLE:").strip() if first_line.startswith("TITLE:") else conv.title
    body  = "\n".join(summary.splitlines()[1:]).strip() if first_line.startswith("TITLE:") else summary

    # ── Write to ChromaDB ─────────────────────────────────────────────────
    from config import CHROMA_DB_PATH, EMBEDDING_API_KEY, EMBEDDING_MODEL
    try:
        import chromadb
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        from tools.confluence_save import _split_text

        client       = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        embedding_fn = OpenAIEmbeddingFunction(api_key=EMBEDDING_API_KEY, model_name=EMBEDDING_MODEL)
        col_name     = f"knowledge_{conv.agent_id}"
        collection   = client.get_or_create_collection(
            name=col_name,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

        doc_id   = f"conversation::{conv_id}"
        chunks   = _split_text(body)
        # Remove any previous version of this conversation summary
        existing = collection.get(where={"conversation_id": conv_id})
        if existing and existing.get("ids"):
            collection.delete(ids=existing["ids"])

        ids       = [f"{doc_id}::chunk-{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "source":          f"conversation:{title}",
                "conversation_id": conv_id,
                "chunk_index":     i,
            }
            for i in range(len(chunks))
        ]
        collection.add(documents=chunks, ids=ids, metadatas=metadatas)
    except Exception as e:
        raise HTTPException(500, f"Failed to write to knowledge base: {e}")

    return {"title": title, "chunks": len(chunks), "collection": col_name}


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: str, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(404, "Conversation not found")
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv_id)
        .order_by(Message.created_at)
        .all()
    )
    return {
        "id": conv.id,
        "title": conv.title,
        "agent_id": conv.agent_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "tool_calls": json.loads(m.tool_calls_json or "[]"),
                "created_at": m.created_at.isoformat() + "Z",
            }
            for m in messages
        ],
    }


# ── WebSocket endpoint ─────────────────────────────────────────────────────────

@router.websocket("/conversations/{conv_id}/ws")
async def chat_ws(conv_id: str, ws: WebSocket):
    """
    Real-time chat over WebSocket.

    Client → Server:
      {"type": "message",  "content": "..."}
      {"type": "approval", "approved": true/false}

    Server → Client:
      {"type": "thinking"}                              – agent started reasoning
      {"type": "thinking_text", "content": "..."}      – LLM reasoning text before tool calls
      {"type": "tool_call",  "tool": "...", "preview": "..."}
      {"type": "tool_result","content": "..."}          – abbreviated tool return
      {"type": "message",   "content": "..."}           – final assistant reply
      {"type": "done"}                                  – round complete, re-enable input
      {"type": "approval_required", "tool": "...", "args": {...}, "call_id": "..."}
      {"type": "error",     "content": "..."}
    """
    await ws.accept()

    from web.db.database import SessionLocal
    db = SessionLocal()

    try:
        conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
        if not conv:
            await _send(ws, {"type": "error", "content": "Conversation not found"})
            await ws.close()
            return

        agent_row = db.query(Agent).filter(Agent.id == conv.agent_id).first()
        if not agent_row:
            await _send(ws, {"type": "error", "content": "Agent not found"})
            await ws.close()
            return

        app = _get_or_build_app(conv.agent_id)

        # Load active prompt versions for this agent (base + specialization)
        active_versions = db.query(PromptVersion).filter(
            PromptVersion.agent_id == conv.agent_id,
            PromptVersion.is_active == True,
        ).all()
        version_map = {v.type: v.content for v in active_versions}
        base_prompt = version_map.get("base", "")
        specialization = version_map.get("specialization", agent_row.specialization or "")

        # Load configurable permissions from DB (fallback to hardcoded if tables are empty)
        tool_risk_rows = db.query(ToolRiskConfig).all()
        ranking_ceil_rows = db.query(RankingCeilingConfig).all()
        tool_risk_level = {r.tool_name: r.risk_level for r in tool_risk_rows}
        ranking_ceilings = {r.ranking: r.ceiling for r in ranking_ceil_rows}

        lg_config = {
            "configurable": {
                "thread_id": conv_id,
                "agent_id": conv.agent_id,
                "agent_name": agent_row.name,
                "specialization": specialization,
                "ranking": agent_row.ranking or "Intern",
                "base_prompt": base_prompt,
                "tool_risk_level": tool_risk_level,
                "ranking_ceilings": ranking_ceilings,
                # trace_id is refreshed per turn in the message loop below
            }
        }

        while True:
            data = await ws.receive_json()
            if data.get("type") != "message":
                continue

            user_content = data.get("content", "").strip()
            if not user_content:
                continue

            _save_message(db, conv_id, "user", user_content)

            if conv.title == "New Conversation":
                conv.title = user_content[:60]
                db.commit()

            # ── P0: fresh trace_id per turn ────────────────────────────────
            turn_trace_id = str(uuid.uuid4())
            lg_config["configurable"]["trace_id"] = turn_trace_id

            from langchain_core.messages import HumanMessage, AIMessage as _AI
            from config import TOOL_RISK_LEVEL, CONTEXT_COMPRESS_THRESHOLD, CONTEXT_KEEP_RECENT

            # ── Context window management ──────────────────────────────────
            # Load previous messages in this conversation and compress if needed.
            # The DB keeps full history; only the in-flight LangGraph state is trimmed.
            history_rows = (
                db.query(Message)
                .filter(Message.conversation_id == conv_id)
                .order_by(Message.created_at)
                .all()
            )
            # Build LangChain message list from DB (exclude the just-saved user message)
            def _db_to_lc(m):
                if m.role == "user":
                    return HumanMessage(content=m.content or "")
                return _AI(content=m.content or "")

            history_lc = [_db_to_lc(m) for m in history_rows if m.content]
            # Drop the last entry — it's the current user message we're about to process
            if history_lc and history_lc[-1].content == user_content:
                history_lc = history_lc[:-1]

            if len(history_lc) >= CONTEXT_COMPRESS_THRESHOLD:
                # Split: compress everything except the most recent CONTEXT_KEEP_RECENT messages
                to_compress = history_lc[:-CONTEXT_KEEP_RECENT]
                keep_recent  = history_lc[-CONTEXT_KEEP_RECENT:]
                transcript = "\n".join(
                    f"[{'User' if isinstance(m, HumanMessage) else 'Assistant'}]: {m.content}"
                    for m in to_compress
                )
                compress_resp = call_llm(
                    system_prompt="You are a conversation summariser. Produce a concise summary of the conversation below, preserving key decisions, findings, and context needed for the assistant to continue helping.",
                    messages=[HumanMessage(content=f"Conversation to summarise:\n\n{transcript}")],
                    tool_definitions=[],
                    model=MODEL_NAME,
                    provider=LLM_PROVIDER,
                    anthropic_api_key=ANTHROPIC_API_KEY,
                    openai_api_key=OPENAI_API_KEY,
                    openai_base_url=OPENAI_BASE_URL,
                    max_tokens=512,
                )
                summary_msg = HumanMessage(
                    content=f"[Earlier conversation summary]\n{compress_resp.text.strip()}"
                )
                history_lc = [summary_msg] + keep_recent

            state = {
                "messages": history_lc + [HumanMessage(content=user_content)],
                "task_id": conv_id,
                "task_description": user_content,
                "pending_approval": False,
                "escalated": False,
                "escalation_reason": "",
            }

            tool_calls_log = []
            final_response = ""
            interrupted = False

            await _send(ws, {"type": "thinking"})

            try:
                streaming_final = False   # True once we start token-streaming the final reply

                async for tag, payload in _astream(app, state, lg_config):

                    # ── Token delta (streaming final response) ─────────────
                    if tag == "token":
                        if not streaming_final:
                            # First token: open a streaming message on the frontend
                            await _send(ws, {"type": "message_start"})
                            streaming_final = True
                        await _send(ws, {"type": "token", "content": payload})
                        final_response += payload
                        continue

                    # ── LangGraph node update ──────────────────────────────
                    event = payload
                    node_name = list(event.keys())[0]
                    node_output = event[node_name]

                    if node_name == "__interrupt__" or not isinstance(node_output, dict):
                        interrupted = True
                        break

                    msgs = node_output.get("messages", [])

                    if node_name == "agent":
                        for msg in msgs:
                            if hasattr(msg, "tool_calls") and msg.tool_calls:
                                # Send intermediate reasoning text (before tool calls)
                                if hasattr(msg, "content") and msg.content:
                                    text = msg.content if isinstance(msg.content, str) else ""
                                    if text.strip():
                                        await _send(ws, {
                                            "type": "thinking_text",
                                            "content": text[:400],
                                        })
                                # Show all tool calls in the thinking log.
                                # Do NOT send approval_required here — handled
                                # by the interrupt block below to avoid double-sending.
                                for tc in msg.tool_calls:
                                    await _send(ws, {
                                        "type": "tool_call",
                                        "tool": tc["name"],
                                        "preview": _tool_preview(tc),
                                    })
                                    if TOOL_RISK_LEVEL.get(tc["name"], "L1") != "L2":
                                        tool_calls_log.append({"name": tc["name"], "args": tc["args"]})
                            elif hasattr(msg, "content") and msg.content and not streaming_final:
                                # Final answer — not streamed (fallback for non-streaming path)
                                final_response = msg.content if isinstance(msg.content, str) else str(msg.content)

                    elif node_name == "tools":
                        # Tool results — show abbreviated preview
                        for msg in msgs:
                            result_text = str(getattr(msg, "content", "")).strip()
                            if result_text:
                                await _send(ws, {
                                    "type": "tool_result",
                                    "content": result_text[:200],
                                })

                # Handle L2 interrupt: agent paused waiting for Mentor approval
                if interrupted:
                    last_lg_state = app.get_state(lg_config)
                    last_msg = last_lg_state.values["messages"][-1]
                    l2_calls = [
                        tc for tc in last_msg.tool_calls
                        if TOOL_RISK_LEVEL.get(tc["name"], "L1") == "L2"
                    ]

                    for tc in l2_calls:
                        await _send(ws, {
                            "type": "approval_required",
                            "tool": tc["name"],
                            "args": tc["args"],
                            "call_id": tc["id"],
                        })

                        approval_data = await ws.receive_json()
                        approved = approval_data.get("approved", False)

                        # Audit the L2 decision (with trace_id for chain tracing)
                        from tools.audit_logger import log_l2_decision
                        log_l2_decision(
                            agent_id=conv.agent_id,
                            agent_name=agent_row.name,
                            conversation_id=conv_id,
                            tool_name=tc["name"],
                            tool_args=tc["args"],
                            approved=approved,
                            trace_id=turn_trace_id,
                        )

                        if not approved:
                            await _send(ws, {"type": "message", "content": "Operation cancelled by Mentor."})
                            await _send(ws, {"type": "done"})
                            _save_message(db, conv_id, "assistant", "Operation cancelled by Mentor.")
                            continue

                        # Resume graph after approval — also run in thread
                        await _send(ws, {"type": "thinking"})
                        await _send(ws, {"type": "tool_call", "tool": tc["name"], "preview": _tool_preview(tc)})

                        async for tag, payload in _astream(app, None, lg_config):
                            if tag == "token":
                                if not streaming_final:
                                    await _send(ws, {"type": "message_start"})
                                    streaming_final = True
                                await _send(ws, {"type": "token", "content": payload})
                                final_response += payload
                                continue
                            event = payload
                            node_name = list(event.keys())[0]
                            node_output = event[node_name]
                            if node_name == "__interrupt__" or not isinstance(node_output, dict):
                                break
                            for msg in node_output.get("messages", []):
                                if hasattr(msg, "content") and msg.content and node_name == "agent" and not streaming_final:
                                    final_response = msg.content if isinstance(msg.content, str) else str(msg.content)

            except Exception as e:
                await _send(ws, {"type": "error", "content": f"Agent error: {e}"})
                final_response = ""

            if final_response and not streaming_final:
                await _send(ws, {"type": "message", "content": final_response})
                try:
                    _save_message(db, conv_id, "assistant", final_response, tool_calls=tool_calls_log)
                except Exception:
                    pass
            elif final_response and streaming_final:
                # Streaming path: save the accumulated response to DB
                try:
                    _save_message(db, conv_id, "assistant", final_response, tool_calls=tool_calls_log)
                except Exception:
                    pass

            # ── P2: background quality scoring ─────────────────────────────
            # Fire-and-forget: LLM-as-Judge scores the turn asynchronously.
            # Does NOT block the user's response.
            if final_response:
                asyncio.create_task(_score_quality(
                    agent_id=conv.agent_id,
                    agent_name=agent_row.name,
                    conversation_id=conv_id,
                    user_message=user_content,
                    assistant_reply=final_response,
                    trace_id=turn_trace_id,
                ))

            # Always send "done" so the frontend re-enables the input box
            await _send(ws, {"type": "done"})

    except (WebSocketDisconnect, RuntimeError):
        # WebSocketDisconnect: client closed normally
        # RuntimeError("WebSocket is not connected"): client disconnected during
        # the accept handshake (e.g. rapid page refresh) — treat as clean exit
        pass
    finally:
        db.close()


async def _score_quality(
    agent_id: str,
    agent_name: str,
    conversation_id: str,
    user_message: str,
    assistant_reply: str,
    trace_id: str,
) -> None:
    """
    P2: LLM-as-Judge quality scoring for a completed chat turn.
    Runs in a background task; result written to audit_logs as event_type='quality_score'.
    Scores on three dimensions:
      - Helpfulness: did the response address the user's question?
      - Boundaries:  did it stay within its role (no overreach)?
      - Clarity:     is the response clear and well-structured?
    Final score = average of three dimensions (0.0–1.0).
    """
    try:
        from langchain_core.messages import HumanMessage
        from tools.audit_logger import log_quality_score

        system = (
            "You are a strict QA evaluator reviewing a digital employee's response. "
            "Score the response on three criteria, each 0-3:\n"
            "  helpfulness: Did it directly answer the user's question? (0=no, 3=fully)\n"
            "  boundaries: Did it stay within its role without overreach? (0=violated, 3=perfect)\n"
            "  clarity: Is the response clear and well-structured? (0=confusing, 3=excellent)\n\n"
            "Output ONLY valid JSON: "
            '{\"helpfulness\": N, \"boundaries\": N, \"clarity\": N, \"verdict\": \"good|ok|poor\", \"reasoning\": \"...\"}'
        )
        prompt = (
            f"User message:\n{user_message[:400]}\n\n"
            f"Assistant reply:\n{assistant_reply[:800]}"
        )
        resp = await asyncio.to_thread(
            call_llm,
            system_prompt=system,
            messages=[HumanMessage(content=prompt)],
            tool_definitions=[],
            model=MODEL_NAME,
            provider=LLM_PROVIDER,
            anthropic_api_key=ANTHROPIC_API_KEY,
            openai_api_key=OPENAI_API_KEY,
            openai_base_url=OPENAI_BASE_URL,
            max_tokens=200,
        )
        import json as _json
        raw = resp.text.strip()
        # Extract JSON even if LLM wraps it in markdown fences
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        data = _json.loads(raw)
        total = (data.get("helpfulness", 0) + data.get("boundaries", 0) + data.get("clarity", 0)) / 9.0
        log_quality_score(
            agent_id=agent_id,
            agent_name=agent_name,
            conversation_id=conversation_id,
            score=round(total, 3),
            verdict=data.get("verdict", "ok"),
            reasoning=data.get("reasoning", ""),
            trace_id=trace_id,
        )
    except Exception:
        pass  # Quality scoring must never affect the user experience


def _save_message(db, conv_id: str, role: str, content: str, tool_calls: list = None):
    msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conv_id,
        role=role,
        content=content,
        tool_calls_json=json.dumps(tool_calls or []),
        created_at=datetime.utcnow(),
    )
    db.add(msg)
    db.commit()


def _tool_preview(tc: dict) -> str:
    args = tc.get("args", {})
    for key in ["query", "issue_key", "page_id", "mr_url", "key", "file_path"]:
        if key in args:
            val = str(args[key])
            return val[:80] + ("…" if len(val) > 80 else "")
    return str(args)[:80]
