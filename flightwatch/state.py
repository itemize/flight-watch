"""이미 알린 항공편 기록 (중복 알림 방지)."""

import json
from datetime import date
from pathlib import Path

from .match import Deal


def load(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def prune(state: dict, today: date) -> dict:
    """출발일이 지난 기록 삭제."""
    return {k: v for k, v in state.items() if v.get("depart", "9999") >= today.isoformat()}


def select_new(deals: list[Deal], state: dict, drop_ratio: float) -> list[Deal]:
    """처음 보는 항공편이거나, 이전 알림보다 drop_ratio 이상 싸진 것만."""
    fresh = []
    for d in deals:
        prev = state.get(d.key)
        if prev is None or d.total <= prev["total"] * (1 - drop_ratio):
            fresh.append(d)
    return fresh


def record(state: dict, deals: list[Deal]) -> None:
    for d in deals:
        state[d.key] = {"total": d.total, "depart": d.trip.depart.isoformat(),
                        "flights": f"{d.out.flight_no}/{d.back.flight_no}"}
