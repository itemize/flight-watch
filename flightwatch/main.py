"""주말 항공권 검색 → 조건 맞으면 텔레그램 알림.

사용법:
  python -m flightwatch.main               # 검색 + 알림
  python -m flightwatch.main --dry-run     # 알림 대신 콘솔 출력, 기록 저장 안 함
  python -m flightwatch.main --dry-run --dest KIX --limit-weekends 2
"""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import notify, state as st
from .dates import weekend_trips
from .google import Leg, round_trip_url, search_one_way
from .match import best_deal, ok_leg, sort_deals

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))


def log(*args):
    print(*args, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--state", default=str(ROOT / "state" / "notified.json"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--origin", action="append", help="특정 출발지만 (반복 가능)")
    ap.add_argument("--dest", action="append", help="특정 목적지만 (반복 가능)")
    ap.add_argument("--limit-weekends", type=int, help="가까운 주말 N개만")
    ap.add_argument("--budget", type=int, help="예산 덮어쓰기 (테스트용)")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    today = datetime.now(KST).date()
    end = cfg["end_date"] if isinstance(cfg["end_date"], date) else date.fromisoformat(str(cfg["end_date"]))
    budget = args.budget or int(cfg["budget_krw"])
    max_dur = int(cfg["max_duration_minutes"])
    pax = cfg["passengers"]
    delay = float(cfg.get("request_delay_sec", 1.0))
    airports = cfg["airports"]

    trips = weekend_trips(today, end, cfg["trips"])
    if args.limit_weekends:
        sundays = sorted({t.ret for t in trips})[: args.limit_weekends]
        trips = [t for t in trips if t.ret in sundays]
    if not trips:
        log(f"검색할 일정 없음 (오늘 {today}, 종료 {end}) — 종료")
        return 0

    routes = [(o, d) for o, oc in cfg["origins"].items() if not args.origin or o in args.origin
              for d in oc["destinations"] if not args.dest or d in args.dest]
    shards = int(cfg.get("shards", 1))
    if shards > 1:
        idx = int(time.time() // (4 * 3600)) % shards
        routes = [r for i, r in enumerate(routes) if i % shards == idx]
        log(f"샤드 {idx + 1}/{shards}")
    log(f"오늘 {today} | 일정 {len(trips)}개 | 노선 {len(routes)}개 | 예산 {budget:,}원")

    pool = ThreadPoolExecutor(max_workers=int(cfg.get("workers", 3)))
    stats = {"ok": 0, "fail": 0}
    errors: list[str] = []

    def run(jobs: dict) -> dict:
        futures = {k: pool.submit(search_one_way, *k[:3], pax, k[3], delay=delay) for k in jobs}
        out = {}
        for k, f in futures.items():
            try:
                out[k] = f.result()
                stats["ok"] += 1
            except Exception as e:
                out[k] = []
                stats["fail"] += 1
                errors.append(str(e))
        return out

    # 1단계: 가는 편 (출발지→목적지)
    t0 = time.time()
    out_jobs = {(o, d, t.depart.isoformat(), t.min_depart_hour) for o, d in routes for t in trips}
    outs = run(out_jobs)
    log(f"가는 편 {len(out_jobs)}건 조회 ({time.time() - t0:.0f}초)")

    # 2단계: 오는 편 — 가는 편 최저가가 예산 안에 드는 경우만
    def cheapest_out(o, d, t) -> int | None:
        legs = [l for l in outs.get((o, d, t.depart.isoformat(), t.min_depart_hour), [])
                if ok_leg(l, max_dur, t.min_depart_hour)]
        return min((l.price for l in legs), default=None)

    need_back = {(d, o, t.ret.isoformat(), 0) for o, d in routes for t in trips
                 if (p := cheapest_out(o, d, t)) is not None and p < budget}
    t0 = time.time()
    backs = run(need_back)
    log(f"오는 편 {len(need_back)}건 조회 ({time.time() - t0:.0f}초) | 실패 {stats['fail']}건")
    pool.shutdown()

    deals = []
    for o, d in routes:
        for t in trips:
            out_legs: list[Leg] = outs.get((o, d, t.depart.isoformat(), t.min_depart_hour), [])
            back_legs: list[Leg] = backs.get((d, o, t.ret.isoformat(), 0), [])
            deal = best_deal(t, o, d, out_legs, back_legs, budget, max_dur,
                             japan=bool(airports.get(d, {}).get("japan")))
            if deal:
                deals.append(deal)
    deals = sort_deals(deals)
    log(f"조건 충족 {len(deals)}건")

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    total_q = stats["ok"] + stats["fail"]

    # 조회가 대부분 실패하면 알림 (차단·구조 변경 감지)
    if total_q and stats["fail"] / total_q > 0.5:
        msg = (f"⚠️ 항공권 검색 실패 {stats['fail']}/{total_q}건\n"
               f"예: {errors[0][:300] if errors else '-'}")
        log(msg)
        if not args.dry_run and token and chat_id:
            notify.send(token, chat_id, msg)

    state_path = Path(args.state)
    state = st.prune(st.load(state_path), today)
    fresh = st.select_new(deals, state, float(cfg.get("renotify_drop_ratio", 0.05)))
    log(f"새 알림 대상 {len(fresh)}건")

    if fresh:
        blocks = [
            notify.format_deal(
                d,
                city=airports.get(d.dest, {}).get("city", d.dest),
                origin_name=cfg["origins"][d.origin].get("name", d.origin),
                url=round_trip_url(d.origin, d.dest, d.trip.depart.isoformat(), d.trip.ret.isoformat(), pax),
                prev_total=state.get(d.key, {}).get("total"),
            )
            for d in fresh
        ]
        msgs = notify.chunk(blocks, f"✈️ 조건 맞는 항공권 {len(fresh)}건 (예산 {budget:,}원 이하)")
        if args.dry_run:
            for m in msgs:
                log("-" * 40 + "\n" + m)
        elif token and chat_id:
            for m in msgs:
                notify.send(token, chat_id, m)
            log(f"텔레그램 {len(msgs)}개 메시지 발송")
            st.record(state, fresh)  # 보낸 것만 기록
        else:
            log("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 없음 — 발송 생략")

    if not args.dry_run:
        st.save(state_path, state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
