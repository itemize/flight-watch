"""검색할 주말 일정 생성."""

from dataclasses import dataclass
from datetime import date, timedelta

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


@dataclass(frozen=True)
class Trip:
    name: str          # "1박2일" 등
    depart: date
    ret: date          # 항상 일요일
    min_depart_hour: int


def weekend_trips(today: date, end: date, trip_defs: list[dict]) -> list[Trip]:
    """today 이후 출발 ~ end 이전 귀국인 일정 목록 (출발일 순)."""
    trips = []
    sunday = today + timedelta(days=(6 - today.weekday()) % 7)
    while sunday <= end:
        for t in trip_defs:
            wd = WEEKDAYS[t["depart_weekday"]]
            depart = sunday - timedelta(days=(6 - wd) % 7 or 7)
            if depart >= today:
                trips.append(Trip(t["name"], depart, sunday, int(t.get("min_depart_hour", 0))))
        sunday += timedelta(days=7)
    return sorted(trips, key=lambda t: (t.depart, t.name))
