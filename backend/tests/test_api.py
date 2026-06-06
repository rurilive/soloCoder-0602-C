import pytest
import uuid
from datetime import datetime, timedelta, timezone
from .conftest import get_token, auth_headers


@pytest.mark.asyncio
async def test_login_success(client, test_users):
    response = await client.post("/api/login", json={"user_id": "user1"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_user(client, test_users):
    response = await client.post("/api/login", json={"user_id": "nonexistent"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_user_success(client, test_users):
    response = await client.post(
        "/api/users",
        json={"id": "newuser", "username": "NewUser", "avatar": "new.png"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "newuser"
    assert data["role"] == "user"


@pytest.mark.asyncio
async def test_create_admin_user(client, test_users):
    response = await client.post(
        "/api/users",
        json={"id": "newadmin", "username": "NewAdmin", "avatar": "admin.png", "role": "admin"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "newadmin"
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_list_users_no_auth(client, test_users):
    response = await client.get("/api/users")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_users_with_auth(client, test_users):
    token = await get_token(client, "user1")
    response = await client.get("/api/users", headers=auth_headers(token))
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 3


@pytest.mark.asyncio
async def test_create_room_success(client, test_users):
    token = await get_token(client, "user1")
    response = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_group"] is False
    assert len(data["members"]) == 2
    member_ids = {m["id"] for m in data["members"]}
    assert member_ids == {"user1", "user2"}


@pytest.mark.asyncio
async def test_create_room_no_auth(client, test_users):
    response = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_room_with_nonexistent_users(client, test_users):
    token = await get_token(client, "user1")
    response = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "nonexistent"], "is_group": False},
        headers=auth_headers(token),
    )
    assert response.status_code == 400
    assert "Users not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_room_with_insufficient_members(client, test_users):
    token = await get_token(client, "user1")
    response = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1"], "is_group": False},
        headers=auth_headers(token),
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_room_deduplication(client, test_users):
    token = await get_token(client, "user1")
    response1 = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(token),
    )
    assert response1.status_code == 200
    room1_id = response1.json()["id"]

    response2 = await client.post(
        "/api/rooms",
        json={"member_ids": ["user2", "user1"], "is_group": False},
        headers=auth_headers(token),
    )
    assert response2.status_code == 200
    room2_id = response2.json()["id"]

    assert room1_id == room2_id


@pytest.mark.asyncio
async def test_create_group_room(client, test_users):
    token = await get_token(client, "user1")
    response = await client.post(
        "/api/rooms",
        json={
            "member_ids": ["user1", "user2", "user3"],
            "is_group": True,
            "name": "Test Group",
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_group"] is True
    assert data["name"] == "Test Group"
    assert len(data["members"]) == 3


@pytest.mark.asyncio
async def test_list_rooms_success(client, test_users):
    token = await get_token(client, "user1")
    await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(token),
    )

    response = await client.get(
        "/api/rooms/user1",
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_list_rooms_other_user_forbidden(client, test_users):
    token = await get_token(client, "user1")
    response = await client.get(
        "/api/rooms/user2",
        headers=auth_headers(token),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_rooms_admin_can_view_others(client, test_users):
    token = await get_token(client, "admin1")
    response = await client.get(
        "/api/rooms/user2",
        headers=auth_headers(token),
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_send_message_success(client, test_users):
    token = await get_token(client, "user1")
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(token),
    )
    room_id = room_resp.json()["id"]

    response = await client.post(
        "/api/messages",
        json={
            "room_id": room_id,
            "sender_id": "user1",
            "content": "Hello, world!",
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["room_id"] == room_id
    assert data["sender_id"] == "user1"
    assert data["content"] == "Hello, world!"
    assert data["is_recalled"] is False


@pytest.mark.asyncio
async def test_send_message_as_other_user_forbidden(client, test_users):
    token = await get_token(client, "user1")
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(token),
    )
    room_id = room_resp.json()["id"]

    response = await client.post(
        "/api/messages",
        json={
            "room_id": room_id,
            "sender_id": "user2",
            "content": "Fake message from user2",
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_send_message_admin_can_impersonate(client, test_users):
    token = await get_token(client, "admin1")
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(token),
    )
    room_id = room_resp.json()["id"]

    response = await client.post(
        "/api/messages",
        json={
            "room_id": room_id,
            "sender_id": "user1",
            "content": "Admin sent as user1",
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_send_message_not_member_forbidden(client, test_users):
    token = await get_token(client, "user3")
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(await get_token(client, "user1")),
    )
    room_id = room_resp.json()["id"]

    response = await client.post(
        "/api/messages",
        json={
            "room_id": room_id,
            "sender_id": "user3",
            "content": "I'm not a member!",
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 403
    assert "Not a member" in response.json()["detail"]


@pytest.mark.asyncio
async def test_send_message_admin_can_send_to_any_room(client, test_users):
    token_user1 = await get_token(client, "user1")
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(token_user1),
    )
    room_id = room_resp.json()["id"]

    token_admin = await get_token(client, "admin1")
    response = await client.post(
        "/api/messages",
        json={
            "room_id": room_id,
            "sender_id": "admin1",
            "content": "Admin message to any room",
        },
        headers=auth_headers(token_admin),
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_messages_pagination(client, test_users):
    token = await get_token(client, "user1")
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(token),
    )
    room_id = room_resp.json()["id"]

    for i in range(60):
        await client.post(
            "/api/messages",
            json={
                "room_id": room_id,
                "sender_id": "user1",
                "content": f"Message {i}",
            },
            headers=auth_headers(token),
        )

    response = await client.get(
        f"/api/messages/{room_id}?limit=20&offset=0",
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 60
    assert data["limit"] == 20
    assert data["offset"] == 0
    assert len(data["items"]) == 20

    response2 = await client.get(
        f"/api/messages/{room_id}?limit=20&offset=40",
        headers=auth_headers(token),
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["total"] == 60
    assert len(data2["items"]) == 20

    all_content = {m["content"] for m in data["items"]} | {m["content"] for m in data2["items"]}
    assert len(all_content) == 40


@pytest.mark.asyncio
async def test_list_messages_not_member_forbidden(client, test_users):
    token = await get_token(client, "user1")
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user2", "user3"], "is_group": False},
        headers=auth_headers(token),
    )
    room_id = room_resp.json()["id"]

    response = await client.get(
        f"/api/messages/{room_id}",
        headers=auth_headers(token),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_messages_admin_can_view_any(client, test_users):
    token = await get_token(client, "admin1")
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user2", "user3"], "is_group": False},
        headers=auth_headers(token),
    )
    room_id = room_resp.json()["id"]

    response = await client.get(
        f"/api/messages/{room_id}",
        headers=auth_headers(token),
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_recall_message_success(client, test_users):
    token = await get_token(client, "user1")
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(token),
    )
    room_id = room_resp.json()["id"]

    msg_resp = await client.post(
        "/api/messages",
        json={
            "room_id": room_id,
            "sender_id": "user1",
            "content": "To be recalled",
        },
        headers=auth_headers(token),
    )
    msg_id = msg_resp.json()["id"]

    response = await client.put(
        f"/api/messages/{msg_id}/recall",
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    msgs_resp = await client.get(
        f"/api/messages/{room_id}",
        headers=auth_headers(token),
    )
    msgs = msgs_resp.json()["items"]
    recalled_msg = next(m for m in msgs if m["id"] == msg_id)
    assert recalled_msg["is_recalled"] is True


@pytest.mark.asyncio
async def test_recall_message_not_owner(client, test_users):
    token1 = await get_token(client, "user1")
    token2 = await get_token(client, "user2")
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(token1),
    )
    room_id = room_resp.json()["id"]

    msg_resp = await client.post(
        "/api/messages",
        json={
            "room_id": room_id,
            "sender_id": "user1",
            "content": "Cannot recall this",
        },
        headers=auth_headers(token1),
    )
    msg_id = msg_resp.json()["id"]

    response = await client.put(
        f"/api/messages/{msg_id}/recall",
        headers=auth_headers(token2),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_recall_message_not_found(client, test_users):
    token = await get_token(client, "user1")
    response = await client.put(
        "/api/messages/nonexistent/recall",
        headers=auth_headers(token),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_recall_message_no_auth(client, test_users):
    response = await client.put("/api/messages/nonexistent/recall")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_recall_message_invalid_token(client, test_users):
    response = await client.put(
        "/api/messages/nonexistent/recall",
        headers=auth_headers("invalid_token"),
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_recall_others_message(client, test_users):
    token_admin = await get_token(client, "admin1")
    token_user1 = await get_token(client, "user1")
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(token_admin),
    )
    room_id = room_resp.json()["id"]

    msg_resp = await client.post(
        "/api/messages",
        json={
            "room_id": room_id,
            "sender_id": "user1",
            "content": "Admin can recall this",
        },
        headers=auth_headers(token_user1),
    )
    msg_id = msg_resp.json()["id"]

    response = await client.put(
        f"/api/messages/{msg_id}/recall",
        headers=auth_headers(token_admin),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    msgs_resp = await client.get(
        f"/api/messages/{room_id}",
        headers=auth_headers(token_admin),
    )
    msgs = msgs_resp.json()["items"]
    recalled_msg = next(m for m in msgs if m["id"] == msg_id)
    assert recalled_msg["is_recalled"] is True


@pytest.mark.asyncio
async def test_mark_read_success(client, test_users):
    token = await get_token(client, "user2")
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(token),
    )
    room_id = room_resp.json()["id"]

    token1 = await get_token(client, "user1")
    msg_resp = await client.post(
        "/api/messages",
        json={
            "room_id": room_id,
            "sender_id": "user1",
            "content": "Read me",
        },
        headers=auth_headers(token1),
    )
    msg_id = msg_resp.json()["id"]

    response = await client.post(
        "/api/messages/read",
        json={"message_id": msg_id, "user_id": "user2"},
        headers=auth_headers(token),
    )
    assert response.status_code == 200

    msgs_resp = await client.get(
        f"/api/messages/{room_id}",
        headers=auth_headers(token),
    )
    msgs = msgs_resp.json()["items"]
    read_msg = next(m for m in msgs if m["id"] == msg_id)
    assert "user2" in read_msg["read_by"]


@pytest.mark.asyncio
async def test_mark_read_other_user_forbidden(client, test_users):
    token1 = await get_token(client, "user1")
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(token1),
    )
    room_id = room_resp.json()["id"]

    msg_resp = await client.post(
        "/api/messages",
        json={
            "room_id": room_id,
            "sender_id": "user1",
            "content": "Read me",
        },
        headers=auth_headers(token1),
    )
    msg_id = msg_resp.json()["id"]

    response = await client.post(
        "/api/messages/read",
        json={"message_id": msg_id, "user_id": "user2"},
        headers=auth_headers(token1),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_mark_read_idempotent(client, test_users):
    token = await get_token(client, "user2")
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(token),
    )
    room_id = room_resp.json()["id"]

    token1 = await get_token(client, "user1")
    msg_resp = await client.post(
        "/api/messages",
        json={
            "room_id": room_id,
            "sender_id": "user1",
            "content": "Read me twice",
        },
        headers=auth_headers(token1),
    )
    msg_id = msg_resp.json()["id"]

    await client.post(
        "/api/messages/read",
        json={"message_id": msg_id, "user_id": "user2"},
        headers=auth_headers(token),
    )

    response = await client.post(
        "/api/messages/read",
        json={"message_id": msg_id, "user_id": "user2"},
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "already_read"


@pytest.mark.asyncio
async def test_list_messages_default_limit(client, test_users):
    token = await get_token(client, "user1")
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(token),
    )
    room_id = room_resp.json()["id"]

    for i in range(10):
        await client.post(
            "/api/messages",
            json={
                "room_id": room_id,
                "sender_id": "user1",
                "content": f"Msg {i}",
            },
            headers=auth_headers(token),
        )

    response = await client.get(
        f"/api/messages/{room_id}",
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 50
    assert data["offset"] == 0
    assert data["total"] == 10
    assert len(data["items"]) == 10


@pytest.mark.asyncio
async def test_create_room_with_duplicate_member_ids(client, test_users):
    token = await get_token(client, "user1")
    response = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user1", "user2"], "is_group": False},
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["members"]) == 2


@pytest.mark.asyncio
async def test_send_message_nonexistent_room_404(client, test_users):
    token = await get_token(client, "user1")
    response = await client.post(
        "/api/messages",
        json={
            "room_id": "nonexistent-room-id",
            "sender_id": "user1",
            "content": "Hello!",
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 404
    assert "Room not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_send_message_admin_nonexistent_room_404(client, test_users):
    token = await get_token(client, "admin1")
    response = await client.post(
        "/api/messages",
        json={
            "room_id": "nonexistent-room-id",
            "sender_id": "admin1",
            "content": "Hello!",
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 404
    assert "Room not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_list_messages_since_id(client, test_users):
    token = await get_token(client, "user1")
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
        headers=auth_headers(token),
    )
    room_id = room_resp.json()["id"]

    for i in range(5):
        await client.post(
            "/api/messages",
            json={
                "room_id": room_id,
                "sender_id": "user1",
                "content": f"Message {i}",
            },
            headers=auth_headers(token),
        )

    all_resp = await client.get(
        f"/api/messages/{room_id}?limit=50",
        headers=auth_headers(token),
    )
    all_messages = all_resp.json()["items"]
    assert len(all_messages) == 5

    third_msg_id = all_messages[2]["id"]
    since_resp = await client.get(
        f"/api/messages/{room_id}?limit=50&since_id={third_msg_id}",
        headers=auth_headers(token),
    )
    since_messages = since_resp.json()["items"]
    assert len(since_messages) == 2
    since_ids = {m["id"] for m in since_messages}
    assert third_msg_id not in since_ids
