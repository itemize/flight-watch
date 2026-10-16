# flight-watch ✈️

주말 가족여행 항공권을 Google 항공편에서 4시간마다 찾아보고, 조건에 맞는 게 나오면 텔레그램으로 알려줍니다.

## 조건 (config.yaml)
- 출발: 인천(ICN), 청주(CJJ)
- 1박2일: 토요일 출국 → 일요일 귀국
- 2박3일: 금요일 18시 이후 출국 → 일요일 귀국
- 성인 2 + 어린이 1, **3명 왕복 합계 100만 원 이하**
- 가는 편·오는 편 같은 항공사 (`same_airline: false`로 끄면 항공사 섞어서 최저가 조합)
- 직항, 편도 4시간 이내 / 일본 우선 (대만·홍콩·마카오·중국 일부 포함)
- 2026-12-31까지 (지난 날짜는 자동 제외, 이후엔 검색 안 함)

가는 편과 오는 편을 편도로 각각 검색해서 가장 싼 조합을 합산합니다. 노선·주말·일정별로 가장 싼 조합 하나만 알리고, 한 번 알린 건 **5% 이상 더 싸졌을 때만** 다시 알립니다 (`state/notified.json`).

## 항공사 특가 소식
같은 실행 때 Google 뉴스에서 국내외 항공사(제주항공·진에어·트리니티·에어서울·에어부산·이스타·에어로케이·피치 등)의 특가·세일 기사를 찾아 텔레그램으로 보냅니다.
- 항공사 사이트는 봇 차단이 많아서 뉴스 기사로 대신 찾습니다. 특가 공지 후 기사가 나오기까지 보통 반나절~하루 걸립니다.
- 같은 행사 기사는 항공사별로 묶어서 한 번만 보내고, 한 항공사 소식을 보낸 뒤 3일(`cooldown_days`)은 그 항공사 기사를 건너뜁니다.
- 일본·청주·인천이 제목에 있으면 ⭐ 표시와 함께 위쪽에 나옵니다.
- `config.yaml`의 `sales_news`에서 항공사·키워드·제외어를 바꾸거나 `enabled: false`로 끌 수 있습니다.
- 기록: `state/sales_seen.json`

## 설정 방법

### 1. 텔레그램 봇 만들기
1. 텔레그램에서 **@BotFather** → `/newbot` → 이름 정하기 → **토큰** 받기
2. 새 봇과 대화를 열고 아무 메시지나 보내기
3. 브라우저에서 `https://api.telegram.org/bot<토큰>/getUpdates` 열기 → `"chat":{"id":123456789` 의 숫자가 **chat_id**

### 2. GitHub 시크릿 등록
저장소 → Settings → Secrets and variables → Actions → New repository secret
- `TELEGRAM_BOT_TOKEN` : 봇 토큰
- `TELEGRAM_CHAT_ID` : chat_id

### 3. 테스트 실행
Actions 탭 → **항공권 검색** → Run workflow. `budget`에 `3000000`처럼 큰 값을 넣으면 알림이 오는지 바로 확인할 수 있습니다.
(테스트로 보낸 항목도 기록되므로, 테스트 후 `state/notified.json`을 `{}`로 되돌리면 깨끗하게 시작합니다.)

이후에는 4시간마다 자동 실행됩니다 (KST 1·5·9·13·17·21시 무렵, GitHub 사정으로 몇 분~수십 분 늦을 수 있음).

## 조건 바꾸기
`config.yaml`만 고치면 됩니다: 예산, 인원, 목적지, 금요일 출발 시각, 검색 종료일 등.
한 번 검색에 노선 수 × 주말 수만큼 요청이 가므로(현재 약 800건, 10분 안팎), 차단되면 `shards: 2`로 나눠 검색하세요.

## 로컬 실행
```bash
pip install -r requirements.txt
python -m flightwatch.main --dry-run --dest KIX --limit-weekends 2
python -m flightwatch.sales --dry-run
pytest
```

## 참고
- 비공식 라이브러리([fast-flights](https://github.com/AWeirdDev/fast-flights))로 Google 항공편을 읽기 때문에 Google 쪽이 바뀌거나 차단되면 실패할 수 있습니다. 조회가 절반 이상 실패하면 텔레그램으로 경고를 보냅니다.
- 가격은 Google 항공편이 보여주는 3인 합계(원화)이며, 편도 2장 합산이라 대형 항공사 왕복 운임보다 약간 높게 나올 수 있습니다.
