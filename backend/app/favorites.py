import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .config import FAVORITES_DIR, get_user_files_dir_safe


def ensure_favorites_dir():
    FAVORITES_DIR.mkdir(parents=True, exist_ok=True)


def _get_user_favorites_file(username: str) -> Path:
    ensure_favorites_dir()
    return FAVORITES_DIR / f"{username}.json"


def _load_favorites(username: str) -> List[Dict]:
    fav_file = _get_user_favorites_file(username)
    if not fav_file.exists():
        return []
    with open(fav_file, "r") as f:
        return json.load(f)


def _save_favorites(username: str, favorites: List[Dict]):
    fav_file = _get_user_favorites_file(username)
    with open(fav_file, "w") as f:
        json.dump(favorites, f, ensure_ascii=False, indent=2)


def add_favorite(rel_path: str, username: str) -> Dict:
    from .utils import get_abs_path, get_file_info

    abs_path = get_abs_path(rel_path, username)
    if not abs_path.exists():
        raise ValueError("File or folder not found")

    favorites = _load_favorites(username)
    for fav in favorites:
        if fav["path"] == rel_path:
            raise ValueError("Already in favorites")

    file_info = get_file_info(abs_path, username)
    favorite_item = {
        "name": file_info["name"],
        "path": file_info["path"],
        "isDir": file_info["isDir"],
        "size": file_info["size"],
        "type": file_info["extension"] if file_info["extension"] else ("folder" if file_info["isDir"] else "file"),
        "extension": file_info["extension"],
        "favoritedAt": datetime.now().isoformat(),
        "modified": file_info["modified"],
    }
    favorites.append(favorite_item)
    _save_favorites(username, favorites)
    return favorite_item


def remove_favorite(rel_path: str, username: str) -> bool:
    favorites = _load_favorites(username)
    new_favorites = [f for f in favorites if f["path"] != rel_path]
    if len(new_favorites) == len(favorites):
        raise ValueError("Not in favorites")
    _save_favorites(username, new_favorites)
    return True


def list_favorites(username: str) -> List[Dict]:
    favorites = _load_favorites(username)
    favorites.sort(key=lambda x: x.get("favoritedAt", ""), reverse=True)
    return favorites


def is_favorite(rel_path: str, username: str) -> bool:
    favorites = _load_favorites(username)
    return any(f["path"] == rel_path for f in favorites)
