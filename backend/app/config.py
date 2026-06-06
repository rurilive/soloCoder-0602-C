import os

PORT = int(os.getenv("PORT", 3331))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./chat.db")
RECALL_WINDOW_SECONDS = 120
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production-32-chars-min!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days
