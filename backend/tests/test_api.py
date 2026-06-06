import pytest
import uuid
from datetime import datetime, timedelta, timezone


@pytest.mark.asyncio
async def test_create_room_success(client, test_users):
    response = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_group"] is False
    assert len(data["members"]) == 2
    member_ids = {m["id"] for m in data["members"]}
    assert member_ids == {"user1", "user2"}


@pytest.mark.asyncio
async def test_create_room_with_nonexistent_users(client, test_users):
    response = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "nonexistent"], "is_group": False},
    )
    assert response.status_code == 400
    assert "Users not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_room_with_insufficient_members(client, test_users):
    response = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1"], "is_group": False},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_room_deduplication(client, test_users):
    response1 = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
    )
    assert response1.status_code == 200
    room1_id = response1.json()["id"]

    response2 = await client.post(
        "/api/rooms",
        json={"member_ids": ["user2", "user1"], "is_group": False},
    )
    assert response2.status_code == 200
    room2_id = response2.json()["id"]

    assert room1_id == room2_id


@pytest.mark.asyncio
async def test_create_group_room(client, test_users):
    response = await client.post(
        "/api/rooms",
        json={
            "member_ids": ["user1", "user2", "user3"],
            "is_group": True,
            "name": "Test Group",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_group"] is True
    assert data["name"] == "Test Group"
    assert len(data["members"]) == 3


@pytest.mark.asyncio
async def test_send_message_success(client, test_users):
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
    )
    room_id = room_resp.json()["id"]

    response = await client.post(
        "/api/messages",
        json={
            "room_id": room_id,
            "sender_id": "user1",
            "content": "Hello, world!",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["room_id"] == room_id
    assert data["sender_id"] == "user1"
    assert data["content"] == "Hello, world!"
    assert data["is_recalled"] is False


@pytest.mark.asyncio
async def test_list_messages_pagination(client, test_users):
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
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
        )

    response = await client.get(f"/api/messages/{room_id}?limit=20&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 60
    assert data["limit"] == 20
    assert data["offset"] == 0
    assert len(data["items"]) == 20

    response2 = await client.get(f"/api/messages/{room_id}?limit=20&offset=40")
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["total"] == 60
    assert len(data2["items"]) == 20

    all_content = {m["content"] for m in data["items"]} | {m["content"] for m in data2["items"]}
    assert len(all_content) == 40


@pytest.mark.asyncio
async def test_recall_message_success(client, test_users):
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
    )
    room_id = room_resp.json()["id"]

    msg_resp = await client.post(
        "/api/messages",
        json={
            "room_id": room_id,
            "sender_id": "user1",
            "content": "To be recalled",
        },
    )
    msg_id = msg_resp.json()["id"]

    response = await client.put(f"/api/messages/{msg_id}/recall?user_id=user1")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    msgs_resp = await client.get(f"/api/messages/{room_id}")
    msgs = msgs_resp.json()["items"]
    recalled_msg = next(m for m in msgs if m["id"] == msg_id)
    assert recalled_msg["is_recalled"] is True


@pytest.mark.asyncio
async def test_recall_message_not_owner(client, test_users):
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
    )
    room_id = room_resp.json()["id"]

    msg_resp = await client.post(
        "/api/messages",
        json={
            "room_id": room_id,
            "sender_id": "user1",
            "content": "Cannot recall this",
        },
    )
    msg_id = msg_resp.json()["id"]

    response = await client.put(f"/api/messages/{msg_id}/recall?user_id=user2")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_recall_message_not_found(client, test_users):
    response = await client.put("/api/messages/nonexistent/recall?user_id=user1")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_mark_read_success(client, test_users):
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
    )
    room_id = room_resp.json()["id"]

    msg_resp = await client.post(
        "/api/messages",
        json={
            "room_id": room_id,
            "sender_id": "user1",
            "content": "Read me",
        },
    )
    msg_id = msg_resp.json()["id"]

    response = await client.post(
        "/api/messages/read",
        json={"message_id": msg_id, "user_id": "user2"},
    )
    assert response.status_code == 200

    msgs_resp = await client.get(f"/api/messages/{room_id}")
    msgs = msgs_resp.json()["items"]
    read_msg = next(m for m in msgs if m["id"] == msg_id)
    assert "user2" in read_msg["read_by"]


@pytest.mark.asyncio
async def test_mark_read_idempotent(client, test_users):
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
    )
    room_id = room_resp.json()["id"]

    msg_resp = await client.post(
        "/api/messages",
        json={
            "room_id": room_id,
            "sender_id": "user1",
            "content": "Read me twice",
        },
    )
    msg_id = msg_resp.json()["id"]

    await client.post(
        "/api/messages/read",
        json={"message_id": msg_id, "user_id": "user2"},
    )

    response = await client.post(
        "/api/messages/read",
        json={"message_id": msg_id, "user_id": "user2"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "already_read"


@pytest.mark.asyncio
async def test_list_messages_default_limit(client, test_users):
    room_resp = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user2"], "is_group": False},
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
        )

    response = await client.get(f"/api/messages/{room_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 50
    assert data["offset"] == 0
    assert data["total"] == 10
    assert len(data["items"]) == 10


@pytest.mark.asyncio
async def test_create_room_with_duplicate_member_ids(client, test_users):
    response = await client.post(
        "/api/rooms",
        json={"member_ids": ["user1", "user1", "user2"], "is_group": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["members"]) == 2
