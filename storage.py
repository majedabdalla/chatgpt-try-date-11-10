
"""storage.py - atomic JSON storage helpers"""
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
import os
import threading

BASE = Path(__file__).parent
DATA_DIR = BASE / 'data'
DATA_DIR.mkdir(exist_ok=True)

USER_FILE = DATA_DIR / 'user_data.json'
ROOMS_FILE = DATA_DIR / 'rooms.json'

_lock = threading.Lock()

def _atomic_write(path: Path, data):
    tmp = None
    with _lock:
        tmp = NamedTemporaryFile('w', delete=False, dir=str(path.parent), encoding='utf-8')
        try:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()
        os.replace(tmp.name, path)

def load_json(path: Path, default=None):
    if default is None:
        default = {}
    try:
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        return default
    return default

def save_users(data: dict):
    _atomic_write(USER_FILE, data)

def save_rooms(data: dict):
    _atomic_write(ROOMS_FILE, data)

def load_users():
    return load_json(USER_FILE, {})

def load_rooms():
    return load_json(ROOMS_FILE, {})
