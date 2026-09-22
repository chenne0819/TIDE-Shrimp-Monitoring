from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import utcnow
from ..storage import aware
from .models import Activity, AssistantResult, Conversation, Message
from .schemas import StrictModel
from .service import ACTIVE

def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/assistant", tags=["AI analysis"], dependencies=[Depends(no_store)])


def database(request: Request):
    with request.app.state.sessions() as db:
        yield db


Database = Annotated[Session, Depends(database)]


class CreateConversation(StrictModel):
    demo: bool = False


class SubmitMessage(StrictModel):
    message: str = Field(min_length=1, max_length=2000)
    request_id: UUID


def conversation_json(value):
    return {"id": value.id, "title": value.title, "demo": value.demo,
            "created_at": aware(value.created_at).isoformat(), "updated_at": aware(value.updated_at).isoformat()}


def activity_json(value):
    return {"id": value.id, "kind": value.kind, "label": value.label, "status": value.status,
            "started_at": aware(value.started_at).isoformat(),
            "finished_at": aware(value.finished_at).isoformat() if value.finished_at else None,
            "detail": value.detail, "metadata": value.activity_metadata}


def message_activity(db, message_ids):
    """One bounded batch for a conversation, including messages with no history."""
    result = {message_id: [] for message_id in message_ids}
    if result:
        rows = db.scalars(select(Activity).where(Activity.message_id.in_(list(result)))
                          .order_by(Activity.message_id, Activity.position))
        for row in rows:
            result[row.message_id].append(activity_json(row))
    return result


def message_presentations(db, message_ids):
    # Read only routing metadata; computed facts stay private to the service.
    if not message_ids:
        return {}
    return dict(db.execute(select(AssistantResult.message_id, AssistantResult.presentation)
                           .where(AssistantResult.message_id.in_(message_ids))).all())


def message_json(value, activity=None, presentation=None):
    kind = ("analysis" if presentation == "board" or value.board is not None else
            "answer" if presentation == "answer" or value.status not in ACTIVE else "pending")
    return {"id": value.id, "role": value.role, "content": value.content, "status": value.status,
            "created_at": aware(value.created_at).isoformat(), "board": value.board,
            "followups": value.followups, "error": value.error, "activity": activity or [], "response_kind": kind}


def find_conversation(db, conversation_id, *, lock=False):
    statement = select(Conversation).where(Conversation.id == str(conversation_id))
    if lock:
        statement = statement.with_for_update()
    result = db.scalar(statement)
    if result is None:
        raise HTTPException(404, "找不到這個對話")
    return result


@router.get("/capabilities")
def capabilities(db: Database, demo: bool = False):
    from .analytics import get_catalog
    from .providers import provider_status
    return {**get_catalog(db, demo=demo), **provider_status()}


@router.get("/conversations")
def list_conversations(db: Database, demo: bool = False, limit: int = Query(30, ge=1, le=100)):
    items = db.scalars(select(Conversation).where(Conversation.demo == demo)
                       .order_by(Conversation.updated_at.desc()).limit(limit))
    return {"items": [conversation_json(value) for value in items]}


@router.post("/conversations", status_code=201)
def create_conversation(payload: CreateConversation, db: Database):
    value = Conversation(id=str(uuid4()), title="新的分析", demo=payload.demo)
    db.add(value)
    db.commit()
    return conversation_json(value)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: UUID, db: Database):
    value = find_conversation(db, conversation_id)
    items = list(db.scalars(select(Message).where(Message.conversation_id == value.id)
                            .order_by(Message.position).limit(40)))
    activities = message_activity(db, [item.id for item in items])
    presentations = message_presentations(db, [item.id for item in items])
    return {**conversation_json(value), "messages": [message_json(item, activities[item.id], presentations.get(item.id)) for item in items]}


@router.post("/conversations/{conversation_id}/messages", status_code=202)
async def submit_message(conversation_id: UUID, payload: SubmitMessage, request: Request, db: Database):
    from .providers import provider_status
    question = payload.message.strip()
    if not question or any(ord(c) < 32 and c not in "\n\t\r" for c in question):
        raise HTTPException(422, "請輸入 1 至 2000 字的問題")
    conversation = find_conversation(db, conversation_id, lock=True)
    previous = db.scalar(select(Message).where(
        Message.conversation_id == conversation.id, Message.request_id == str(payload.request_id),
        Message.role == "assistant"))
    if previous:
        original = db.scalar(select(Message).where(Message.conversation_id == conversation.id,
                              Message.request_id == str(payload.request_id), Message.role == "user"))
        if original.content != question:
            raise HTTPException(409, "這個請求編號已用於另一個問題")
        return message_json(previous, message_activity(db, [previous.id])[previous.id],
                            message_presentations(db, [previous.id]).get(previous.id))
    if conversation.active_message_id:
        raise HTTPException(409, "這個對話已有正在執行的分析，請等待或先停止")
    status = provider_status()
    if not status["enabled"]:
        raise HTTPException(503, status.get("reason") or "AI 分析尚未設定")
    service = request.app.state.assistant
    if not service.has_capacity():
        raise HTTPException(429, "目前分析請求已滿，請稍後再試")
    count = db.scalar(select(func.count()).select_from(Message).where(Message.conversation_id == conversation.id))
    if count >= 40:
        raise HTTPException(409, "這個對話已達 20 次提問，請開啟新對話")
    user = Message(id=str(uuid4()), conversation_id=conversation.id, request_id=str(payload.request_id),
                   position=count, role="user", content=question, status="completed")
    result = Message(id=str(uuid4()), conversation_id=conversation.id, request_id=str(payload.request_id),
                     position=count + 1, role="assistant", content="", status="planning")
    db.add_all([user, result])
    conversation.active_message_id = result.id
    conversation.updated_at = utcnow()
    if count == 0:
        conversation.title = question[:60]
    db.commit()
    service.start(result.id, question)
    return message_json(result)


@router.post("/messages/{message_id}/cancel")
async def cancel_message(message_id: UUID, request: Request, db: Database):
    value = db.get(Message, str(message_id))
    if value is None or value.role != "assistant":
        raise HTTPException(404, "找不到這次分析")
    if value.status in ACTIVE:
        await request.app.state.assistant.cancel(value.id)
        db.expire_all()
        value = db.get(Message, str(message_id))
    return message_json(value, message_activity(db, [value.id])[value.id],
                        message_presentations(db, [value.id]).get(value.id))
