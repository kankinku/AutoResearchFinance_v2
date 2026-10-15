# Quant Autoresearch D06 / 4-1 — 미국 ETF 다자산 세션 정렬·독립 StrategyIR 연구

기준: 2026-10-15 UTC / 2026-10-16 KST. 코드 브랜치 `feat/d06-multi-asset-session-alignment-20261016`, 코드 커밋 `6fdf881` GitHub origin Push 확인. 운영 MCP 미배포.

## 이번 개발 변경

- `research/indicator_engine/multi_asset_development.py` 신규. 기존 전략 소스인 typed `AlgorithmPlan`은 보존. 기존 `compile_algorithm_plan` 및 `evaluate_algorithm_plan`(StrategyIR와 canonical fee backtest)를 사용해 각 종목 별도 독립 연구를 실행하며, core/data·core/backtest·전략 기본 계약 등 보호 영역은 수정하지 않음.
- 입력은 `DataZone.DEVELOPMENT`, `us_equities`, `1d`, 2~8개 허용된 미국 ETF(QQQ/SPY/IWM/DIA/VTI/EFA/TLT/GLD) 및 동일 NYSE 현지 세션당 종목 1개 완료 봉으로 제한. `ZoneInfo("America/New_York")`로 UTC/서머타임 정합화.
- **안전 정책:** 모든 자산이 동일 거래일을 가져야 한다. 누락·중복·주말·해당 일 16:00 뉴욕 시각보다 이른 시각의 미완료 일봉은 거부. 행 누락을 과거 종가 forward-fill하거나 앞날 가격으로 대체하지 않음. 동시 의사결정 `decision_known_at`은 참여 자산의 가장 늦은 바 완료 시각. 최소 차기 공통 연구 개장 시각은 다음 09:30 뉴욕 시각(마지막 세션은 None). 늦은 벤더 갱신 시각/과거 공개 시점 및 조기 폐장 실제 운영 캘린더 검증은 아직 미확인: **PIT 주장 금지**.
- 연구 계획·원본 데이터·자산별 버전·정렬/통계 증거를 해시로 연결해 입력 변경 후 실행을 거부. 결과는 종목별 독립 `initial_cash=10000` 기준 비용·체결수·최종 equity 요약이고 **공유 자본을 가진 다종목 포트폴리오 수익률이 아니다**.
- 로컬 CLI `preview-parallel-algorithm --market-parquet <path> --plan-json-file <path>` 추가. 출처 읽기 경로가 symbolic link 또는 파일 크기 제한(Parquet 64MiB/JSON 32KiB)을 넘으면 거부. `portfolio_pnl_approved=false`, `independent_oos_approved=false`, `orders_enabled=false` 고정.
- 기존 MCP 도구 32개 이름/URL, OAuth/토큰, 외부 GPT MCP 플로우, 원본 시장 데이터와 sealed OOS, 실주문 비활성 정책은 변경하지 않음.

## 실제 테스트

T0/T1: 신규 `tests/research/test_multi_asset_development_d06.py` **10 PASS**, 기존 `test_academic_algorithm_plan.py` **17 PASS**, 총 **27 PASS**; 변경 경로 Ruff·Mypy PASS 및 diff 검사 완료. 사례: QQQ/SPY 650 synthetic 영업일 시계열 정렬, 3분 늦게 마감 기록된 SPY가 의사결정 시각을 결정, 날짜 누락·동일 날짜 중복·미완료 봉 거부, 봉 끝값 변경 시 기존 관측 신호의 불변, compiled hash 변경 차단, Parquet/JSON local CLI 실행 및 sealed OOS 거부. 합성 자료이므로 **실제 시장 수익률·PIT 검증 아님**.

미실행/잔여:
- T2 기존 MCP 32개 전체 실제 호출과 D06 통합 개발 도구 노출은 D07에 배치.
- T3 전체 Pytest/Ruff/Mypy·서버 롤백, T4 GPT 10/100세대, T5 실제 가격 빈티지·기초유니버스 생존 편향/PIT·OOS, 거래 비용/용량, T6 paper 거래는 전부 미실행.
- 기존 프로젝트 목표 전체의 '다자산/다시장' 완결 단계는 아님: 현재 미국 ETF 동일거래소 세션만 다루고, 크로스섹셔널 랭킹/자산 간 교차 신호, 공통 계좌 할당, 다른 나라 시장·거래시간/휴장 캘린더/분할·배당 적용 및 공동 포트폴리오 accounting이 별도 필요. 이 기능을 갖추기 전 통합 수익률을 만들거나 승인하지 않는다.

**다음: D07 / 2-1** 모든 기존 MCP 32도구 실제 연결·권한·조회/쓰기/세대 체크포인트 계약 확인 → D08 통합/운영배포·롤백 → V01~V07 최종 데이터·OOS·통계/페이퍼 검증.
