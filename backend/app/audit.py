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


def _count_total_lines(file_path: Path, action_type: Optional[str] = None) -> int:
    count = 0
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if action_type:
                try:
                    entry = json.loads(line)
                    if entry.get("action") != action_type:
                        continue
                except Exception:
                    continue
            count += 1
    return count


def _read_lines_reverse(
    file_path: Path,
    action_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    block_size: int = 4096,
) -> List[Dict]:
    results = []
    skipped = 0

    with open(file_path, "rb") as f:
        f.seek(0, 2)
        file_size = f.tell()

        if file_size == 0:
            return []

        buffer = b""
        position = file_size

        while position > 0 and len(results) < limit:
            read_size = min(block_size, position)
            position -= read_size
            f.seek(position)
            chunk = f.read(read_size)
            buffer = chunk + buffer

            lines = buffer.split(b"\n")
            buffer = lines[0]

            for line_bytes in reversed(lines[1:]):
                if not line_bytes:
                    continue
                try:
                    line = line_bytes.decode("utf-8").strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    if action_type and entry.get("action") != action_type:
                        continue
                    if skipped < skip:
                        skipped += 1
                        continue
                    results.append(entry)
                    if len(results) >= limit:
                        break
                except Exception:
                    continue

        if buffer and len(results) < limit:
            try:
                line = buffer.decode("utf-8").strip()
                if line:
                    entry = json.loads(line)
                    if not action_type or entry.get("action") == action_type:
                        if skipped < skip:
                            skipped += 1
                        else:
                            results.append(entry)
            except Exception:
                pass

    return results


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

    skip = (page - 1) * per_page
    items = _read_lines_reverse(audit_file, action_type, skip, per_page)
    total = _count_total_lines(audit_file, action_type)

    return {
        "items": items,
        "total": total,
        "page": page,
        "perPage": per_page,
    }
