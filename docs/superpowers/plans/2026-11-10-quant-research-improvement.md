# Quant AutoResearch Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**작성일:** 2026-11-10 · **상태:** 사용자 개발 승인 / 순차 구현 중 / 미배포
**Goal:** 기존 Quant 자율 금융 연구기를 보존한 채 실행 정확성을 복구하고, V05 경제성 검증 → T4 실제 GPT 10/100세대 및 공정 대조 → V01~V04 독립 검증 → V06/V07 안전한 출시 판정으로 이어지는 재현 가능한 운용 체계를 완성한다.

**Architecture:** 기존 `StrategyIR`, 정본 백테스터, ChatGPT↔MCP 체크포인트, S2 진단, S7 대조 실험, S8 연구 메모리, 원장 및 V3의 분리된 세 트랙을 재사용한다. 새 실행 프레임워크·별도 ML 플랫폼을 만들지 않고, 수정은 오류 재현 테스트와 독립적인 최소 코드 변경으로 한정한다. 새 평가기와 옛 G150 증거는 버전·세션 경계로 분리한다.

**Tech Stack:** Python 3.10–3.12, pytest, Ruff, mypy, Pydantic v2, SQLite, pandas/pyarrow, MCP SDK, FastAPI, 기존 GitHub/Moon 및 ChatGPT 인증 연동.

**Spec:** [`docs/superpowers/specs/2026-11-10-quant-research-improvement-design.md`](../specs/2026-11-10-quant-research-improvement-design.md).  
**Plan Path:** `docs/superpowers/plans/2026-11-10-quant-research-improvement.md` (문서 저장 완료, 구현 승인은 별도).  
**Baseline:** `main` `c6fe2d7d70e34903110d889a718a9e80276e780a`, 태그 `quant-v3.0.0`; GitHub의 리포지토리 기본 브랜치는 여전히 `master`이므로 모든 PR의 기준은 명시적 `main`.

---

**2026-11-10 변경 승인:** [신규 연구 초기화 ADR](../../decisions/2026-11-10-quant-fresh-research-reset.md)에 따라 과거 G150 및 기존 실험의 부모·학습 기억·성과는 신규 연구로 계승하지 않습니다. G150 원장 복구를 새 연구의 선행 조건으로 적은 이전 문구는 이 ADR로 대체합니다. 기존 역사 기록을 위조하지 않으며 운영 원본의 물리 삭제는 미실행 상태입니다.

## Global Constraints — 변경 금지 규칙

1. `AGENTS.md`, `docs/decisions/2026-10-14-autoresearch-interview-20q.md`, `docs/decisions/2026-10-16-autoresearch-20q-scope-lock-v1.md`, `docs/operations/autoresearch-master-progress.md`를 **매 작업 시작 때 확인**. Q01–Q20, V05→T4→V01~V04→V06→V07 변경 금지. 범위 변경 시 사용자 별도 승인 및 ADR.
2. 과거 G1~G150 및 이전 실험은 새 연구의 부모·기억·승격/채점 입력에서 제거한다. 승인 아키텍처·과거 Git 감사 기록은 위조하지 않는다. 새 G1 세션은 별도 상태 경로와 새 엔진/입력/정책 해시만 사용한다.
3. StrategyIR가 전략의 유일한 소스. 모델은 typed 제안만 제출하며 `core/data`, `core/backtest`, `core/evaluator`, `core/validation`, `core/costs`, `core/integrity`, sealed OOS, 브로커 인증·주문 설정을 수정할 수 없다. 보호 파일의 개발자 수정은 검토된 PR에서만.
4. 기존 ChatGPT MCP URL·OAuth 등록·32개 공개 도구·모델 기본 실행 방식 변경 금지. 앱 모델 호출과 모델 없는 배치 워커는 분리 보고. 별도 LLM API 자동 전환 금지.
5. 실거래/실주문 불허. 모의 주문 관련 검증은 주입된 가짜 전송계층만 사용; 실제 인증정보/주문 테스트 금지.
6. 추가 전략 지표 대량 병합·기존 모듈 전면 개편·새 에이전트/강화학습 엔진 생성·의미 없는 설정 옵션 추가 금지. P3 우선순위보다 큰 신규 범위는 별도 승인.
7. 과거 연구 SQLite 부재는 신규 G1 개발을 막지 않는다. 다만 새 실험에 필요한 실제 시세·독립 검증 자료가 없으면 실제 T4/OOS 실증은 `BLOCKED`. 미확인 구 DB를 자동 생성·삭제·복구하지 않는다.
8. **매 작업:** 테스트 먼저 실패 확인(RED) → 최소 변경(GREEN) → 관련 회귀/Ruff/mypy 확인 → 작업별 독립 리뷰 → 원장 진행표 업데이트 → 원자적 커밋/PR. 사용자 승인이 있을 때만 실제 코드 작업·푸시/배포.
9. 상태값 `PASS / FAIL / BLOCKED / NOT_RUN / INTERRUPTED`를 구별해 보고. 수익성과 모델 자율성은 모의 테스트나 문서 완료로 대체하지 않는다.

## Review Focus — 구현 누락 위험이 높은 다섯 조건

1. **과거 세대 계승 차단:** 신규 연구가 옛 G150 또는 다른 실험의 부모·S7·S8·점수를 계승하지 않는지 Task 0·1·6·10에서 확인.
2. **지표 입력 이중 지연·주봉 미래 누출:** 이미 지연된 사전 계산 벡터와 기간 말 관측의 as-of 의미를 각각 테스트; Task 1·2.
3. **원시 데이터 동시 수집/부분 모의체결:** 실패한 동시 수집자가 다른 파일 삭제 금지, 미체결 주문 남으면 `FLAT` 보고 금지; Task 3·4.
4. **모델 없이 완료한 100세대 / 무작위 대비 불공정:** 진짜 각 세대 모델 호출 증거와 동일 자원/사전잠금 대조 확인; Task 8·9·10.
5. **OOS 결과 재학습·실거래 오인:** sealed data 결과는 연구 Director로 되돌리지 않으며 paper 시스템도 주문권한 승격 불허; Task 11·12·13.

## Source Map — 적용 위치와 책임

| 경계 | 현재 소스 | 계획상 처리 |
|---|---|---|
| API/모델 입력 | `integrations/chatgpt_mcp_sdk.py`, `integrations/codex_mcp_core.py` | 공개 인터페이스 변경 통제, 실제 ChatGPT 호출 증거 |
| 체크포인트/세대 | `application/academic_checkpoint_service.py`, `research/llm/autonomous_cycle.py`, `research/llm/checkpoint_autopilot.py` | 기존 세대 상태·멱등/재개 계약 재사용 |
| 지표/자료 | `core/data/{contracts,parquet,access}.py`, `core/features/{alignment,series,calculators}.py`, `research/llm/inherited_feature_compiler.py` | 접두 안정성·lag·source/PIT 복구 |
| 실행/손익 | `core/backtest/engine.py`, `core/costs/{model,slippage}.py`, `research/indicator_engine/strategy_adapter.py` | 비용 포함 진짜 동일 조건 재실행 |
| 원인/실험 | `research/llm/{diagnostic_research,experiment_learning,adaptive_direction}.py`, `application/academic_checkpoint_service.py:evaluate_experiments` | 증거와 가설 구분, 실패 기억 품질 검증 |
| 부모/전략 분기 | `research/llm/{lineage_selection,parent_portfolio_v2,inherited_feature_compiler}.py` | 기존 opt-in 다양성 경로 대조 |
| 실험 대조 | `scripts/{preregister_t4_equal_plan_comparison,score_t4_equal_plan_comparison,t4_preregister_random_control}.py` | 동일 예산 GPT/규칙/무작위 실증 |
| V05 | `research/indicator_engine/development_economics_v05.py` | 비용 프록시와 실제 replay 구분 |
| 영속 원장/장애복구 | `memory/evidence_store.py`, `runtime/{persistent_queue,system_controller,evaluation_executor}.py` | 원장 불변·중복·복구 경로 확인 |
| 시장 입력/모의 주문 | `application/market_data_service.py`, `research/indicator_engine/nasdaq_capture.py`, `integrations/kis/{config,client,paper_orders}.py` | 동시 저장 및 비체결 상태 안전성 |
| 별도 V3 브랜치 | `research/v3-strategy-evolution`, `research/v3-event-detection`, `validation/v3-independent-oos` | Track1 지표 단위 채택·Track2 사건 탐지 독립·Track3 검증 분리 |

**전수 조사 메모:** `main` Python 653개 파일 111,956줄 정적 AST 파싱 0 오류, 개발 분기 변경 파일 각각 353/355/34 Python 파싱 0 오류. 이 수치는 개별 런타임 경로를 완주한 테스트 수가 아니다. 2개 V3 event/OOS 브랜치는 메인 대비 문서만 변경됨. 전체 테스트·전체 mypy의 최종 통과 여부는 아직 `NOT_RUN`으로 둔다.

## Stage Gate — 작업 시작 순서

- **T0 / 안정성 선행:** Task 0~4. 원본 증거/권한 및 실행 정확성. 외부 운영 데이터 없으면 재개 `BLOCKED`.
- **V05 / 경제성:** Task 5~6. 기존 지표·비용 평가를 정직하게 구분; 릴리스/계약 문제 격리.
- **T4 / AI 진화 실증:** Task 7~10. 메모리·부모 선택 실험 → 실제 GPT 10세대 → 100세대. 새로운 알고리즘 도입보다 실제 루프 검증 우선.
- **V01~V04 / 독립 검증:** Task 11, 외부 데이터가 확보된 경우만 실행. Track2는 Task 14로 분리된 승인 작업이며 주경로를 막지 않는다.
- **V06 / 관측 운영:** Task 12.
- **V07 / 최종 판정:** Task 13. GO/NO-GO를 코드 테스트·모델 실증·경제성 각각 분리.
- **조건부 성능/확장:** Task 14~15. 현재 단계의 병목·근거가 있는 경우만.

---

## Task 0. T0 — 불변 기준점·운영 데이터 복구 가능성 잠금

**Files:** 확인 `AGENTS.md`, `docs/releases/quant-v3.0.0-checkpoint-20261027.md`, `.moon/recovery/2026-11-05-status.md`; 진행 시 `docs/operations/autoresearch-master-progress.md` 갱신만. 관련 검사 `scripts/verify_v3_ledger_integrity_fail_closed.py`, `scripts/verify_v3_checkpoint_memory_clone.py`.

**Interfaces:** 이후 모든 Task가 참조할 `source_commit`, `dataset_hash`, `session_id`, `evidence_head`, `evaluator_version`, `auth_endpoint`의 운영 메타데이터(시크릿 제외)를 문서화. 새로운 API 없음.

- [ ] **Step 1 — 확인:** `git rev-parse HEAD`, `git status --porcelain`, 원래 세 DB·Parquet의 존재/소유권/백업 해시를 **읽기 전용**으로 조회. 운영 원본을 새로 초기화·덮어쓰기하지 않는다.
- [ ] **Step 2 — 실패 조건 기록:** 현재 `/shared/Quant`에 운영 DB/데이터가 없으면 `BLOCKED: CANONICAL_STATE_NOT_MOUNTED`로 남기고 별도 경로를 임의 가정하지 않는다.
- [ ] **Step 3 — 검증:** 확보된 경우만 원장 SQLite 무결성, 150/150 세션, G150 증거 head `23925180a3664a669773f515d65cffa0607b6189cdfd59fcbff05b9864ab814d` 및 입력 데이터 hash `f637bcf0a8098aa13ed1758308086e8bfb4c3ade264ecb003ae741095ba95f9e` 확인. 불일치 시 중단.
- [ ] **Step 4 — 계약:** 옛 G150은 별도 read-only 자료이며 수정 엔진은 **새 평가 버전·새 세션**으로 시작. 테스트: 옛 레코드 변경 시 검출, 새 버전이 옛 세션에 자동 이어붙지 않는지 확인.
- [ ] **Step 5 — 완료 판정/기록:** Git source/원장/시세의 정확한 위치와 보호/미확인 상태를 원장에 기록; 실행환경 변경·실험 시작 없음.

**Exit:** 신연구는 기존 원장과 무관한 빈 상태의 G1에서 시작. 과거 DB 미회수가 아닌 새 시장·검증 데이터 부재만 관련 실증을 `BLOCKED` 처리.

## Task 1. T0 — 지표 지연을 한 번만 적용

**Files:** 수정 후보 `core/backtest/engine.py:474–538`, `research/llm/inherited_feature_compiler.py:28–88`; 테스트 `tests/research/test_inherited_feature_compiler.py`, `tests/core/test_series_feature_backtest.py` 및 새 `tests/core/test_precomputed_feature_lag.py`(필요할 때만).

**Interfaces:** 기존 `BacktestRequest(feature_values=...)`, `_feature_values(..., supplied, ...)`, `_new_feature_vector(ref, market)` 유지. 새 공개 API·모델 정책 없음. 사전계산 벡터의 **lag 적용 책임** 하나를 결정하고 모든 호출자를 확인.

- [ ] **Step 1 — RED:** `test_precomputed_feature_lag_is_applied_exactly_once`: ATR ref `lag_bars=2`가 컴파일 결과 첫 유효 인덱스 3, 엔진 신호에서도 3으로 유지; 현재 동작 5이므로 실패하도록 작성. 계산기 입력으로 생성한 미지연 벡터는 ref/spec lag가 정확히 한 번 적용되도록 별도 테스트.
- [ ] **Step 2 — 확인:** `pytest -q tests/research/test_inherited_feature_compiler.py tests/core/test_precomputed_feature_lag.py`에서 새 테스트가 의도한 이유로 실패하는지 확인.
- [ ] **Step 3 — 최소 수정:** 호출 경로 전체를 확인하고 사전 계산/엔진 입력 소유권 충돌 **한 곳만** 수정. 이전 기록의 지표 벡터를 조용히 재해석하지 않음.
- [ ] **Step 4 — GREEN:** 위 테스트 및 `tests/core/test_signal_backtest.py`, `tests/research/test_forward_window.py`, `tests/research/test_inherited_feature_compiler.py` 통과. 지표 hash와 체결 시점이 신버전에서 일관적인지 확인.
- [ ] **Step 5 — 변경/기록:** 기존 세션 무변경, 신버전 결과에 별도 버전 기록. 핵심 파이프라인 코드 리뷰 후 작업별 커밋.

**Exit:** `lag=2`가 4로 바뀌지 않고, 새 연구에서 과거 G150을 계승하지 않음.

## Task 2. T0 — 주봉/월봉 완료 시각과 as-of 검증

**Files:** `core/features/series.py:47–84`, `core/features/alignment.py`, `core/backtest/engine.py:501–515`; 테스트 `tests/core/test_feature_series.py`, `tests/core/test_feature_contracts.py`, `tests/core/test_series_feature_backtest.py`.

**Interfaces:** `resample_completed(observations, timeframe) -> tuple[SeriesObservation, ...]`, `align_as_of(target_timestamps, observations)` 공개 형태 유지. `available_at`보다 빠른 사용 금지.

- [ ] **Step 1 — RED:** 같은 수요일 시점에 ① 수요일까지만 있는 시계열과 ② 이후 금요일 데이터까지 추가된 시계열을 주봉 정렬한 값이 같아야 함(미완료 주 데이터 제외). 월말, 휴장일, 발표 지연 및 처음/끝 구간도 확인.
- [ ] **Step 2 — 확인:** `pytest -q tests/core/test_feature_series.py tests/core/test_feature_contracts.py tests/core/test_series_feature_backtest.py`에서 신규 prefix 테스트 실패를 관찰.
- [ ] **Step 3 — 최소 수정:** '주 내 최신 관측'과 '완료된 주봉 신호' 분리. 안전한 최소 선택은 **다음 주 관측 전에는 그 주의 값 확정으로 간주하지 않는 방식**; 동일 기간의 공개일자를 보유한 별도 근거가 있을 때만 조기 확정 사용.
- [ ] **Step 4 — GREEN:** 접두 불변, 주/월 경계, `available_at > target` 반환 금지, 지표 워밍업 통과. 이전 원장 재생은 Task 0의 구버전 경계를 따름.
- [ ] **Step 5 — 기록:** 타임프레임별 가용 시각 규칙 및 데이터 누출 방지 조건을 짧게 문서화하고 커밋.

**Exit:** 미래 관측을 덧붙여도 과거 신호가 변하지 않음.

## Task 3. T0 — 원시 시장 데이터 동시 수집 원자성

**Files:** `research/indicator_engine/nasdaq_capture.py:115–156`, `core/data/parquet.py`, `application/market_data_service.py:423–444`; 테스트 `tests/research/test_nasdaq_qqq_capture.py`.

**Interfaces:** `capture_nasdaq_qqq(start, end, output, raw_path, manifest_path, ..., fetch_bytes, captured_at)` 유지. 기존 append-only 단일 파일·원시 해시 계약 보존.

- [ ] **Step 1 — RED:** 두 프로세스가 동일 3개 출력 경로로 동시에 수집할 때 한 작업이 `FileExistsError`를 받더라도 성공자의 raw/Parquet/manifest 3개가 모두 남고 해시가 유효해야 함. 오류 후 소유하지 않은 파일 삭제 금지.
- [ ] **Step 2 — 확인:** `pytest -q tests/research/test_nasdaq_qqq_capture.py::test_concurrent_capture_preserves_winning_bundle` 신규 테스트 실패 확인.
- [ ] **Step 3 — 최소 수정:** 원자적 잠금/소유권 또는 전용 임시 번들 디렉터리와 배타적 승격 방식 중 **기존 프로젝트 관례에 맞는 하나만** 선택. 성공자 파일을 `except`에서 무조건 unlink하는 코드 제거.
- [ ] **Step 4 — GREEN:** 경쟁 실행(수십 회), 한 파일 쓰기 실패, 동일 경로 재요청 및 기존 파일 존재 시 무손실. 원본 해시와 불변 정책 확인.
- [ ] **Step 5 — 리뷰/커밋:** 잠금 해제 실패 등 실제 위험 경로만 검사, 불필요한 새 저장소/워커 추가 금지.

**Exit:** 경쟁자 실패 시 성공한 데이터를 삭제하지 않음.

## Task 4. T0 — 모의주문 부분 체결·미체결 주문 정리

**Files:** `integrations/kis/paper_orders.py:99–197`, 테스트 `tests/integrations/test_paper_orders.py`, `tests/cli/test_paper_order_smoke.py`.

**Interfaces:** `KISPaperOrderClient.run_buy_then_sell(...) -> PaperRoundTripResult`; `place_market_order`의 paper-only URL/거래 모드 게이트 불변.

- [ ] **Step 1 — RED:** 10주 주문 중 2주 체결 후 잔여 8주가 활성인 응답에서 `FLAT` 반환 금지. 늦게 체결되는 잔여 주문과 매도 부분 체결도 테스트; 모든 테스트는 `RecordingTransport` 주입만 사용.
- [ ] **Step 2 — 확인:** `pytest -q tests/integrations/test_paper_orders.py`에서 신규 테스트가 실패하는지 확인.
- [ ] **Step 3 — 최소 수정:** **잔여 주문 취소 요청·확인 및 최종 잔고/미체결 상태 확인** 전엔 반대 주문/`FLAT` 확정 금지. 취소 실패 시 주문 상태를 `UNSETTLED`나 명시적 오류로 반환(기존 결과 모델 호환은 테스트로 확인). 실거래 endpoint 거부 유지.
- [ ] **Step 4 — GREEN:** 부분 체결/지연 체결/미체결/중복 응답/취소 실패/잔고 미일치/라이브 endpoint 차단 시뮬레이션 통과.
- [ ] **Step 5 — 기록:** 해당 경로는 종이 계좌 테스트용이며 실제 주문 활성화 작업이 아님을 명시하고 커밋.

**Exit:** 활성 주문을 남긴 성공 판정 0건; 실제 KIS 호출 0건.

## Task 5. V05 — 실제 비용 스트레스·선택편향 평가 정합성

**Files:** `research/indicator_engine/development_economics_v05.py`, `research/indicator_engine/strategy_adapter.py`, `core/backtest/engine.py`, `evaluation/*` 중 실제 호출 경로; 테스트 `tests/research/test_development_economics_v05.py`, `tests/research/test_academic_benchmark_reconciliation.py`.

**Interfaces:** 기존 `audit_development_economics(...)`의 현재 고정 체결비용 프록시 필드/의미 유지. canonical 엔진으로 동일 StrategyIR/데이터를 새 비용으로 실제 재실행하는 검증 결과는 별도 출력 필드/함수에 넣어야 하며, **사후 차감 프록시를 재실행으로 표기 금지**.

- [ ] **Step 1 — RED:** 비용 스트레스가 신호·현금·체결 허용 조건에 영향을 줄 때 고정 체결 프록시와 전체 재실행 결과가 다를 수 있음을 테스트로 입증. 거래 수/비용·낙폭·순손익은 실제 재실행으로 계산해야 함.
- [ ] **Step 2 — 확인:** `pytest -q tests/research/test_development_economics_v05.py`에서 새 재실행 비교 테스트 의도된 실패 확인.
- [ ] **Step 3 — 최소 수정:** 이미 존재하는 `BacktestEngine.run(BacktestRequest(..., cost_stress_multiplier=...))` 재사용. 새 비용 모형·학습기·매매 모델 도입 금지.
- [ ] **Step 4 — GREEN:** 출처/체결 as-of/공매수 한도/일일 거래량/슬리피지·거래비용/표본 부족/시도 횟수·효과적인 다중 탐색 수 검증. 개발 단일기간 수익만으로 합격 금지.
- [ ] **Step 5 — V05 게이트:** `DEVELOPMENT_ONLY` 결과와 독립 수익성/승인 분리, 변경 후 기존 원장 replay 호환 방식 확인, 결과 기록 및 커밋.

**Exit:** 비용 스트레스 결과가 실제 리플레이인지 프록시인지 명확하고, 위험·비용 게이트 위반 시 불합격.

## Task 6. V05/T4 선행 — 통합 계약·릴리스 회귀 게이트 복구

**Files:** `integrations/chatgpt_mcp_sdk.py`, `integrations/codex_mcp_core.py`, 테스트 `tests/integrations/test_chatgpt_mcp_sdk.py`, `tests/integrations/test_chatgpt_mcp_moon_oauth.py`, `tests/contracts/*`, `moon.config.json`, `pyproject.toml`; 비교 브랜치 `fix/quant-v3-parent-feedback-ponytail-20261030`.

**Interfaces:** 기본 공개 도구 32개, 기존 인증 범위·도구 이름·기존 URL. 변경된 브랜치 `suggest_guided_thresholds`는 **자동 통합하지 않음**.

- [ ] **Step 1 — RED:** 위 WIP 브랜치에서 과거 `32 != 33` 도구 수에 따른 두 실패 테스트를 정확히 재확인(메인에서 섣불리 33개로 테스트만 수정하지 않음).
- [ ] **Step 2 — 영향 조사:** 새로운 공개 도구를 삭제/비공개로 유지하거나 **기존 연구 도구의 선택 인자**로 수용 가능한지 클라이언트/서버·로그/모의테스트 비교. 공개 API 추가가 필수면 승인 ADR로 별도 분리.
- [ ] **Step 3 — 최소 수정:** 대상 브랜치에서 공개 계약·테스트·문서를 동일한 32 도구 정책으로 정합화. 내용과 계약이 맞지 않는 단순 assertion 숫자 교체 금지.
- [ ] **Step 4 — GREEN:** `pytest -q tests/contracts tests/integrations/test_chatgpt_mcp_sdk.py tests/integrations/test_chatgpt_mcp_moon_oauth.py`; `ruff check .`; `python -m mypy .` 결과를 각각 기록. `uv --locked` 설치/lock 문제가 나면 의존성 상태 따로 보고하며 운영 환경을 무단 초기화하지 않음.
- [ ] **Step 5 — 통합 제한:** WIP 45개 변경 파일 전체 병합 금지. 해당 결함을 해결할 최소 커밋과 관련 테스트만 선별. `main` 반영 전 독립 리뷰.

**Exit:** MCP/OAuth/기존 클라이언트 계약을 깨지 않는 부분적 수정만 병합 가능.

## Task 7. T4 — 실패 연구 메모리의 실제 의사결정 품질 검증

**Files:** `research/llm/{experiment_learning,adaptive_direction,cross_generation_memory,feature_contribution_f3}.py`, `application/academic_checkpoint_service.py:_context`, `research/llm/diagnostic_research.py`; 테스트 `tests/research/test_experiment_learning_d05.py`, `tests/research/test_adaptive_research_direction.py`.

**Interfaces:** 기존 `build_experiment_learning(history, records, *, max_recent=12)`, `build_research_direction(history, controlled_reports)` 보존. 새로운 학습 모델이나 가중치 파라미터 DB 불필요.

- [ ] **Step 1 — RED:** 다음 계획 컨텍스트가 S7의 `NO_OBSERVED_EFFECT`, `DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY`, `DIRECTION_MATCHED_DEVELOPMENT_ONLY`를 구분하고, 실패 가설/실행 신호 중복을 가중치 조정만으로 성공으로 착각하지 않는지 테스트.
- [ ] **Step 2 — 확인:** 이미 코드에서 만족하는 테스트라면 **변경 불필요**로 판정. 테스트가 실패할 때만 컨텍스트의 원인 코드·최근 실패 목록 요약을 고침.
- [ ] **Step 3 — 최소 수정:** 연구 패킷의 근거 해시·실험 ID·가설/관측 구분을 유지하며 필요한 정보만 표시. 방대한 새 DB/기억 엔진 추가하지 않음.
- [ ] **Step 4 — GREEN:** 원장 checksum 변조, 미시험 가설, 같은 체결·다른 StrategyIR, 최근 실험만 보여 과거 실패를 반복하는 경우 테스트. GPT의 '자기평가'가 근거 검증을 우회하지 않음.
- [ ] **Step 5 — 성과 지표:** '유효 새 체결/평가 수', '동일 실패 반복률', '가설 방향 일치율'을 원장에서 추출 가능하게 확인. LLM이 '학습했다'는 문구보다 실제 실험 재현성과 대조 결과 사용.

**Exit:** 메모리 전달이 유실/중복되지 않음을 실증. 대조 실험 전에는 우월성 미주장.

## Task 8. T4 — 부모 전략 다양화: 기존 opt-in 경로의 통제 실험

**Files:** `research/llm/{lineage_selection,parent_portfolio_v2}.py`, `application/academic_checkpoint_service.py:_selected_development_parent`, `tests/research/test_parent_portfolio_v2.py`, `tests/research/test_lineage_parent_selection_p0_3b.py`, 필요시 새 실험 스크립트 **1개만**.

**Interfaces:** 기존 `parent_portfolio_v2=False` 기본값 그대로. `shortlist_counted_generations`, `choose_parent_lane`, `choose_development_parent` 재사용. 새 후보 선택은 기록된 StrategyIR/해시를 평가할 뿐, 원장 수치·OOS·브로커 설정을 바꾸지 않는다.

- [ ] **Step 1 — RED:** G94/G96/G106에 최근 25세대 부모가 몰리는 사례를 재생 가능한 **개발 후보 픽스처**로 검증. 부모 다양화 on/off 양측에 같은 후보·예산·실험수를 배정.
- [ ] **Step 2 — 확인:** `pytest -q tests/research/test_parent_portfolio_v2.py tests/research/test_lineage_parent_selection_p0_3b.py` 및 신규 다양성/동일 체결 해시 테스트 실행.
- [ ] **Step 3 — 최소 수정:** 실효 신호 동일/비용 게이트/거래 수 부족 부모 제외 기능을 기존 경로에서 우선 활용. **충분하지 않을 때만** 서로 다른 계열 유지(수익형/저낙폭형/다른 레짐) 선택 규칙을 opt-in 방식으로 보강.
- [ ] **Step 4 — 실험:** 원래 선택 방식과 opt-in 방식을 같은 개발 데이터/시드/호출 예산으로 대조. 부모 집중도·새 신호 수·가설 검증률·저낙폭 트랙 보존·비용을 기록.
- [ ] **Step 5 — 판정:** 통계적으로 유리하다는 실증 전에는 메인 기본값을 변경하지 않고 `EXPERIMENTAL`로만 표기. OOS 승격·이전 원장 재작성 금지.

**Exit:** 부모 다양성이 개선되는지 객관적으로 비교. 단순 `unique hash` 증가로 합격 처리 금지.

## Task 9. T4 — GPT·기존 규칙·무작위 동일 예산 대조 실험 사전등록

**Files:** `scripts/{t4_preregister_random_control,preregister_t4_equal_plan_comparison,score_t4_equal_plan_comparison}.py`, `research/llm/adaptive_direction.py`, `tests/research/test_t4_equal_plan_prereg.py`, `tests/research/test_t4_equal_plan_score.py`, `docs/operations/...`의 별도 실험 보고서.

**Interfaces:** 기존 스크립트 입력/출력 형식 및 증거 SHA 재사용. 새로운 기본 정책 변경 금지.

- [ ] **Step 1 — 사전등록:** 비교군 세 가지를 고정: (A) GPT+S7/S8, (B) 기존 고정 선택 규칙, (C) 난수 시드 고정 랜덤. **동일 데이터/비용/후보 생성 횟수/백테스트 수/가능한 모델 호출·토큰 비용**을 사전 문서화. 다른 자원은 결과에 그대로 명시.
- [ ] **Step 2 — RED/검수:** 계획을 제출한 뒤 점수 입력/구간/전략 해시를 수정하면 스크립트가 거부하도록 테스트. 동일 체결 신호인데 hash만 다른 전략은 '새 알고리즘'으로 세지 않음.
- [ ] **Step 3 — 최소 수정:** 기존 정본 평가기·스크립트가 부족한 **실행 시간/모델 요청/시도/중복/유효 후보 수 필드만** 보강; 새 점수 체계·ML 훈련기 도입하지 않음.
- [ ] **Step 4 — GREEN:** 판정 항목은 개발구간 누적수익이 아니라 **동일 예산 유효한 신규 신호·비용 반영 위험 성과·S7 가설 적중·중복/실패 횟수**. 통계 검정 신뢰도와 시드 수 부족을 함께 출력.
- [ ] **Step 5 — 결과 정책:** GPT 우위가 모호하거나 불리하면 'T4 엔진 완료 여부'와 '연구 진화 능력 불합격'을 별도로 보고; 편향된 새 정책을 기본으로 승격하지 않음.

**Exit:** 결과를 보기 전에 대조군·예산·선택 기준이 고정되고 변경 흔적이 검증됨.

## Task 10. T4 — 실제 ChatGPT MCP 10→100 완결 연구 + 중단·재개

**Files:** 기존 `research/llm/checkpoint_autopilot.py`, `research/llm/inherited_checkpoint_autopilot.py`, `research/llm/autonomous_cycle.py`, `application/academic_checkpoint_service.py`, `integrations/chatgpt_mcp_sdk.py`; 테스트 `tests/integrations/test_academic_autopilot.py`, `tests/integrations/test_academic_mcp_sessions.py`, `tests/research/test_autonomous_academic_cycle.py`.

**Interfaces:** 기존 인증 연결과 `start/get/submit_plan/submit_diagnosis/evaluate_experiments` 계약 유지. `AcademicCheckpointAutopilot.run(session_id, max_generations=...)`는 **호출자 제공 모델**인 경우에만 실제 제안 호출. 모델 없는 배치와 비교/합산 금지.

- [ ] **Step 1 — 환경 게이트:** Task 0 `PASS`로 진본 데이터·DB를 확보했고 Task 1~6 정확성/인증 회귀를 통과했는지 확인. 인증된 ChatGPT MCP 도구가 실제 노출되고 모델 Plan/Diagnosis 제출 가능한지 **동일 app 경로**로 확인. 없으면 `BLOCKED`.
- [ ] **Step 2 — RED/복구 테스트:** 중단 시 `AWAITING_PLAN`, `AWAITING_DIAGNOSIS`, 완료 커밋 직후 S7 누락, `RUNNING`의 명시 재조정, 2중 제출/중복 세대 방지 테스트. 실패 시 실제 원장 변경없이 복구.
- [ ] **Step 3 — 10세대:** 별도 새 세션에서 실제 모델이 10개 세대 각각 Plan→결정/체결 감사→Diagnosis→S7→다음 계획을 제출·커밋. **호출 로그/실험 ID/모델 근거/시드/계약 해시**와 회차 수 일치 확인. 서비스가 단순한 mock인지 반드시 분리.
- [ ] **Step 4 — 100세대:** 10세대 증거가 통과한 뒤 같은 버전 계약으로 최대 100세대 실행. 중단/재시작·재개 시 이미 커밋된 세대를 재증가/수정하지 않음. 별도 **중지 요청까지 지속 모드**도 기존 상태기계를 재사용하되 실제 GPT 공급자를 부르지 못하면 BLOCKED로 표시하고 모델 없는 배치를 자율 모드로 속이지 않음. 최근 20세대 정체/중복이 발생하면 정지 사유도 기록.
- [ ] **Step 5 — 검증:** 실제 GPT 연속 실행 입증과 GPT가 무작위보다 우수함을 **독립 판정**. `completed_generations=100`만으로 학습/수익성 인증하지 않음. 완료 증거와 수락 게이트 원장 기록.

**Exit:** 수량보다 각 세대의 진짜 모델 관여와 원장 진실성이 검증됨. 데이터 회수·앱 권한 불가 시 `BLOCKED`.

## Task 11. V01~V04 — 독립 OOS 사전 잠금·PIT 검증 및 일회성 평가

**Files:** `research/indicator_engine/{historical_vintage_preflight,sealed_oos_precommit,corporate_asof_gate}.py`(실제 이름과 구현 존재 확인 후), `core/data/access.py`, `evaluation/*`, `tests/research/test_sealed_oos_precommit_v04.py`, `tests/research/test_historical_vintage_preflight.py`, 전용 브랜치 `validation/v3-independent-oos`.

**Interfaces:** 기존 데이터 존 `DataZone.SEALED_OOS`, 연구 역할 접근 금지 및 `InMemoryDataProvider.read(zone, role)` 권한 계약 유지. 별도 평가 보고서를 다음 세대 context로 export하지 않음.

- [ ] **Step 1 — 읽기 전용 사전 확인:** Track3에 기록된 고정 G94/G106/G96/G60 StrategyIR 해시, 기존 데이터/증거 해시 및 독립 소스의 실제 확보 여부를 검증. 기존 연구기간을 다른 이름으로 복사한 데이터 금지.
- [ ] **Step 2 — RED:** 연구 권한으로 SEALED_OOS를 조회하거나 OOS 결과를 연구 컨텍스트로 전달하려 하면 테스트가 실패/접근 거부되는지 확인.
- [ ] **Step 3 — 선등록:** 평가 전에 데이터 기간/벤더 발표 시각/배당·분할·가격 조정/PIT/유동성/비용/벤치마크/결과 임계치/선택 전략 해시를 불변 형식으로 고정. 미검증 자료라면 `BLOCKED` 유지.
- [ ] **Step 4 — GREEN/독립 실행:** 조건이 모두 맞을 때만 Track3 독립 평가자에게 접근권을 부여하고 1회 평가. 추정오차·낙폭·거래수·순수익·위험 맞춤 비교를 포함. 결과 보고 이후 같은 구간을 튜닝에 사용하지 않음.
- [ ] **Step 5 — 결과:** 성과 좋음/나쁨과 무관하게 원본 G150과 Track1/2 학습 입력 불변. 재평가가 필요하면 **새 외부 독립 구간**을 확보할 때까지 중단.

**Exit:** 독립 데이터 확보 전에는 승인 없음, 결과 공개 후 개발 회귀 금지.

## Task 12. V06 — 주문 OFF 상태의 연구 신호 관측/모의 운영

**Files:** `integrations/kis/{permissions,live_gate,config,client,paper_orders}.py`, `runtime/system_controller.py`, 기존 broker 모의 테스트.

**Interfaces:** `validate_research_permissions`, paper-only endpoint gate 유지. 시스템의 `orders_enabled=False`는 결과/대시보드에도 일관되게 표시.

- [ ] **Step 1 — RED:** 연구 프로세스가 KIS 인증정보/주문 권한을 얻는 구성, 라이브 endpoint 입력, 사람 승인 없는 포지션 실행을 거부하는 테스트 작성.
- [ ] **Step 2 — 확인:** 테스트가 실제 주문 없이 실패 조건을 검출하는지 실행.
- [ ] **Step 3 — 최소 수정:** 기존 `ResearchPermissions`/paper-only 검사를 재사용; 자동 실계좌/주문 기능 개발·활성화 금지. 필요한 관측 로그/신호 시점만 안전하게 표시.
- [ ] **Step 4 — GREEN:** 전환 시나리오(복구/환경변수/테스트 전송/실서버 URL)에서 한 번도 주문 권한이 승격되지 않음.
- [ ] **Step 5 — 기록:** V06은 '실거래 허가'가 아님을 보고서·원장에 명시.

**Exit:** 주문 OFF 환경에서도 신호/시점/가상 결과를 관측하고 복구할 수 있음.

## Task 13. V07 — 독립 최종 GO/NO-GO 및 릴리스 품질 판정

**Files:** `moon.config.json`, `AGENTS.md` 정책 준수 검사, `docs/operations/autoresearch-master-progress.md`, existing `tests/governance/test_autoresearch_scope_lock.py`, 관련 CI/릴리스 문서.

**Interfaces:** 기존 릴리스 체크 및 status schema 재사용. 필요한 신규 대시보드/도구 만들지 않음.

- [ ] **Step 1 — 증거 대조:** ① 엔진 및 안전성 ② 실제 AI 자율/무작위 대비 ③ 독립 수익성 각 단계의 증거 SHA와 차단 사유를 분리.
- [ ] **Step 2 — 전체 게이트:** `ruff check .`, `python -m mypy .`, `python -m pytest -q`를 지정 개발환경에서 **완주하여** 각 상태 기록. 에러·중단을 PASS로 취급하지 않는다.
- [ ] **Step 3 — 호환 게이트:** 기존 ChatGPT 32 tools·OAuth·MCP URL·작업 재개·기존 G150 조회(구버전)·데이터 존·주문 OFF 테스트. 배포 전 독립 Reviewer의 위험 경로 확인.
- [ ] **Step 4 — 판정:** 세 단계 중 하나라도 증거가 부족하면 해당 단계 `NO-GO/BLOCKED`; 계획에 없는 권한을 자동 부여하지 않는다.
- [ ] **Step 5 — 마감:** 진행 원장 완료/잔여를 날짜·브랜치·SHA·테스트 로그/차단 원인과 함께 기록. 코드/시크릿/운영 DB 자동 배포 금지.

**Exit:** 기술적 기능·진화 실증·경제성·주문 승인을 서로 혼동하지 않는 릴리스 보고서.

## Task 14. 별도 승인·분리 트랙 — Track2 특수 시장 이벤트 조기 탐지 (주경로 차단 금지)

**Files:** 독립 브랜치 `research/v3-event-detection`, 기존 `core/features`, `research/indicator_engine`, `evaluation` 중 검증 가능한 공통 부분만. 기존 계획 `docs/plans/v3-track2-event-detection-20261027.md`.

- [ ] **Step 1:** 사건 정의(폭락/반등/변동성 급등)와 관측 시점/사후 레이블을 **별도 명세**로 잠금. 임의 임계값을 확정된 사용자 선호처럼 주장하지 않음.
- [ ] **Step 2:** 사전 사건 리드타임, 경고 예산, PR-AUC, 연간 오경보, 무경고·항상경고 기준선 테스트의 실패 사례 작성.
- [ ] **Step 3:** 기존 등록 지표만으로 기저 빈도·계산 가능성 검토. 희귀 이벤트 부족 시 추가 데이터 필요성만 기록하고 합격 주장 금지.
- [ ] **Step 4:** 탐지기의 경고 원장과 비인과·PIT 제한을 명시. Track3 OOS 조회/Track1 연구 반영은 별도 승인 전 금지.
- [ ] **Step 5:** T4 검증을 지연하거나 본체 코드에 선제 통합하지 않음.

**Exit:** 이벤트 탐지는 본체의 수익 전략 진화와 다른 독립 과제로 평가됨.

## Task 15. 조건부 개선 — 원장 성능·대형 서비스 파일 분해 (증거가 있을 때만)

**Files:** `memory/evidence_store.py:97–103`, `application/academic_checkpoint_service.py`(약 2,867줄), `runtime/runtime_snapshot.py`; 관련 테스트.

- [ ] **Step 1:** 150·1,000·10,000 이벤트 기준 실제 append/read 지연, 메모리, 잠금 경합을 측정하고 환경/데이터 크기·반복 횟수 기록.
- [ ] **Step 2:** 수용 가능한 목표(예: 세대당 append p95 제한)를 **검증 이전에** 정하고 실측이 목표 이내면 코드 변경 생략.
- [ ] **Step 3:** 병목이 입증되면 동일 SQLite 테이블의 indexed query 또는 해당 기능 부분 분리 등 **가장 작은 변경**만. 분리 자체를 목표로 삼지 않음.
- [ ] **Step 4:** 증거 hash·불변 trigger·rollback/동시성·재현성에 대한 회귀 테스트 및 성능 재측정.
- [ ] **Step 5:** 실제 측정 개선이 없는 리팩터링은 반려. 별도 실증 전 V05/T4 진행을 지연하지 않음.

**Exit:** 측정된 병목만 해결 또는 변경하지 않기로 기록.

---

## 실행 방법·브랜치·리뷰 약속

1. **추천 실행 방식:** Superpowers `subagent-driven-development` — 고위험 경계인 금융 계산·원장·권한 수정은 Task마다 독립 리뷰가 효과적. 단, subagent 실행환경이 없는 경우 `executing-plans`로 같은 TDD 단계를 진행하고 본체 PR 전체를 독립 리뷰.
2. **작업 브랜치:** 승인 후 `main`에서 **새 격리 worktree/작업 브랜치** 생성. `main`/`master`/Track3 원본 직접 수정 금지. `superpowers:using-git-worktrees`를 실행 단계에서 사용.
3. **의존성:** Task 0 → Task 1~4 (상호 일부 병렬 가능, 그러나 백테스터·자료 변경과 원장 테스트는 순차 통합) → 5 → 6 → 7~9 → 10 → 11 → 12 → 13. Task 14/15는 별도 승인·근거가 있을 때만.
4. **자주 커밋:** 각 Task당 하나 이상의 최소 atomic commit, 관련 테스트 로그와 코드 diff를 리뷰; `git diff --check`; 범위 밖 파일 수정 없음.
5. **추가 라이브러리·프레임워크:** 사전 승인 전 추가하지 않는다. '연구가 더 똑똑해졌다'는 말은 동일 예산 대조에서 실제로 증명했을 때만.
6. **원장 복구:** 입력 원본·키·OAuth는 Git에 포함하지 않고 운영 저장소 백업과 수정 소스 버전을 1:1로 추적.
7. **보고:** 사용자에게 매 단계 '무엇을 함/무엇이 통과/남은 차단/다음 작업' 4가지 항목만 짧게 보고, 세부 로그는 체크포인트에 저장.

## 자체 검토 체크리스트

- [ ] 원본 20문답, Q05/Q06/Q07/Q08/Q09/Q11/Q13/Q15/Q17/Q20 요구가 Task 0~13과 직접 연결됨.
- [ ] 기존 `main`과 3개 개발 변경분을 섞어 버전·성능·검증 상태를 허위 표기하지 않음.
- [ ] 설계 명세와 각 Task의 변경 파일·테스트·합격 결과·실패 시 상태가 연결됨.
- [ ] V05→T4→V01~V04→V06→V07 고정 순서 준수; event/성능 확장은 조건부.
- [ ] 모델 기본 연결, 공개 도구, OAuth, PIT/OOS, 주문권한, Evidence 원본 불변.
- [ ] 새 API/코드 추상화는 기존 모듈로 해결되지 않을 때만.

## 수락 및 인계

이 계획은 2026-11-10 사용자 개발·실험 초기화 승인을 반영했다. 구현은 단계별 독립 테스트·리뷰를 요구하며 운영 배포 또는 실주문을 승인하지 않는다. 시작 시 반드시 기존 저장소 기준 SHA·데이터 마운트 상태를 다시 점검한다. 해당 경로를 확보하지 못하면 운영 연구 실행·성과 검증은 `BLOCKED` 처리하고 **원본 보존을 우선**한다.
