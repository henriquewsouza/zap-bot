import json
import logging
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


class LocalMembersStore:
    """
    Local persistence for members/levels, backed by `members.json`.

    File format matches the existing repo file: { "<discord_id>": { ...fields... } }
    """

    def __init__(self, path: str = "members.json"):
        self.path = Path(path)
        self._lock = RLock()
        self._data: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            if not self.path.exists():
                self._data = {}
                return self._data
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                log.exception("Failed to read %s; using empty store.", self.path)
                self._data = {}
            return self._data

    def save(self) -> None:
        with self._lock:
            self.path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    def all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return dict(self._data)

    def get(self, discord_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._data.get(str(discord_id))

    def upsert(self, discord_id: int, patch: Dict[str, Any], persist: bool = True) -> Dict[str, Any]:
        with self._lock:
            cur = self._data.get(str(discord_id), {})
            nxt = {**cur, **patch}
            self._data[str(discord_id)] = nxt
            if persist:
                self.save()
            return nxt


