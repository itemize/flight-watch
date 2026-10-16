"""항공사 특가 소식 알림 (Google 뉴스 RSS).

항공사 사이트는 봇 차단·자바스크립트 렌더링이 많아서, 특가 기사를 뉴스 검색으로 모은다.
같은 행사 기사가 여러 언론사에서 나오므로 제목이 비슷한 기사는 하나로 묶는다.

사용법:
  python -m flightwatch.sales             # 새 소식 텔레그램 발송
  python -m flightwatch.sales --dry-run   # 콘솔 출력만
"""

import argparse
import html
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
import yaml

from . import notify, state as st

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
SIMILAR = 0.35  # 제목 단어 겹침 비율이 이 이상이면 같은 행사로 봄


@dataclass
class Article:
    title: str      # 언론사명 제외
    source: str
    link: str
    guid: str
    published: datetime
    airline: str


def tokens(title: str) -> set[str]:
    words = re.findall(r"[0-9A-Za-z가-힣日]+", title)
    return {w for w in words if len(w) >= 2}


def similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / min(len(ta), len(tb)) if ta and tb else 0.0


def build_url(cfg: dict) -> str:
    airlines = " OR ".join(cfg["airlines"])
    keywords = " OR ".join(cfg["keywords"])
    q = f"({airlines}) ({keywords}) when:{int(cfg.get('days', 3))}d"
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})


def is_sale(title: str, cfg: dict) -> bool:
    """항공사 이름 + 특가성 단어가 있고 제외 단어가 없는 제목."""
    has = lambda words: any(w in title for w in words)
    if not has(cfg["airlines"]) or has(cfg.get("exclude", [])):
        return False
    if has(cfg.get("strong_keywords", [])):
        return True
    return has(cfg["keywords"]) and has(cfg.get("ticket_words", []))


def parse_rss(xml: bytes, cfg: dict) -> list[Article]:
    out = []
    for it in ET.fromstring(xml).findall("./channel/item"):
        title = it.findtext("title") or ""
        source = it.findtext("source") or ""
        while source and title.endswith(f" - {source}"):
            title = title[: -len(f" - {source}")]
        if not is_sale(title, cfg):
            continue
        airline = next(a for a in cfg["airlines"] if a in title)
        try:
            published = parsedate_to_datetime(it.findtext("pubDate"))
        except (TypeError, ValueError):
            published = datetime.now(timezone.utc)
        out.append(Article(title.strip(), source, it.findtext("link") or "",
                           it.findtext("guid") or it.findtext("link") or title, published, airline))
    return sorted(out, key=lambda a: a.published, reverse=True)


def select_new(articles: list[Article], seen: dict, today: date, cooldown_days: int) -> list[Article]:
    """처음 보는 기사 중, 최근 알린 소식과 겹치지 않는 것만.

    같은 행사도 언론사마다 제목이 달라서, 알림을 보낸 항공사는 cooldown_days 동안 쉬고
    그 뒤에도 이전에 알린 제목과 비슷하면 같은 행사로 본다.
    """
    notified = [v for v in seen.values() if v.get("notified")]
    cutoff = (today - timedelta(days=cooldown_days)).isoformat()
    cooling = {n["airline"] for n in notified if n["date"] > cutoff}
    return [a for a in articles
            if a.guid not in seen and a.airline not in cooling
            and not any(n["airline"] == a.airline and similarity(n["title"], a.title) >= SIMILAR for n in notified)]


def group_by_airline(articles: list[Article]) -> list[list[Article]]:
    """항공사별로 묶고, 묶음 안에서는 제목이 비슷한 기사를 빼서 서로 다른 제목만 남김."""
    groups: dict[str, list[Article]] = {}
    for a in articles:
        g = groups.setdefault(a.airline, [])
        if not any(similarity(x.title, a.title) >= SIMILAR for x in g):
            g.append(a)
    return list(groups.values())


def remember(seen: dict, articles: list[Article], notified: list[Article], today: date) -> None:
    sent = {a.guid for a in notified}
    for a in articles:
        seen.setdefault(a.guid, {"date": today.isoformat(), "airline": a.airline, "title": a.title,
                                 "notified": a.guid in sent})


def prune(seen: dict, today: date, keep_days: int = 21) -> dict:
    cutoff = (today - timedelta(days=keep_days)).isoformat()
    return {k: v for k, v in seen.items() if v.get("date", "") >= cutoff}


def highlighted(g: list[Article], highlight: list[str]) -> bool:
    return any(h in a.title for a in g for h in highlight)


def format_group(g: list[Article], highlight: list[str], max_titles: int = 3) -> str:
    star = "⭐ " if highlighted(g, highlight) else ""
    lines = [f"{star}<b>{html.escape(g[0].airline)}</b>"]
    for a in g[:max_titles]:
        when = a.published.astimezone(KST).strftime("%m/%d")
        lines.append(f'• {when} <a href="{html.escape(a.link)}">{html.escape(a.title)}</a>')
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--state", default=str(ROOT / "state" / "sales_seen.json"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")).get("sales_news", {})
    if not cfg.get("enabled", False):
        print("sales_news 꺼짐")
        return 0
    today = datetime.now(KST).date()

    r = requests.get(build_url(cfg), timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    articles = parse_rss(r.content, cfg)

    state_path = Path(args.state)
    seen = prune(st.load(state_path), today)
    new_articles = select_new(articles, seen, today, int(cfg.get("cooldown_days", 3)))
    fresh = group_by_airline(new_articles)
    # 일본·출발 공항 관련 소식을 위로
    hl = cfg.get("highlight", [])
    fresh.sort(key=lambda g: not highlighted(g, hl))
    print(f"기사 {len(articles)}건 → 새 기사 {len(new_articles)}건 → 항공사 {len(fresh)}곳", flush=True)

    sent = False
    if fresh:
        msgs = notify.chunk([format_group(g, hl) for g in fresh], f"🎫 항공사 특가 소식 ({len(fresh)}개 항공사)")
        token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
        if args.dry_run:
            for m in msgs:
                print("-" * 40 + "\n" + m)
        elif token and chat_id:
            for m in msgs:
                notify.send(token, chat_id, m)
            sent = True
            print(f"텔레그램 {len(msgs)}개 메시지 발송")
        else:
            print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 없음 — 발송 생략")

    if not args.dry_run:
        # 못 보낸 기사는 기록하지 않아 다음 실행에 다시 시도
        unsent = [] if sent else new_articles
        remember(seen, [a for a in articles if a not in unsent], new_articles if sent else [], today)
        st.save(state_path, seen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
