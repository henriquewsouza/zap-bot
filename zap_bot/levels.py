from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .storage import LocalMembersStore


@dataclass
class LevelService:
    store: LocalMembersStore
    temp_levels: Dict[int, Dict[str, Any]] = field(default_factory=dict)

    def get_info(self, discord_id: int) -> Dict[str, Any]:
        # temp overrides persistent level/nickname for balancing, but we still keep store metadata.
        base = self.store.get(discord_id) or {}
        tmp = self.temp_levels.get(discord_id) or {}
        return {**base, **tmp}

    def get_level(self, discord_id: int) -> int:
        info = self.get_info(discord_id)
        try:
            return int(info.get("level", 0) or 0)
        except Exception:
            return 0

    def get_nickname(self, discord_id: int, fallback: str = "Unknown") -> str:
        info = self.get_info(discord_id)
        return str(info.get("nickname") or fallback)

    def set_level(self, discord_id: int, level: int, nickname: Optional[str] = None) -> None:
        patch: Dict[str, Any] = {"level": int(level)}
        if nickname:
            patch["nickname"] = nickname
        self.store.upsert(discord_id, patch, persist=True)

    def add_temp(self, discord_id: int, level: int, nickname: Optional[str] = None) -> None:
        patch: Dict[str, Any] = {"level": int(level)}
        if nickname:
            patch["nickname"] = nickname
        self.temp_levels[int(discord_id)] = patch


