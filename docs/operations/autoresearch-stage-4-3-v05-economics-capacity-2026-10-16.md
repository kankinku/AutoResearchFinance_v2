# Quant Autoresearch V05(4-3) — 비용·유동성·다중검정 개발 검증

점검 시각: 2026-10-16 KST/UTC. 사용자 승인 범위 잠금: [20문답 v1](../decisions/2026-10-16-autoresearch-20q-scope-lock-v1.md). 해당 Q04·Q07·Q09·Q20. 코드 브랜치 `feat/v05-cost-capacity-multiple-trials-20261016`, 기능 SHA `ea96ad7` GitHub Push 완료. 기존 MCP 운영 `da2331d`, URL/OAuth·연구원장·주문 비활성 유지.

## 기존 엔진 재사용 — 범위 무분별 확장 금지

- `core/costs/model.py`, `core/costs/slippage.py`의 고정 수수료/스프레드/슬리피지와 정규 `StrategyIR` 백테스트를 수정하지 않았다.
- `evaluation/trial_dependence.py`, `trial_null_calibration.py` 기존 제한적 Gaussian-null/상관 진단을 재사용했다. 해당 값은 보정된 DSR이나 전체 탐색 후보 수의 공증이 아니다.
- 신규 `research/indicator_engine/development_economics_v05.py`가 실제 학술 DEVELOPMENT fill·equity SHA, 비용/거래량, 후보 수 누락을 별도 read-only 진단. 다음 T4에서 GPT 후보·동일예산 랜덤 대조를 동일한 한계와 함께 감사할 수 있다.
- `research/indicator_engine/cli.py`에 `audit-algorithm-economics --database ... --market-parquet ... --plan-json-file ... --attempted-trials ... --max-participation ... --stress-multiplier ...` 로컬 명령 추가. 기존 검증된 AlgorithmPlan만 StrategyIR에 재컴파일해 비용 있는 canonical 백테스트를 한 후 결과를 검사한다. 별도 서버 자동 GPT 호출·MCP 도구수 변경 없음.

## 검사 내용·수학적 한계

1. 매수는 기존 엔진에서 현금 투입분에서 비용을 먼저 빼고 순수량으로 기록한다. V05는 이 처리 규칙을 역계산해 원래 매수 **총투입 금액**과 실제 기록된 매수 비용을 대조한다. 매도는 기록된 명목금액이 그대로 비용 적용 대상. 총비용/체결가격/수량/시각/원본해시 불일치 시 명시적 거부.
2. 비용 배수 증가는 **이미 실행된 수량과 거래시각을 고정한 선형 추가비용**이다. 재백테스트하지 않았으므로 해당 가정의 진짜 재현 가능한 equity/CAGR/Sharpe·수익성 보증은 없다.
3. 수량 ÷ 당일 일봉 거래량으로 사후 참여율을 관찰한다. 미래에 알 수 있는 장 종료 거래량을 next-open 주문에 사용하지 않으며, **실제 장중 호가 깊이/스프레드/시장 충격·체결 가능 용량을 입증하지 않는다**. 거래량 0·과도한 참여율·거래 없음은 통과 상태로 표시하지 않는다.
4. 시도한 후보 수는 caller 선언으로 **미공증**. 전체 후보 수익률 벡터가 주어졌을 때도 기존 상관/entropy/가우시안 참조의 `TRAINING_ONLY` proxy만 기록한다. 빠진 후보가 있거나 수익 벡터의 시간 정렬이 틀리면 오류. 독립 OOS p-value, 우월성/α·실수익 GO 모두 false.
5. OOS/VALIDATION/SEALED_OOS·임의 원본 변조·비유한 입력·기존 평가 비용과 불일치하는 통계는 차단. 실거래 실행 권한과 자동 주문 없음.

## 실제 저장된 QQQ 개발 원본에 대한 읽기 전용 1회 적용

`data/market/tiingo/QQQ_2020-01-02_2025-12-31_raw.parquet` (1,508봉, non-PIT DEVELOPMENT)와 기존 테스트용 typed `AlgorithmPlan` 예제를 **실제 보존 데이터에서 다시 평가**한 수치. GPT가 선발한 전략이 아니며 **선언 시도 후보 수=1**을 사용했다.

| 항목 | 결과 |
|---|---:|
| 개발 데이터 체결 수 | 69 |
| 기존 백테스트가 지불한 비용 | 646.7852129달러 |
| 기준 백테스트 net PnL (10,000달러 예시 원금) | 5,654.8332765달러 |
| 비용 스트레스 2배 가정 시 **추가** 비용 proxy | 565.9370613달러 |
| 가정된 사후 하루 최대 참여율 허용치 | 1% (임의 stress 설정, 거래 승인값 아님) |
| 관측 최대 당일 거래량 참여율 | 0.0000014894073 (비율, 0.00014894%) |
| 참여율 가정 초과 거래 날짜 수 | 0 |
| 실제 전체 후보 추적/다중검정 유의성 | 불가 |
| 판정 | `RESEARCH_ONLY_TRIAL_LEDGER_INCOMPLETE` |

증거 위치 `docs/operations/evidence/quant-validation-20261016/v05-qqq-development-economic-proxy.json`. 본 예시는 1개 계획의 **in-sample 개발 데이터** 재평가일 뿐, 다음 T4 전체 GPT 10/100세대 실제 연구와 랜덤 대조가 아닙니다. 단일 개발 데이터에서 크게 보이는 손익은 실현 가능 순수익으로 계산하거나 독립 검증 완료라고 보고하지 않습니다.

## 테스트·배포·다음 단계

- 신규 V05 테스트 **16개**, 범위 잠금 4개·기존 AlgorithmPlan/코호트 통계 테스트와 묶은 **53 PASS**, 변경 파일 Ruff/Mypy PASS.
- 전체 프로젝트 T3는 코드 변경 이후 미실행. T4 실제 GPT 10/100 연속 도구 호출·실중단 복구·같은 예산 무작위 비교, T5 진짜 서로 다른 날짜/공급자/PIT/봉인 OOS, T6 paper 미실행.
- **V05 코드 구현/로컬 개발 진단 완료, 경제성 인증 BLOCKED_NON_PIT_MISSING_FULL_TRIAL_LEDGER.**
- **다음은 범위 잠금대로 T4 실제 인증 ChatGPT MCP 10→100 완결 세대**. 코드/검증기 추가로 T4를 지연시키지 않는다. 기존 `https://project-moon.taild689f9.ts.net/quant/mcp` 및 OAuth/도구 32개/주문 비활성 유지.
