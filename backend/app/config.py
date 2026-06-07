import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FILES_BASE_DIR = DATA_DIR / "files"
SHARES_DIR = DATA_DIR / "shares"
USERS_DIR = DATA_DIR / "users"
TMP_DIR = DATA_DIR / "tmp"
TRASH_DIR_NAME = ".trash"
TRASH_EXPIRE_DAYS = 30
DEFAULT_STORAGE_QUOTA = 500 * 1024 * 1024
CHUNK_SIZE = 5 * 1024 * 1024

def get_user_files_dir(username: str) -> Path:
    return FILES_BASE_DIR / username

def get_user_trash_dir(username: str) -> Path:
    return get_user_files_dir(username) / TRASH_DIR_NAME

class Config:
    PORT = 3331
    HOST = "0.0.0.0"
    MAX_CONTENT_LENGTH = 1024 * 1024 * 1024
    FILES_BASE_DIR = FILES_BASE_DIR
    SHARES_DIR = SHARES_DIR
    USERS_DIR = USERS_DIR
    TRASH_DIR_NAME = TRASH_DIR_NAME
    TRASH_EXPIRE_DAYS = TRASH_EXPIRE_DAYS
    DEFAULT_STORAGE_QUOTA = DEFAULT_STORAGE_QUOTA
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret-key-change-in-production")
    JWT_EXPIRE_HOURS = 24
