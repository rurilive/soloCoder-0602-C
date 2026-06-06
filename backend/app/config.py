import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FILES_DIR = DATA_DIR / "files"
SHARES_DIR = DATA_DIR / "shares"
USERS_DIR = DATA_DIR / "users"

class Config:
    PORT = 3331
    HOST = "0.0.0.0"
    MAX_CONTENT_LENGTH = 1024 * 1024 * 1024
    FILES_DIR = FILES_DIR
    SHARES_DIR = SHARES_DIR
    USERS_DIR = USERS_DIR
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret-key-change-in-production")
    JWT_EXPIRE_HOURS = 24
