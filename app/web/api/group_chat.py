"""
Group Chat API — REST CRUD + WebSocket orchestration.

WebSocket protocol:
  Client → Server:
    {"type": "message", "content": "..."}

  Server → Client:
    {"type": "agent_thinking", "agent_id": ..., "agent_name": ..., "agent_emoji": ...}
    {"type": "agent_message",  "agent_id": ..., "agent_name": ..., "agent_emoji": ..., "content": ...}
    {"type": "agent_pass",     "agent_id": ..., "agent_name": ..., "agent_emoji": ...}
    {"type": "done"}
    {"type": "error", "content": ...}
"""
import asyncio
import uuid
from datetime import datetime

from starlette.websockets import WebSocketDisconnect as _WSD
from fastapi import APIRouter, Depends, HTTPException, WebSocket
from pydantic import BaseModel
from sqlalchemy.orm import Session

from web.db.database import get_db
from web.db.models import GroupChat, GroupMembership, GroupMessage, Agent

router = APIRouter(tags=["group-chat"])


# ── Async helpers ──────────────────────────────────────────────────────────────

async def _send(ws, payload: dict) -> bool:
    try:
        await ws.send_json(payload)
        return True
    except (_WSD, RuntimeError):
        return False


async def _astream_group(app, state, config):
    """Async bridge: runs synchronous LangGraph app.stream() in a thread,
    forwarding events to the caller via an asyncio.Queue."""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _worker():
        try:
            for event in app.stream(state, config=config, stream_mode="updates"):
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
                yield payload
    finally:
        await worker_task


# ── Serialisation ──────────────────────────────────────────────────────────────

def _load_members(group_id: str, db: Session) -> list:
    """Return membership rows with .agent populated."""
    memberships = (
        db.query(GroupMembership)
        .filter(GroupMembership.group_id == group_id)
        .all()
    )
    for m in memberships:
        m.agent = db.query(Agent).filter(Agent.id == m.agent_id).first()
    return memberships


def _members_to_list(memberships) -> list[dict]:
    return [
        {
            "agent_id":    m.agent_id,
            "name":        m.agent.name        if m.agent else "",
            "avatar_emoji": m.agent.avatar_emoji if m.agent else "🤖",
            "product_line": m.agent.product_line if m.agent else "",
            "ranking":     m.agent.ranking     if m.agent else "Intern",
        }
        for m in memberships
        if m.agent
    ]


def _messages_to_list(messages) -> list[dict]:
    return [
        {
            "id":        msg.id,
            "role":      msg.speaker_type,
            "agent_id":  msg.speaker_id,
            "speaker":   msg.speaker_name,
            "emoji":     msg.speaker_emoji,
            "content":   msg.content,
            "is_pass":   msg.is_pass,
            "created_at": msg.created_at.isoformat() + "Z",
        }
        for msg in messages
    ]


def _group_to_dict(group: GroupChat, memberships, messages=None) -> dict:
    return {
        "id":         group.id,
        "title":      group.title,
        "created_at": group.created_at.isoformat() + "Z" if group.created_at else None,
        "members":    _members_to_list(memberships),
        "messages":   _messages_to_list(messages or []),
    }


# ── In-memory orchestrator cache ───────────────────────────────────────────────

_group_apps: dict = {}


def _get_orchestrator(group_id: str, participants: list[dict]):
    """Return (and cache) the compiled LangGraph for this group."""
    if group_id not in _group_apps:
        from agent.group_orchestrator import build_group_orchestrator
        _group_apps[group_id] = build_group_orchestrator(participants)
    return _group_apps[group_id]


# ── REST endpoints ─────────────────────────────────────────────────────────────

class GroupCreate(BaseModel):
    title: str = "New Group Chat"
    agent_ids: list[str]


@router.get("/group-chats")
def list_groups(db: Session = Depends(get_db)):
    groups = db.query(GroupChat).order_by(GroupChat.created_at.desc()).all()
    result = []
    for g in groups:
        members = _load_members(g.id, db)
        result.append(_group_to_dict(g, members))
    return result


@router.post("/group-chats", status_code=201)
def create_group(payload: GroupCreate, db: Session = Depends(get_db)):
    if len(payload.agent_ids) < 2:
        raise HTTPException(400, "A group chat requires at least 2 agents")

    for aid in payload.agent_ids:
        if not db.query(Agent).filter(Agent.id == aid, Agent.is_active == True).first():
            raise HTTPException(404, f"Active agent {aid} not found")

    group = GroupChat(
        id=str(uuid.uuid4()),
        title=payload.title.strip() or "New Group Chat",
        created_at=datetime.utcnow(),
    )
    db.add(group)
    db.flush()

    for aid in payload.agent_ids:
        db.add(GroupMembership(
            id=str(uuid.uuid4()),
            group_id=group.id,
            agent_id=aid,
            joined_at=datetime.utcnow(),
        ))

    db.commit()
    db.refresh(group)
    members = _load_members(group.id, db)
    return _group_to_dict(group, members)


@router.get("/group-chats/{group_id}")
def get_group(group_id: str, db: Session = Depends(get_db)):
    group = db.query(GroupChat).filter(GroupChat.id == group_id).first()
    if not group:
        raise HTTPException(404, "Group chat not found")
    members  = _load_members(group_id, db)
    messages = (
        db.query(GroupMessage)
        .filter(GroupMessage.group_id == group_id)
        .order_by(GroupMessage.created_at)
        .all()
    )
    return _group_to_dict(group, members, messages)


@router.patch("/group-chats/{group_id}")
def rename_group(group_id: str, body: dict, db: Session = Depends(get_db)):
    group = db.query(GroupChat).filter(GroupChat.id == group_id).first()
    if not group:
        raise HTTPException(404, "Group chat not found")
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "title is required")
    group.title = title[:100]
    db.commit()
    return {"id": group.id, "title": group.title}


@router.delete("/group-chats/{group_id}", status_code=204)
def delete_group(group_id: str, db: Session = Depends(get_db)):
    group = db.query(GroupChat).filter(GroupChat.id == group_id).first()
    if not group:
        raise HTTPException(404, "Group chat not found")
    db.query(GroupMessage).filter(GroupMessage.group_id == group_id).delete()
    db.query(GroupMembership).filter(GroupMembership.group_id == group_id).delete()
    db.delete(group)
    db.commit()
    _group_apps.pop(group_id, None)


# ── WebSocket ──────────────────────────────────────────────────────────────────

@router.websocket("/group-chats/{group_id}/ws")
async def group_chat_ws(group_id: str, ws: WebSocket):
    await ws.accept()

    from web.db.database import SessionLocal
    db = SessionLocal()

    try:
        group = db.query(GroupChat).filter(GroupChat.id == group_id).first()
        if not group:
            await _send(ws, {"type": "error", "content": "Group chat not found"})
            return

        memberships = _load_members(group_id, db)
        participants = [
            {
                "id":            m.agent.id,
                "name":          m.agent.name,
                "product_line":  m.agent.product_line,
                "specialization": m.agent.specialization or "",
                "avatar_emoji":  m.agent.avatar_emoji,
                "ranking":       m.agent.ranking or "Intern",
            }
            for m in memberships
            if m.agent and m.agent.is_active
        ]

        if len(participants) < 2:
            await _send(ws, {"type": "error", "content": "Need at least 2 active agents"})
            return

        app = _get_orchestrator(group_id, participants)

        while True:
            data = await ws.receive_json()
            if data.get("type") != "message":
                continue

            user_content = data.get("content", "").strip()
            if not user_content:
                continue

            # Persist user message
            db.add(GroupMessage(
                id=str(uuid.uuid4()),
                group_id=group_id,
                speaker_type="user",
                speaker_name="You",
                speaker_emoji="👤",
                content=user_content,
                is_pass=False,
                created_at=datetime.utcnow(),
            ))
            if group.title == "New Group Chat":
                group.title = user_content[:60]
            db.commit()

            # Build history context from all previous DB messages (before this one)
            history_rows = (
                db.query(GroupMessage)
                .filter(GroupMessage.group_id == group_id)
                .order_by(GroupMessage.created_at)
                .all()
            )
            history_lines = []
            for m in history_rows:
                if m.content == user_content and m.speaker_type == "user":
                    # skip the message we just added — it goes into messages[0]
                    continue
                if m.speaker_type == "user":
                    history_lines.append(f"[User]: {m.content}")
                elif m.is_pass:
                    history_lines.append(f"[{m.speaker_emoji} {m.speaker_name}]: (passed)")
                else:
                    history_lines.append(f"[{m.speaker_emoji} {m.speaker_name}]: {m.content}")
            history_context = "\n\n".join(history_lines)

            # Initial LangGraph state — fresh per user message
            initial_state = {
                "messages":    [{"role": "user", "speaker": "You", "emoji": "👤",
                                  "content": user_content, "is_pass": False, "agent_id": None}],
                "history_context": history_context,
                "participants": participants,
                "turn_count":   0,
                "next_speaker": None,
                "is_resolved":  False,
                "agents_passed_this_round": [],
            }
            config = {"configurable": {"thread_id": str(uuid.uuid4())}}

            agent_messages_buffer = []

            try:
                async for event in _astream_group(app, initial_state, config):
                    node_name   = list(event.keys())[0]
                    node_output = event[node_name]

                    if not isinstance(node_output, dict):
                        continue

                    if node_name == "supervisor":
                        # Emit "thinking" for whoever speaks next
                        next_id = node_output.get("next_speaker")
                        if next_id:
                            info = next((p for p in participants if p["id"] == next_id), None)
                            if info:
                                await _send(ws, {
                                    "type":       "agent_thinking",
                                    "agent_id":   info["id"],
                                    "agent_name": info["name"],
                                    "agent_emoji": info["avatar_emoji"],
                                })
                    else:
                        # Agent node — node_name == agent_id
                        for msg in node_output.get("messages", []):
                            if msg.get("role") != "agent":
                                continue
                            if msg["is_pass"]:
                                await _send(ws, {
                                    "type":       "agent_pass",
                                    "agent_id":   msg["agent_id"],
                                    "agent_name": msg["speaker"],
                                    "agent_emoji": msg["emoji"],
                                })
                            else:
                                await _send(ws, {
                                    "type":       "agent_message",
                                    "agent_id":   msg["agent_id"],
                                    "agent_name": msg["speaker"],
                                    "agent_emoji": msg["emoji"],
                                    "content":    msg["content"],
                                })
                            agent_messages_buffer.append(msg)

            except Exception as exc:
                await _send(ws, {"type": "error", "content": str(exc)})

            # Persist all agent responses
            for msg in agent_messages_buffer:
                db.add(GroupMessage(
                    id=str(uuid.uuid4()),
                    group_id=group_id,
                    speaker_type="agent",
                    speaker_id=msg["agent_id"],
                    speaker_name=msg["speaker"],
                    speaker_emoji=msg["emoji"],
                    content=msg.get("content", ""),
                    is_pass=msg.get("is_pass", False),
                    created_at=datetime.utcnow(),
                ))
            db.commit()

            await _send(ws, {"type": "done"})

    except (_WSD, Exception):
        pass
    finally:
        db.close()
