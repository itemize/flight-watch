"""텔레그램 알림."""

import html

import requests

from .match import Deal

WEEKDAY_KO = "월화수목금토일"
MAX_LEN = 3800  # 텔레그램 한도 4096자


def _d(day) -> str:
    return f"{day.month}/{day.day}({WEEKDAY_KO[day.weekday()]})"


def format_deal(d: Deal, city: str, origin_name: str, url: str, prev_total: int | None) -> str:
    flag = "🇯🇵 " if d.japan else ""
    drop = f" (⬇ {prev_total:,}원에서)" if prev_total else ""
    return (
        f"{flag}<b>{html.escape(origin_name)} → {html.escape(city)}</b> · {d.trip.name}\n"
        f"💰 <b>{d.total:,}원</b> (3인 왕복){drop}\n"
        f"🛫 {_d(d.trip.depart)} {d.out.dep_time}→{d.out.arr_time} {html.escape(d.out.airline)} {d.out.flight_no}"
        f" · {d.out.price:,}원\n"
        f"🛬 {_d(d.trip.ret)} {d.back.dep_time}→{d.back.arr_time} {html.escape(d.back.airline)} {d.back.flight_no}"
        f" · {d.back.price:,}원\n"
        f'<a href="{html.escape(url)}">Google 항공편에서 보기</a>'
    )


def chunk(blocks: list[str], header: str) -> list[str]:
    msgs, cur = [], header
    for b in blocks:
        if len(cur) + len(b) + 2 > MAX_LEN:
            msgs.append(cur)
            cur = ""
        cur = (cur + "\n\n" + b) if cur else b
    if cur:
        msgs.append(cur)
    return msgs


def send(token: str, chat_id: str, text: str) -> None:
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=30,
    )
    r.raise_for_status()
