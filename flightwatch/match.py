"""가는 편 + 오는 편 조합 및 조건 필터."""

from dataclasses import dataclass

from .dates import Trip
from .google import Leg


@dataclass(frozen=True)
class Deal:
    trip: Trip
    origin: str
    dest: str
    out: Leg
    back: Leg
    japan: bool

    @property
    def total(self) -> int:
        return self.out.price + self.back.price

    @property
    def key(self) -> str:
        return f"{self.origin}-{self.dest}-{self.trip.depart}-{self.trip.ret}"


def ok_leg(leg: Leg, max_duration: int, min_depart_hour: int = 0) -> bool:
    return leg.duration <= max_duration and leg.dep_hour >= min_depart_hour


def airline_code(leg: Leg) -> str:
    """편명 앞 2자리 (예: 7C1305 → 7C). 편명이 없으면 항공사 이름."""
    return leg.flight_no[:2] if leg.flight_no else leg.airline


def best_deal(trip: Trip, origin: str, dest: str, outs: list[Leg], backs: list[Leg],
              budget: int, max_duration: int, japan: bool, same_airline: bool = False) -> Deal | None:
    """조건에 맞는 가장 싼 왕복 조합 하나 (없으면 None)."""
    outs = [l for l in outs if ok_leg(l, max_duration, trip.min_depart_hour)]
    backs = [l for l in backs if ok_leg(l, max_duration)]
    pick_out = lambda ls: min(ls, key=lambda l: (l.price, l.dep_time))
    pick_back = lambda ls: min(ls, key=lambda l: (l.price, -int(l.dep_time.replace(":", ""))))  # 같은 값이면 늦게 오는 편

    if same_airline:
        candidates = []
        for code in {airline_code(l) for l in outs} & {airline_code(l) for l in backs}:
            candidates.append(Deal(trip, origin, dest,
                                   pick_out([l for l in outs if airline_code(l) == code]),
                                   pick_back([l for l in backs if airline_code(l) == code]), japan))
        deal = min(candidates, key=lambda d: d.total, default=None)
    else:
        deal = Deal(trip, origin, dest, pick_out(outs), pick_back(backs), japan) if outs and backs else None
    return deal if deal and deal.total <= budget else None


def sort_deals(deals: list[Deal]) -> list[Deal]:
    """일본 먼저, 그다음 가격순."""
    return sorted(deals, key=lambda d: (not d.japan, d.total, d.trip.depart))
