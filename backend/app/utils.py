import os
import json
import uuid
import hashlib
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from werkzeug.utils import secure_filename

from .config import (
    get_user_files_dir,
    get_user_trash_dir,
    SHARES_DIR,
    USERS_DIR,
    FILES_BASE_DIR,
    TMP_DIR,
    TRASH_DIR_NAME,
    TRASH_EXPIRE_DAYS,
    DEFAULT_STORAGE_QUOTA,
)


def ensure_dirs():
    FILES_BASE_DIR.mkdir(parents=True, exist_ok=True)
    SHARES_DIR.mkdir(parents=True, exist_ok=True)
    USERS_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)


def get_dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except (PermissionError, OSError):
            continue
    return total


def get_user_storage_usage(username: str) -> dict:
    user_dir = get_user_files_dir_safe(username)
    trash_dir = get_user_trash_dir(username)
    total_size = get_dir_size(user_dir)
    trash_size = get_dir_size(trash_dir) if trash_dir.exists() else 0
    used_size = total_size - trash_size
    return {
        "used": used_size,
        "trash": trash_size,
        "total": total_size,
        "quota": DEFAULT_STORAGE_QUOTA,
        "remaining": max(0, DEFAULT_STORAGE_QUOTA - used_size),
    }


def check_storage_quota(username: str, required_size: int = 0) -> dict:
    usage = get_user_storage_usage(username)
    if usage["used"] + required_size > usage["quota"]:
        raise ValueError(
            f"存储空间不足，剩余 {usage['remaining']} 字节，需要 {required_size} 字节"
        )
    return usage


def get_trash_item_info(path: Path, username: str) -> Dict:
    user_files_dir = get_user_files_dir_safe(username)
    trash_dir = get_user_trash_dir(username)
    stat = path.stat()
    trash_rel_path = str(path.relative_to(trash_dir))
    parts = trash_rel_path.split("/")
    deleted_at_str = parts[0]
    original_path = "/".join(parts[1:])
    try:
        deleted_at = datetime.strptime(deleted_at_str, "%Y%m%d%H%M%S")
    except ValueError:
        deleted_at = datetime.fromtimestamp(stat.st_mtime)
    return {
        "name": path.name,
        "path": trash_rel_path,
        "originalPath": original_path,
        "isDir": path.is_dir(),
        "size": stat.st_size if path.is_file() else get_dir_size(path),
        "deletedAt": deleted_at.isoformat(),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "extension": path.suffix.lower() if path.is_file() else "",
    }


def soft_delete_item(rel_path: str, username: str) -> bool:
    abs_path = get_abs_path(rel_path, username)
    if not abs_path.exists():
        return False
    trash_dir = get_user_trash_dir(username)
    trash_dir.mkdir(parents=True, exist_ok=True)
    deleted_at = datetime.now()
    safe_deleted_at = deleted_at.strftime("%Y%m%d%H%M%S")
    trash_item_dir = trash_dir / safe_deleted_at
    trash_item_dir.mkdir(parents=True, exist_ok=True)
    dst_path = trash_item_dir / abs_path.name
    counter = 1
    base_name = abs_path.name
    while dst_path.exists():
        stem = Path(base_name).stem
        suffix = Path(base_name).suffix
        dst_path = trash_item_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    shutil.move(str(abs_path), str(dst_path))
    return True


def list_trash(username: str) -> List[Dict]:
    trash_dir = get_user_trash_dir(username)
    if not trash_dir.exists() or not trash_dir.is_dir():
        return []
    items = []
    for dated_dir in trash_dir.iterdir():
        if not dated_dir.is_dir():
            continue
        for item in dated_dir.iterdir():
            try:
                items.append(get_trash_item_info(item, username))
            except Exception:
                continue
    items.sort(key=lambda x: x["deletedAt"], reverse=True)
    return items


def restore_trash_item(trash_rel_path: str, username: str) -> Dict:
    trash_dir = get_user_trash_dir(username)
    abs_path = (trash_dir / trash_rel_path).resolve()
    if not str(abs_path).startswith(str(trash_dir.resolve())):
        raise ValueError("Invalid trash path")
    if not abs_path.exists():
        raise ValueError("Item not found in trash")
    parts = trash_rel_path.split("/")
    original_path = "/".join(parts[1:])
    user_files_dir = get_user_files_dir_safe(username)
    dst_path = user_files_dir / original_path
    if dst_path.exists():
        stem = dst_path.stem
        suffix = dst_path.suffix
        parent = dst_path.parent
        counter = 1
        while dst_path.exists():
            dst_path = parent / f"{stem}_restored{counter}{suffix}"
            counter += 1
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(abs_path), str(dst_path))
    dated_dir = abs_path.parent
    if not any(dated_dir.iterdir()):
        dated_dir.rmdir()
    return get_file_info(dst_path, username)


def permanently_delete_trash_item(trash_rel_path: str, username: str) -> bool:
    trash_dir = get_user_trash_dir(username)
    abs_path = (trash_dir / trash_rel_path).resolve()
    if not str(abs_path).startswith(str(trash_dir.resolve())):
        raise ValueError("Invalid trash path")
    if not abs_path.exists():
        return False
    if abs_path.is_dir():
        shutil.rmtree(abs_path)
    else:
        abs_path.unlink()
    dated_dir = abs_path.parent
    if dated_dir.exists() and not any(dated_dir.iterdir()):
        dated_dir.rmdir()
    return True


def empty_trash(username: str) -> bool:
    trash_dir = get_user_trash_dir(username)
    if not trash_dir.exists():
        return True
    for item in trash_dir.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    return True


def clean_expired_trash(username: str) -> int:
    trash_dir = get_user_trash_dir(username)
    if not trash_dir.exists() or not trash_dir.is_dir():
        return 0
    now = datetime.now()
    expire_delta = timedelta(days=TRASH_EXPIRE_DAYS)
    cleaned_count = 0
    for dated_dir in trash_dir.iterdir():
        if not dated_dir.is_dir():
            continue
        try:
            deleted_at = datetime.strptime(dated_dir.name, "%Y%m%d%H%M%S")
        except ValueError:
            deleted_at = datetime.fromtimestamp(dated_dir.stat().st_mtime)
        if now - deleted_at > expire_delta:
            shutil.rmtree(dated_dir)
            cleaned_count += 1
    return cleaned_count


def clean_all_expired_trash() -> int:
    if not FILES_BASE_DIR.exists():
        return 0
    total_cleaned = 0
    for user_dir in FILES_BASE_DIR.iterdir():
        if user_dir.is_dir():
            total_cleaned += clean_expired_trash(user_dir.name)
    return total_cleaned


def get_user_files_dir_safe(username: str) -> Path:
    user_dir = get_user_files_dir(username)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def get_abs_path(rel_path: str, username: str) -> Path:
    rel_path = rel_path.lstrip("/")
    user_files_dir = get_user_files_dir_safe(username)
    abs_path = (user_files_dir / rel_path).resolve()
    if not str(abs_path).startswith(str(user_files_dir.resolve())):
        raise ValueError("Invalid path")
    return abs_path


def get_file_info(path: Path, username: str) -> Dict:
    user_files_dir = get_user_files_dir_safe(username)
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path.relative_to(user_files_dir)),
        "isDir": path.is_dir(),
        "size": stat.st_size if path.is_file() else 0,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "extension": path.suffix.lower() if path.is_file() else "",
    }


def list_directory(rel_path: str, username: str) -> List[Dict]:
    abs_path = get_abs_path(rel_path, username)
    if not abs_path.exists() or not abs_path.is_dir():
        return []
    items = []
    for item in abs_path.iterdir():
        if item.name == TRASH_DIR_NAME:
            continue
        items.append(get_file_info(item, username))
    items.sort(key=lambda x: (not x["isDir"], x["name"].lower()))
    return items


def create_folder(rel_path: str, name: str, username: str) -> Dict:
    abs_path = get_abs_path(rel_path, username) / secure_filename(name)
    abs_path.mkdir(parents=True, exist_ok=True)
    return get_file_info(abs_path, username)


def delete_item(rel_path: str, username: str) -> bool:
    abs_path = get_abs_path(rel_path, username)
    if not abs_path.exists():
        return False
    if abs_path.is_dir():
        shutil.rmtree(abs_path)
    else:
        abs_path.unlink()
    return True


def rename_item(rel_path: str, new_name: str, username: str) -> Dict:
    abs_path = get_abs_path(rel_path, username)
    parent = abs_path.parent
    new_path = parent / secure_filename(new_name)
    abs_path.rename(new_path)
    return get_file_info(new_path, username)


def move_item(src_rel: str, dst_rel: str, username: str) -> Dict:
    src_path = get_abs_path(src_rel, username)
    dst_path = get_abs_path(dst_rel, username)
    if dst_path.is_dir():
        dst_path = dst_path / src_path.name
    shutil.move(str(src_path), str(dst_path))
    return get_file_info(dst_path, username)


def copy_item(src_rel: str, dst_rel: str, username: str) -> Dict:
    src_path = get_abs_path(src_rel, username)
    dst_path = get_abs_path(dst_rel, username)
    if dst_path.is_dir():
        dst_path = dst_path / src_path.name
    if src_path.is_dir():
        shutil.copytree(src_path, dst_path)
    else:
        shutil.copy2(src_path, dst_path)
    return get_file_info(dst_path, username)


def save_upload(rel_path: str, file_storage, username: str) -> Dict:
    abs_dir = get_abs_path(rel_path, username)
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
    return get_file_info(file_path, username)


def create_share(rel_path: str, username: str, expire_hours: Optional[int] = None, password: Optional[str] = None) -> Dict:
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
        "username": username,
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


def list_directory_tree(rel_path: str, username: str) -> List[Dict]:
    abs_path = get_abs_path(rel_path, username)
    if not abs_path.exists() or not abs_path.is_dir():
        return []
    items = []
    user_dir = get_user_files_dir_safe(username)
    for item in abs_path.iterdir():
        if item.name == TRASH_DIR_NAME:
            continue
        if item.is_dir():
            items.append({
                "name": item.name,
                "path": str(item.relative_to(user_dir)),
            })
    items.sort(key=lambda x: x["name"].lower())
    return items


def search_files(query: str, extension: Optional[str] = None, path: str = "", username: str = "") -> List[Dict]:
    abs_path = get_abs_path(path, username)
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
                results.append(get_file_info(item, username))
        except (PermissionError, OSError):
            continue
    results.sort(key=lambda x: (not x["isDir"], x["name"].lower()))
    return results


def init_chunk_upload(filename: str, total_size: int, total_chunks: int, file_md5: str, username: str) -> Dict:
    upload_id = str(uuid.uuid4())
    upload_dir = TMP_DIR / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_meta = {
        "uploadId": upload_id,
        "filename": secure_filename(filename),
        "totalSize": total_size,
        "totalChunks": total_chunks,
        "fileMD5": file_md5,
        "username": username,
        "createdAt": datetime.now().isoformat(),
        "receivedChunks": [],
    }
    meta_file = upload_dir / "meta.json"
    with open(meta_file, "w") as f:
        json.dump(upload_meta, f)
    return upload_meta


def get_upload_meta(upload_id: str) -> Optional[Dict]:
    upload_dir = TMP_DIR / upload_id
    meta_file = upload_dir / "meta.json"
    if not meta_file.exists():
        return None
    with open(meta_file, "r") as f:
        return json.load(f)


def save_chunk(upload_id: str, chunk_index: int, chunk_data, chunk_md5: str) -> Dict:
    upload_dir = TMP_DIR / upload_id
    if not upload_dir.exists():
        raise ValueError("Upload session not found")
    meta_file = upload_dir / "meta.json"
    with open(meta_file, "r") as f:
        meta = json.load(f)
    chunk_file = upload_dir / f"chunk_{chunk_index}"
    chunk_data.save(str(chunk_file))
    calculated_md5 = hashlib.md5(chunk_file.read_bytes()).hexdigest()
    if calculated_md5 != chunk_md5:
        chunk_file.unlink()
        raise ValueError(f"Chunk {chunk_index} MD5 mismatch")
    if chunk_index not in meta["receivedChunks"]:
        meta["receivedChunks"].append(chunk_index)
        meta["receivedChunks"].sort()
    with open(meta_file, "w") as f:
        json.dump(meta, f)
    return {"receivedChunks": meta["receivedChunks"], "totalChunks": meta["totalChunks"]}


def complete_chunk_upload(upload_id: str, rel_path: str, username: str) -> Dict:
    upload_dir = TMP_DIR / upload_id
    if not upload_dir.exists():
        raise ValueError("Upload session not found")
    meta_file = upload_dir / "meta.json"
    with open(meta_file, "r") as f:
        meta = json.load(f)
    if len(meta["receivedChunks"]) != meta["totalChunks"]:
        missing = [i for i in range(meta["totalChunks"]) if i not in meta["receivedChunks"]]
        raise ValueError(f"Missing chunks: {missing}")
    abs_dir = get_abs_path(rel_path, username)
    abs_dir.mkdir(parents=True, exist_ok=True)
    filename = meta["filename"]
    file_path = abs_dir / filename
    counter = 1
    while file_path.exists():
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        file_path = abs_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    md5_hash = hashlib.md5()
    with open(file_path, "wb") as outfile:
        for i in range(meta["totalChunks"]):
            chunk_file = upload_dir / f"chunk_{i}"
            chunk_data = chunk_file.read_bytes()
            md5_hash.update(chunk_data)
            outfile.write(chunk_data)
    calculated_md5 = md5_hash.hexdigest()
    if calculated_md5 != meta["fileMD5"]:
        file_path.unlink()
        raise ValueError(f"File MD5 mismatch. Expected: {meta['fileMD5']}, Got: {calculated_md5}")
    shutil.rmtree(upload_dir)
    return get_file_info(file_path, username)


def cleanup_expired_uploads(max_age_hours: int = 24) -> int:
    if not TMP_DIR.exists():
        return 0
    now = datetime.now()
    cleaned_count = 0
    for upload_dir in TMP_DIR.iterdir():
        if not upload_dir.is_dir():
            continue
        meta_file = upload_dir / "meta.json"
        try:
            if meta_file.exists():
                with open(meta_file, "r") as f:
                    meta = json.load(f)
                created_at = datetime.fromisoformat(meta["createdAt"])
                if now - created_at > timedelta(hours=max_age_hours):
                    shutil.rmtree(upload_dir)
                    cleaned_count += 1
            else:
                shutil.rmtree(upload_dir)
                cleaned_count += 1
        except Exception:
            continue
    return cleaned_count
