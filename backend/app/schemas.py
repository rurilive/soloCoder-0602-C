from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import enum


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class UserCreate(BaseModel):
    id: str
    username: str
    avatar: Optional[str] = None
    role: Optional[UserRole] = UserRole.USER


class UserOut(BaseModel):
    id: str
    username: str
    avatar: Optional[str] = None
    role: UserRole

    model_config = {"from_attributes": True}


class RoomCreate(BaseModel):
    name: Optional[str] = None
    is_group: bool = False
    member_ids: list[str]


class RoomOut(BaseModel):
    id: str
    name: Optional[str] = None
    is_group: bool
    members: list[UserOut]


class MessageCreate(BaseModel):
    room_id: str
    sender_id: str
    content: str


class MessageOut(BaseModel):
    id: str
    room_id: str
    sender_id: str
    content: str
    is_recalled: bool
    created_at: datetime
    read_by: list[str] = []

    model_config = {"from_attributes": True}


class ReadReceiptCreate(BaseModel):
    message_id: str
    user_id: str


class TypingPayload(BaseModel):
    room_id: str
    user_id: str
    username: str
    is_typing: bool


class MessageListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[MessageOut]


class WSMessage(BaseModel):
    type: str
    payload: dict


class Token(BaseModel):
    access_token: str
    token_type: str


class LoginRequest(BaseModel):
    user_id: str
