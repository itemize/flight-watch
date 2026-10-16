import json
from datetime import date

from flightwatch.dates import Trip, weekend_trips
from flightwatch.google import Leg, parse_html
from flightwatch.match import best_deal, sort_deals
from flightwatch import state as st

TRIPS = [
    {"name": "1박2일", "depart_weekday": "sat", "min_depart_hour": 0},
    {"name": "2박3일", "depart_weekday": "fri", "min_depart_hour": 18},
]


def leg(price, dep="10:00", dur=110, date_="2026-11-21", fno="7C1"):
    return Leg("ICN", "KIX", date_, dep, "12:00", dur, "제주항공", fno, price)


def test_weekend_trips_range():
    trips = weekend_trips(date(2026, 10, 17), date(2026, 12, 31), TRIPS)
    assert trips[0] == Trip("1박2일", date(2026, 10, 17), date(2026, 10, 18), 0)
    assert all(t.ret.weekday() == 6 for t in trips)
    assert trips[-1].ret == date(2026, 12, 27)
    fri = [t for t in trips if t.name == "2박3일"]
    assert fri[0].depart == date(2026, 10, 23) and fri[0].min_depart_hour == 18
    assert len(fri) == 10 and len(trips) == 21


def test_weekend_trips_after_end():
    assert weekend_trips(date(2027, 1, 1), date(2026, 12, 31), TRIPS) == []


def test_best_deal_filters():
    t = Trip("2박3일", date(2026, 11, 20), date(2026, 11, 22), 18)
    outs = [leg(100_000, dep="09:00"), leg(300_000, dep="19:00"), leg(200_000, dep="20:00", dur=300)]
    backs = [leg(400_000), leg(500_000)]
    d = best_deal(t, "ICN", "KIX", outs, backs, 1_000_000, 240, True)
    assert d.out.price == 300_000 and d.back.price == 400_000 and d.total == 700_000
    assert best_deal(t, "ICN", "KIX", outs, backs, 600_000, 240, True) is None


def test_sort_japan_first():
    t = Trip("1박2일", date(2026, 11, 21), date(2026, 11, 22), 0)
    jp = best_deal(t, "ICN", "KIX", [leg(400_000)], [leg(400_000)], 10**7, 240, True)
    tw = best_deal(t, "ICN", "TPE", [leg(100_000)], [leg(100_000)], 10**7, 240, False)
    assert sort_deals([tw, jp]) == [jp, tw]


def test_state_dedup():
    t = Trip("1박2일", date(2026, 11, 21), date(2026, 11, 22), 0)
    d = best_deal(t, "ICN", "KIX", [leg(400_000)], [leg(400_000)], 10**7, 240, True)
    state = {}
    assert st.select_new([d], state, 0.05) == [d]
    st.record(state, [d])
    assert st.select_new([d], state, 0.05) == []
    cheaper = best_deal(t, "ICN", "KIX", [leg(350_000)], [leg(400_000)], 10**7, 240, True)
    assert st.select_new([cheaper], state, 0.05) == [cheaper]
    assert st.prune(state, date(2026, 11, 22)) == {}


def _segment(origin, dest, dep, dur, day, fno):
    s = [None] * 23
    s[3], s[6], s[8], s[10], s[11] = origin, dest, dep, [12, 0], dur
    s[20], s[21], s[22] = day, day, [fno[:2], fno[2:], None, "항공사"]
    return s


def test_parse_html_both_sections_and_missing_price():
    day = [2026, 11, 21]
    best = [[["7C", ["제주항공"], [_segment("ICN", "KIX", [9, 5], 110, day, "7C1301")]], [[None, 500000], "x"]],
            [["ZE", ["이스타"], [_segment("ICN", "KIX", [10], 110, day, "ZE611")]], [[], "x"]]]
    other = [[["MM", ["피치"], [_segment("ICN", "KIX", [None, 30], 105, day, "MM705")]], [[None, 450000], "x"]],
             [["OZ", ["아시아나"], [_segment("ICN", "NRT", [8], 60, day, "OZ1"),
                                    _segment("NRT", "KIX", [11], 60, day, "OZ2")]], [[None, 1], "x"]]]
    payload = [None, None, [best], [other]]
    html = f'<script class="ds:1">AF_initDataCallback({{key: "ds:1", data:{json.dumps(payload)}, sideChannel: {{}}}});</script>'
    legs = parse_html(html)
    assert [(l.flight_no, l.price, l.dep_time) for l in legs] == [("MM705", 450000, "00:30"), ("7C1301", 500000, "09:05")]
