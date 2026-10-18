"""검색할 주말 일정 생성."""

from dataclasses import dataclass
from datetime import date, timedelta

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


@dataclass(frozen=True)
class Trip:
    name: str          # "1박2일" 등
    depart: date
    ret: date
    min_depart_hour: int


def weekend_trips(today: date, end: date, trip_defs: list[dict]) -> list[Trip]:
    """today 이후 출발 ~ end 이전 귀국인 일정 목록 (출발일 순)."""
    trips = []
    for t in trip_defs:
        depart = today + timedelta(days=(WEEKDAYS[t["depart_weekday"]] - today.weekday()) % 7)
        nights = int(t["nights"])
        while depart + timedelta(days=nights) <= end:
            trips.append(Trip(t["name"], depart, depart + timedelta(days=nights), int(t.get("min_depart_hour", 0))))
            depart += timedelta(days=7)
    return sorted(trips, key=lambda t: (t.depart, t.ret, t.name))
