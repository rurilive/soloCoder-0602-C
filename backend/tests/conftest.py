import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event

from app.main import app
from app.database import Base, get_db
from app.models import User, Room, RoomMember, Message, ReadReceipt, UserRole


TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_chat.db"


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()

    import os
    if os.path.exists("./test_chat.db"):
        os.remove("./test_chat.db")


@pytest_asyncio.fixture
async def test_session(test_engine):
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def client(test_session):
    async def override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_users(test_session):
    users = [
        User(id="user1", username="Alice", avatar="avatar1.png", role=UserRole.USER.value),
        User(id="user2", username="Bob", avatar="avatar2.png", role=UserRole.USER.value),
        User(id="user3", username="Charlie", avatar="avatar3.png", role=UserRole.USER.value),
        User(id="admin1", username="Admin", avatar="admin.png", role=UserRole.ADMIN.value),
    ]
    test_session.add_all(users)
    await test_session.commit()
    for u in users:
        await test_session.refresh(u)
    return users


async def get_token(client, user_id: str) -> str:
    resp = await client.post("/api/login", json={"user_id": user_id})
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
