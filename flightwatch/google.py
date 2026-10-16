"""Google Flights 편도 직항 검색.

fast-flights의 쿼리 생성/요청만 쓰고, 파싱은 직접 한다.
(라이브러리 파서는 '최적 항공편' 섹션을 빠뜨리고, 가격이 없는 항공편에서 오류가 남)
"""

import json
import random
import time
from dataclasses import dataclass

from fast_flights import FlightQuery, Passengers, create_query, fetch_flights_html
from selectolax.lexbor import LexborHTMLParser


@dataclass(frozen=True)
class Leg:
    origin: str
    dest: str
    date: str          # YYYY-MM-DD
    dep_time: str      # HH:MM
    arr_time: str      # HH:MM
    duration: int      # 분
    airline: str
    flight_no: str     # 예: 7C1305
    price: int         # 전체 인원 합산, KRW

    @property
    def dep_hour(self) -> int:
        return int(self.dep_time[:2])


class FetchError(Exception):
    pass


def _hhmm(value) -> str:
    padded = [*(value or []), None, None]
    return f"{padded[0] or 0:02d}:{padded[1] or 0:02d}"


def build_query(legs: list[tuple[str, str, str]], passengers: dict, trip: str = "one-way",
                min_depart_hour: int | None = None):
    flights = [
        FlightQuery(date=d, from_airport=o, to_airport=t, max_stops=0,
                    earliest_departure_hour=(min_depart_hour if i == 0 else None))
        for i, (o, t, d) in enumerate(legs)
    ]
    return create_query(
        flights=flights,
        trip=trip,
        passengers=Passengers(adults=passengers.get("adults", 1), children=passengers.get("children", 0)),
        currency="KRW",
        language="ko",
    )


def parse_html(html: str) -> list[Leg]:
    script = LexborHTMLParser(html).css_first(r"script.ds\:1")
    if script is None:
        raise FetchError("결과 데이터가 없음 (차단 또는 페이지 구조 변경)")
    js = script.text()
    data = js.split("data:", 1)[1].rsplit(",", 1)[0]
    if data.endswith("errorHasStatus: true"):
        return []
    payload = json.loads(data)

    legs = []
    for section in (2, 3):  # 2: 최적 항공편, 3: 기타 항공편
        block = payload[section] if len(payload) > section else None
        if not block or not block[0]:
            continue
        for item in block[0]:
            try:
                flight, price_info = item[0], item[1]
                segments = flight[2]
                if len(segments) != 1:
                    continue  # 직항만
                price = price_info[0][1] if price_info and price_info[0] else None
                if not price:
                    continue
                s = segments[0]
                fno = s[22] if len(s) > 22 and s[22] else None
                legs.append(Leg(
                    origin=s[3],
                    dest=s[6],
                    date="%04d-%02d-%02d" % tuple(s[20]),
                    dep_time=_hhmm(s[8]),
                    arr_time=_hhmm(s[10]),
                    duration=int(s[11]),
                    airline=(fno[3] if fno and len(fno) > 3 and fno[3] else ", ".join(flight[1])),
                    flight_no=(f"{fno[0]}{fno[1]}" if fno else ""),
                    price=int(price),
                ))
            except (IndexError, TypeError, ValueError):
                continue

    # 같은 편이 두 섹션에 겹치면 싼 것 하나만
    best: dict[tuple, Leg] = {}
    for leg in legs:
        key = (leg.flight_no or leg.airline, leg.date, leg.dep_time)
        if key not in best or leg.price < best[key].price:
            best[key] = leg
    return sorted(best.values(), key=lambda l: l.price)


def search_one_way(origin: str, dest: str, date: str, passengers: dict,
                   min_depart_hour: int | None = None, retries: int = 3,
                   delay: float = 1.0) -> list[Leg]:
    q = build_query([(origin, dest, date)], passengers, min_depart_hour=min_depart_hour or None)
    last = None
    for attempt in range(retries):
        try:
            time.sleep(delay * random.uniform(0.5, 1.5))
            return parse_html(fetch_flights_html(q))
        except Exception as e:  # 네트워크 오류, 차단, 파싱 오류
            last = e
            time.sleep(2 ** attempt * 2)
    raise FetchError(f"{origin}->{dest} {date}: {last}")


def round_trip_url(origin: str, dest: str, depart: str, ret: str, passengers: dict) -> str:
    q = build_query([(origin, dest, depart), (dest, origin, ret)], passengers, trip="round-trip")
    return q.url()
