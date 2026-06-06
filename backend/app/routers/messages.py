from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta, timezone
import uuid

from ..database import get_db
from ..models import User, Room, RoomMember, Message, ReadReceipt
from ..schemas import (
    UserCreate, UserOut, RoomCreate, RoomOut,
    MessageCreate, MessageOut, ReadReceiptCreate,
    MessageListResponse,
)
from ..config import RECALL_WINDOW_SECONDS
from ..services.connection_manager import manager

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/users", response_model=UserOut)
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == body.id))
    if result.scalar_one_or_none():
        raise HTTPException(400, "User already exists")
    user = User(id=body.id, username=body.username, avatar=body.avatar)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/users", response_model=list[UserOut])
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    return result.scalars().all()


@router.post("/rooms", response_model=RoomOut)
async def create_room(body: RoomCreate, db: AsyncSession = Depends(get_db)):
    member_ids = sorted(list(set(body.member_ids)))
    if len(member_ids) < 2:
        raise HTTPException(400, "At least 2 members are required to create a room")

    users_result = await db.execute(select(User.id).where(User.id.in_(member_ids)))
    existing_user_ids = {uid for uid in users_result.scalars().all()}
    missing_user_ids = [uid for uid in member_ids if uid not in existing_user_ids]
    if missing_user_ids:
        raise HTTPException(400, f"Users not found: {', '.join(missing_user_ids)}")

    room_result = await db.execute(
        select(RoomMember.room_id)
        .where(RoomMember.user_id.in_(member_ids))
        .group_by(RoomMember.room_id)
        .having(func.count(RoomMember.user_id) == len(member_ids))
    )

    for room_id in room_result.scalars().all():
        rm_check = await db.execute(
            select(func.count()).select_from(RoomMember).where(RoomMember.room_id == room_id)
        )
        if rm_check.scalar_one() == len(member_ids):
            r = await db.execute(select(Room).where(Room.id == room_id))
            existing_room = r.scalar_one_or_none()
            if existing_room and existing_room.is_group == body.is_group:
                if body.is_group:
                    name_match = (existing_room.name is None and body.name is None) or \
                                 (existing_room.name is not None and body.name is not None and existing_room.name == body.name)
                    if not name_match:
                        continue
                members_result = await db.execute(
                    select(User).join(RoomMember, RoomMember.user_id == User.id).where(RoomMember.room_id == room_id)
                )
                members = members_result.scalars().all()
                return RoomOut(id=existing_room.id, name=existing_room.name, is_group=existing_room.is_group, members=members)

    room_id = str(uuid.uuid4())
    room = Room(id=room_id, name=body.name, is_group=body.is_group)
    db.add(room)
    for uid in member_ids:
        db.add(RoomMember(room_id=room_id, user_id=uid))
    await db.commit()
    await db.refresh(room)

    result = await db.execute(
        select(User).join(RoomMember, RoomMember.user_id == User.id).where(RoomMember.room_id == room_id)
    )
    members = result.scalars().all()
    return RoomOut(id=room.id, name=room.name, is_group=room.is_group, members=members)


@router.get("/rooms/{user_id}", response_model=list[RoomOut])
async def list_rooms(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RoomMember.room_id).where(RoomMember.user_id == user_id)
    )
    room_ids = [r for r in result.scalars().all()]
    rooms_out = []
    for rid in room_ids:
        room_result = await db.execute(select(Room).where(Room.id == rid))
        room = room_result.scalar_one()
        members_result = await db.execute(
            select(User).join(RoomMember, RoomMember.user_id == User.id).where(RoomMember.room_id == rid)
        )
        members = members_result.scalars().all()
        rooms_out.append(RoomOut(id=room.id, name=room.name, is_group=room.is_group, members=members))
    return rooms_out


@router.post("/messages", response_model=MessageOut)
async def send_message(body: MessageCreate, db: AsyncSession = Depends(get_db)):
    msg_id = str(uuid.uuid4())
    msg = Message(id=msg_id, room_id=body.room_id, sender_id=body.sender_id, content=body.content)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    await manager.broadcast(body.room_id, {
        "type": "new_message",
        "payload": {
            "id": msg.id,
            "room_id": msg.room_id,
            "sender_id": msg.sender_id,
            "content": msg.content,
            "is_recalled": msg.is_recalled,
            "created_at": msg.created_at.isoformat(),
            "read_by": [],
        },
    })

    return MessageOut(
        id=msg.id, room_id=msg.room_id, sender_id=msg.sender_id,
        content=msg.content, is_recalled=msg.is_recalled,
        created_at=msg.created_at, read_by=[],
    )


@router.get("/messages/{room_id}", response_model=MessageListResponse)
async def list_messages(
    room_id: str,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    if limit < 1:
        limit = 50
    if limit > 200:
        limit = 200
    if offset < 0:
        offset = 0

    count_result = await db.execute(
        select(func.count()).select_from(Message).where(Message.room_id == room_id)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(Message)
        .where(Message.room_id == room_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    messages = result.scalars().all()
    out = []
    for m in messages:
        rr = await db.execute(select(ReadReceipt.user_id).where(ReadReceipt.message_id == m.id))
        read_by = [r for r in rr.scalars().all()]
        out.append(MessageOut(
            id=m.id, room_id=m.room_id, sender_id=m.sender_id,
            content=m.content, is_recalled=m.is_recalled,
            created_at=m.created_at, read_by=read_by,
        ))
    return MessageListResponse(total=total, limit=limit, offset=offset, items=out)


@router.put("/messages/{message_id}/recall")
async def recall_message(message_id: str, user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Message).where(Message.id == message_id))
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(404, "Message not found")
    if msg.sender_id != user_id:
        raise HTTPException(403, "Cannot recall others' messages")
    now = datetime.now(timezone.utc)
    if msg.created_at.tzinfo is None:
        msg_time = msg.created_at.replace(tzinfo=timezone.utc)
    else:
        msg_time = msg.created_at
    if now - msg_time > timedelta(seconds=RECALL_WINDOW_SECONDS):
        raise HTTPException(400, "Recall window expired (2 minutes)")
    msg.is_recalled = True
    await db.commit()

    await manager.broadcast(msg.room_id, {
        "type": "message_recalled",
        "payload": {"message_id": msg.id, "room_id": msg.room_id},
    })

    return {"status": "ok"}


@router.post("/messages/read")
async def mark_read(body: ReadReceiptCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ReadReceipt).where(
            ReadReceipt.message_id == body.message_id,
            ReadReceipt.user_id == body.user_id,
        )
    )
    if result.scalar_one_or_none():
        return {"status": "already_read"}

    receipt = ReadReceipt(message_id=body.message_id, user_id=body.user_id)
    db.add(receipt)
    await db.commit()

    msg_result = await db.execute(select(Message).where(Message.id == body.message_id))
    msg = msg_result.scalar_one_or_none()
    if msg:
        await manager.broadcast(msg.room_id, {
            "type": "read_receipt",
            "payload": {"message_id": body.message_id, "user_id": body.user_id, "room_id": msg.room_id},
        })

    return {"status": "ok"}
