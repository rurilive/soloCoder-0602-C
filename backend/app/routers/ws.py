from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..services.connection_manager import manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{room_id}")
async def ws_endpoint(ws: WebSocket, room_id: str):
    user_id = ws.query_params.get("user_id", "unknown")
    await manager.connect(room_id, ws)

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
