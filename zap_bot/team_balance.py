from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Callable, Iterable, List, Sequence, Tuple, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Partition:
    diff: int
    team1: Tuple[T, ...]
    team2: Tuple[T, ...]


def build_team_message(
    team1: Sequence,
    team2: Sequence,
    get_level: Callable[[object], int],
    get_mention: Callable[[object], str],
    get_name: Callable[[object], str] | None = None,
) -> str:
    """
    Format a Discord message for two teams.
    """
    def lvl(m) -> int:
        try:
            return int(get_level(m))
        except Exception:
            return 0

    sorted_team1 = sorted(team1, key=lvl, reverse=True)
    sorted_team2 = sorted(team2, key=lvl, reverse=True)

    total_team1 = sum(lvl(m) for m in sorted_team1)
    total_team2 = sum(lvl(m) for m in sorted_team2)

    def line(m) -> str:
        mention = get_mention(m)
        name = f" ({get_name(m)})" if get_name else ""
        return f"{mention}{name} (Level: {lvl(m)})"

    team1_text = "\n".join(line(m) for m in sorted_team1)
    team2_text = "\n".join(line(m) for m in sorted_team2)

    return (
        f"**Team 1:**\n{team1_text}\n\n"
        f"**Team 2:**\n{team2_text}\n\n"
        f"**Total Skill:** {total_team1} vs {total_team2}\n"
        f"**Difference:** {abs(total_team1 - total_team2)}"
    )


def generate_partitions(
    members: Sequence[T],
    get_level: Callable[[T], int],
) -> List[Partition[T]]:
    """
    Generate all partitions and return sorted by diff ascending.
    """
    partitions: List[Partition[T]] = []
    n = len(members)
    if n < 2:
        return partitions
    team1_size = n // 2
    for team1 in itertools.combinations(members, team1_size):
        team2 = tuple(m for m in members if m not in team1)
        total1 = sum(int(get_level(m)) for m in team1)
        total2 = sum(int(get_level(m)) for m in team2)
        partitions.append(Partition(diff=abs(total1 - total2), team1=tuple(team1), team2=team2))
    partitions.sort(key=lambda p: p.diff)
    return partitions


