from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
import jwt
from jwt.exceptions import InvalidTokenError, DecodeError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..services.connection_manager import manager
from ..config import SECRET_KEY, ALGORITHM
from ..database import get_db
from ..models import User, Message, ReadReceipt

router = APIRouter(tags=["websocket"])


async def get_ws_user(ws: WebSocket, db: AsyncSession = Depends(get_db)) -> User | None:
    token = ws.query_params.get("token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
    except (InvalidTokenError, DecodeError):
        return None

    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def send_missing_messages(ws: WebSocket, room_id: str, last_event_id: str, db: AsyncSession):
    try:
        since_msg = await db.execute(select(Message).where(Message.id == last_event_id))
        since_msg_obj = since_msg.scalar_one_or_none()
        if not since_msg_obj:
            return

        base_query = select(Message).where(
            Message.room_id == room_id,
            Message.seq > since_msg_obj.seq,
        )

        result = await db.execute(
            base_query.order_by(Message.seq.asc()).limit(200)
        )
        messages = result.scalars().all()

        if not messages:
            return

        message_ids = [m.id for m in messages]
        read_by_map = {}
        if message_ids:
            rr_result = await db.execute(
                select(ReadReceipt.message_id, ReadReceipt.user_id)
                .where(ReadReceipt.message_id.in_(message_ids))
            )
            for msg_id, user_id in rr_result.all():
                if msg_id not in read_by_map:
                    read_by_map[msg_id] = []
                read_by_map[msg_id].append(user_id)

        for msg in messages:
            read_by = read_by_map.get(msg.id, [])
            await ws.send_json({
                "type": "new_message",
                "payload": {
                    "id": msg.id,
                    "room_id": msg.room_id,
                    "sender_id": msg.sender_id,
                    "content": msg.content,
                    "is_recalled": msg.is_recalled,
                    "created_at": msg.created_at.isoformat(),
                    "read_by": read_by,
                },
            })
    except Exception:
        pass


@router.websocket("/ws/{room_id}")
async def ws_endpoint(
    ws: WebSocket,
    room_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await get_ws_user(ws, db)
    if not user:
        await ws.close(code=1008, reason="Unauthorized")
        return

    user_id = user.id
    last_event_id = ws.query_params.get("last_event_id")

    await manager.connect(room_id, ws)

    if last_event_id:
        await send_missing_messages(ws, room_id, last_event_id, db)

    await manager.broadcast(room_id, {
        "type": "user_joined",
        "payload": {"user_id": user_id, "room_id": room_id},
    })

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "typing":
                await manager.broadcast(room_id, {
                    "type": "typing",
                    "payload": {
                        "room_id": room_id,
                        "user_id": user_id,
                        "username": data.get("username", user_id),
                        "is_typing": data.get("is_typing", True),
                    },
                })
    except WebSocketDisconnect:
        manager.disconnect(room_id, ws)
        await manager.broadcast(room_id, {
            "type": "user_left",
            "payload": {"user_id": user_id, "room_id": room_id},
        })
