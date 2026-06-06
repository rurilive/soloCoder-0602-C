import os
import json
import uuid
import hashlib
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from werkzeug.utils import secure_filename

from .config import FILES_DIR, SHARES_DIR, USERS_DIR


def ensure_dirs():
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    SHARES_DIR.mkdir(parents=True, exist_ok=True)
    USERS_DIR.mkdir(parents=True, exist_ok=True)


def get_abs_path(rel_path: str) -> Path:
    rel_path = rel_path.lstrip("/")
    abs_path = (FILES_DIR / rel_path).resolve()
    if not str(abs_path).startswith(str(FILES_DIR.resolve())):
        raise ValueError("Invalid path")
    return abs_path


def get_file_info(path: Path) -> Dict:
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path.relative_to(FILES_DIR)),
        "isDir": path.is_dir(),
        "size": stat.st_size if path.is_file() else 0,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "extension": path.suffix.lower() if path.is_file() else "",
    }


def list_directory(rel_path: str) -> List[Dict]:
    abs_path = get_abs_path(rel_path)
    if not abs_path.exists() or not abs_path.is_dir():
        return []
    items = []
    for item in abs_path.iterdir():
        items.append(get_file_info(item))
    items.sort(key=lambda x: (not x["isDir"], x["name"].lower()))
    return items


def create_folder(rel_path: str, name: str) -> Dict:
    abs_path = get_abs_path(rel_path) / secure_filename(name)
    abs_path.mkdir(parents=True, exist_ok=True)
    return get_file_info(abs_path)


def delete_item(rel_path: str) -> bool:
    abs_path = get_abs_path(rel_path)
    if not abs_path.exists():
        return False
    if abs_path.is_dir():
        shutil.rmtree(abs_path)
    else:
        abs_path.unlink()
    return True


def rename_item(rel_path: str, new_name: str) -> Dict:
    abs_path = get_abs_path(rel_path)
    parent = abs_path.parent
    new_path = parent / secure_filename(new_name)
    abs_path.rename(new_path)
    return get_file_info(new_path)


def move_item(src_rel: str, dst_rel: str) -> Dict:
    src_path = get_abs_path(src_rel)
    dst_path = get_abs_path(dst_rel)
    if dst_path.is_dir():
        dst_path = dst_path / src_path.name
    shutil.move(str(src_path), str(dst_path))
    return get_file_info(dst_path)


def copy_item(src_rel: str, dst_rel: str) -> Dict:
    src_path = get_abs_path(src_rel)
    dst_path = get_abs_path(dst_rel)
    if dst_path.is_dir():
        dst_path = dst_path / src_path.name
    if src_path.is_dir():
        shutil.copytree(src_path, dst_path)
    else:
        shutil.copy2(src_path, dst_path)
    return get_file_info(dst_path)


def save_upload(rel_path: str, file_storage) -> Dict:
    abs_dir = get_abs_path(rel_path)
    abs_dir.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(file_storage.filename)
    file_path = abs_dir / filename
    counter = 1
    while file_path.exists():
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        file_path = abs_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    file_storage.save(str(file_path))
    return get_file_info(file_path)


def create_share(rel_path: str, expire_hours: Optional[int] = None, password: Optional[str] = None) -> Dict:
    share_id = str(uuid.uuid4())[:12]
    expire_at = None
    if expire_hours:
        expire_at = (datetime.now() + timedelta(hours=expire_hours)).isoformat()
    password_hash = None
    if password:
        password_hash = hashlib.sha256(password.encode()).hexdigest()
    share_data = {
        "id": share_id,
        "path": rel_path,
        "expireAt": expire_at,
        "passwordHash": password_hash,
        "createdAt": datetime.now().isoformat(),
    }
    share_file = SHARES_DIR / f"{share_id}.json"
    with open(share_file, "w") as f:
        json.dump(share_data, f)
    return {"id": share_id, "expireAt": expire_at, "hasPassword": password is not None}


def get_share(share_id: str, password: Optional[str] = None) -> Tuple[Optional[Dict], Optional[str]]:
    share_file = SHARES_DIR / f"{share_id}.json"
    if not share_file.exists():
        return None, "Share not found"
    with open(share_file, "r") as f:
        share = json.load(f)
    if share.get("expireAt"):
        expire_at = datetime.fromisoformat(share["expireAt"])
        if datetime.now() > expire_at:
            share_file.unlink()
            return None, "Share has expired"
    if share.get("passwordHash"):
        if not password:
            return None, "Password required"
        input_hash = hashlib.sha256(password.encode()).hexdigest()
        if input_hash != share["passwordHash"]:
            return None, "Invalid password"
    return share, None


def search_files(query: str, extension: Optional[str] = None, path: str = "") -> List[Dict]:
    abs_path = get_abs_path(path)
    if not abs_path.exists() or not abs_path.is_dir():
        return []
    query = query.lower()
    results = []
    for item in abs_path.rglob("*"):
        try:
            if query in item.name.lower():
                if extension:
                    ext = f".{extension.lstrip('.').lower()}"
                    if item.is_file() and item.suffix.lower() != ext:
                        continue
                results.append(get_file_info(item))
        except (PermissionError, OSError):
            continue
    results.sort(key=lambda x: (not x["isDir"], x["name"].lower()))
    return results
