import os

PORT = int(os.getenv("PORT", 3331))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./chat.db")
RECALL_WINDOW_SECONDS = 120
