import json
import threading
import queue
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict

from .config import DATA_DIR

AUDIT_DIR = DATA_DIR / "audit"
AUDIT_QUEUE = queue.Queue()
AUDIT_WORKER = None

AUDIT_TYPES = {
    "upload",
    "delete",
    "rename",
    "move",
    "copy",
    "share",
    "create_folder",
    "restore_trash",
    "permanent_delete",
    "empty_trash",
}


def ensure_audit_dir():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def get_audit_file_path(username: str) -> Path:
    return AUDIT_DIR / f"{username}.jsonl"


def audit_worker():
    while True:
        try:
            entry = AUDIT_QUEUE.get()
            if entry is None:
                break
            username = entry.get("username", "")
            if not username:
                continue
            try:
                ensure_audit_dir()
                audit_file = get_audit_file_path(username)
                with open(audit_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception:
                pass
        except Exception:
            pass


def start_audit_worker():
    global AUDIT_WORKER
    if AUDIT_WORKER is None or not AUDIT_WORKER.is_alive():
        AUDIT_WORKER = threading.Thread(target=audit_worker, daemon=True)
        AUDIT_WORKER.start()


def log_audit(
    username: str,
    action_type: str,
    target_path: str,
    extra: Optional[Dict] = None,
):
    if action_type not in AUDIT_TYPES:
        return
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "username": username,
        "action": action_type,
        "path": target_path,
    }
    if extra:
        entry.update(extra)
    AUDIT_QUEUE.put(entry)


def read_audit_logs(
    username: str,
    action_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> Dict:
    ensure_audit_dir()
    audit_file = get_audit_file_path(username)
    if not audit_file.exists():
        return {"items": [], "total": 0, "page": page, "perPage": per_page}

    all_lines = []
    with open(audit_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if action_type and entry.get("action") != action_type:
                    continue
                all_lines.append(entry)
            except Exception:
                continue

    all_lines.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    total = len(all_lines)
    start = (page - 1) * per_page
    end = start + per_page
    items = all_lines[start:end]

    return {
        "items": items,
        "total": total,
        "page": page,
        "perPage": per_page,
    }
