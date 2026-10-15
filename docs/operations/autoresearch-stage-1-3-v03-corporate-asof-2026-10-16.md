# Quant Autoresearch V03 / 1-3 — QQQ 기업행동·조정가격 as-of 검증

기준: 2026-10-15 UTC / 2026-10-16 KST. 연구 브랜치 `feat/v03-qqq-corporate-asof-gates-20261016`, 코드 `be563c4` origin Push 완료. **운영 MCP da2331d 유지, 재배포·주문 없음**.

## 보존된 진짜 Moon 데이터의 독립적인 재생 결과

- 가격: Tiingo QQQ 원시 가격 개발 데이터(2020-01-02~2025-12-31, 1,508 거래일, 당시 시점에 제공된 빈티지가 아니라 2026-10-10 최신 조회본).
- 배당: Nasdaq `state/indicator-engine/source-captures/QQQ_dividends_2020-2025_20261014T061404Z.raw.json`와 SHA/manifest 원본, 현 시점에 보관된 25개의 배당락·기준·지급·선언일(2026-10-14 수집). 원본 SHA `c7bca224b189d4999931f9fe22d101758c034353cfccdc4ec45b76fcf1348c77`.
- 기존 SHA 핀을 가진 발행사 기준 25건과 1주당 배당 금액 **25/25 일치**. **24건은 선언일(`declarationDate`) 누락**, 나머지 1건도 날짜만 있을 뿐 독립 발행 타임스탬프를 입증하지 않음.
- 실제 과거 결정 시점 예시 `2025-03-24T20:00:00Z`: 그 시점 기준 과거 배당락일 22건, 지급일이 도래한 21건. 배당락을 했어도 아직 지급되지 않은 1건을 당시 현금으로 인식하지 않는 게이트 확인. 그러나 현재 이용한 가격 조회일 `2026-10-10`, 배당 수집일 `2026-10-14`는 과거 결정 시점보다 **뒤**라 미래정보 사용을 차단함.
- 1차 발행사/거래소의 완전한 split catalog·공식 당시 공개시각 증빙 **미확보**. 2000년 분할을 표기한 기존 2차 출처로 2020~2025 기간의 분할 '없음'을 입증하지 않음.
- 이전 2026-10-15 문서에서 매칭한 25건 Tiingo adjusted/raw 조정계수 비교는 당시의 관측 기록으로 보존. **현재 개발 Worktree에는 `QQQ_2020-01-02_2025-12-31_total_return_adjusted.parquet`가 없어** 이번 단계에서 해당 조정계수·분할 잔차를 독립 재계산하지 못함. 불완전한 원본을 대신 만들어 가격 수정이 없다고 주장하지 않음.
- 실제 증거 `docs/operations/evidence/quant-validation-20261016/v03-qqq-corporate-asof-real.json`, 결정 시점별 결과 해시 `fd205916c0bd4dd5afbadabff64d3e2bb78dd8b4382fa6284ecd511dbbfb902b`. `historical_point_in_time_verified=false`, `asof_dividend_signal_approved=false`, `broker_executable=false`.

## V03 신규 기능

- `research/indicator_engine/corporate_asof_gate.py`: 보존 원본 Nasdaq 배당·Tiingo 비조정 일봉 및 SHA 핀 Invesco cash·2차 split ref를 불변 읽기. 날짜 비교를 실제 원본 획득 시각/decision UTC/지급일로 분리. 선언일이 나와도 발표 시각 증빙으로 인정하지 않음.
- 선택적 adjusted 가격을 주면 기존 issuer 배당 계수 비교와 split residual 진단 함수를 다시 사용하되 **별도 as-of 승인 없이 연구용**. 없으면 `latest_adjusted_pair_available=false` 와 blocker 명시. 바 이외 소스·무단 as_of label·SEALED_OOS·다른 벤더/시계열/서명·표시 데이터 변조 거부.
- 로컬 CLI `audit-qqq-corporate-asof --raw-parquet <file> --dividend-raw <file> --dividend-manifest <file> --decision-at ISO-UTC`, 선택 `--adjusted-parquet`. 원본 덮어쓰기·실거래·OAuth 변경 불가.
- V03 신규 8 tests PASS, 기존 관련(발행사 배당·분할 잔차·가격 수정·빈티지 타임라인) 포함 총 **40 PASS**, 변경 경로 Ruff/Mypy PASS. 전체 저장소 통합 테스트는 D08 이후 수정으로 별도 미실행.

## 남은 수락 기준

- 실제 과거 발행자/공급자 발표 및 투자자 수신 시각 증빙. Nasdaq 현시점 배당락일은 과거 시점 가용성 자료가 아님(V02 BLOCKED_EXTERNAL_EVIDENCE).
- 1차 split/기업행동 전체 원본과 당시 사전공개 이력, 조정 전·후 가격 빈티지의 별도 보존 및 수정 시각 검증(V01 2일째 수집도 미달).
- V04에서는 **OOS 봉인·전략 선택 잠금/접근권한 경계 설계 테스트**만 먼저 수행 가능. V01~V03 PIT 미확보인 상태에서 수익률 검증용으로 실제 봉인 OOS 데이터를 열거나 GO 판정하지 않음.

**V03 상태 BLOCKED_EXTERNAL_ASOF. 다음 V04 / 4-2(OOS 경계·동결 검증).**
