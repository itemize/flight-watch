from datetime import date, datetime, timezone

from flightwatch.sales import Article, group_by_airline, is_sale, parse_rss, remember, select_new

CFG = {
    "airlines": ["제주항공", "에어부산", "대한항공"],
    "keywords": ["특가", "할인", "프로모션"],
    "strong_keywords": ["특가"],
    "ticket_words": ["항공권", "국제선"],
    "exclude": ["멤버십"],
}
TODAY = date(2026, 10, 17)


def art(title, airline="에어부산", guid=None):
    return Article(title, "언론사", "https://x", guid or title, datetime(2026, 10, 16, tzinfo=timezone.utc), airline)


def test_is_sale():
    assert is_sale("에어부산, 국제선 특가 프로모션", CFG)
    assert is_sale("제주항공, 동계 항공권 최대 50% 할인", CFG)
    assert not is_sale("대한항공·괌관광청 공동 프로모션", CFG)      # 항공권 단어 없음
    assert not is_sale("제주항공 J멤버십 특가", CFG)                # 제외 단어
    assert not is_sale("트리니티 국제선 특가", CFG)                 # 목록에 없는 항공사


def test_parse_rss_strips_source():
    xml = """<rss><channel>
    <item><title>에어부산, 국제선 특가 - 뉴스1 - 뉴스1</title><link>L1</link><guid>G1</guid>
      <pubDate>Tue, 13 Oct 2026 01:00:00 GMT</pubDate><source url="x">뉴스1</source></item>
    <item><title>제주항공 멤버십 특가 - A</title><link>L2</link><guid>G2</guid><source url="x">A</source></item>
    </channel></rss>""".encode()
    items = parse_rss(xml, CFG)
    assert [(a.title, a.airline, a.guid) for a in items] == [("에어부산, 국제선 특가", "에어부산", "G1")]


def test_group_by_airline_drops_similar_titles():
    a = [art("에어부산, 연말 국제선 특가 프로모션 진행"), art("에어부산 연말 국제선 특가 프로모션"),
         art("에어부산, 일본 노선 땡처리"), art("제주항공 국제선 특가", "제주항공")]
    groups = group_by_airline(a)
    assert [[x.title for x in g] for g in groups] == [
        ["에어부산, 연말 국제선 특가 프로모션 진행", "에어부산, 일본 노선 땡처리"], ["제주항공 국제선 특가"]]


def test_select_new_dedup_and_cooldown():
    seen = {}
    first = [art("에어부산, 연말 국제선 특가 프로모션")]
    assert select_new(first, seen, TODAY, 3) == first
    remember(seen, first, first, TODAY)
    # 같은 기사, 같은 항공사 쿨다운 중인 다른 기사 → 제외
    assert select_new(first + [art("에어부산 다른 행사 특가", guid="g2")], seen, TODAY, 3) == []
    # 쿨다운 지나도 비슷한 제목이면 제외, 다른 행사는 통과
    later = date(2026, 10, 25)
    other = art("에어부산, 신규 노선 취항 기념 할인", guid="g3")
    assert select_new([art("에어부산 연말 국제선 특가 프로모션 시작", guid="g4"), other], seen, later, 3) == [other]
