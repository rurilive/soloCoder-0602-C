from fastapi import WebSocket
import json


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, room_id: str, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(room_id, []).append(ws)

    def disconnect(self, room_id: str, ws: WebSocket):
        if room_id in self.active:
            self.active[room_id] = [w for w in self.active[room_id] if w is not ws]
            if not self.active[room_id]:
                del self.active[room_id]

    async def broadcast(self, room_id: str, data: dict):
        raw = json.dumps(data, ensure_ascii=False, default=str)
        for ws in self.active.get(room_id, []):
            try:
                await ws.send_text(raw)
            except Exception:
                pass

    async def send_to_user(self, room_id: str, user_id: str, data: dict):
        raw = json.dumps(data, ensure_ascii=False, default=str)
        for ws in self.active.get(room_id, []):
            try:
                uid = ws.query_params.get("user_id")
                if uid == user_id:
                    await ws.send_text(raw)
            except Exception:
                pass


manager = ConnectionManager()
