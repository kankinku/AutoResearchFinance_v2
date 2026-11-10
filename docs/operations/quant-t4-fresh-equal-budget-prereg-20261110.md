# Quant T4 3군 동등 예산 실험 사전등록 — [10/16] Task 9

**작성:** 2026-11-10 KST · **상태:** PROTOCOL_FROZEN / FRESH_MANIFEST_BLOCKED · **범위:** 16단계 개선 Task 9 · Q02/Q04/Q07/Q09/Q11/Q13/Q15/Q20.

## 이유 및 선행 통제

기존 2026-10-20 `T4_EQUAL_ALGORITHM_PLAN_OPPORTUNITY_V1` 비교의 GPT군은 **과거에 이미 관측한 GPT 결과**를 가져온 소급 분석이며, 통제군과 모델/토큰·검색 분포가 같지 않다. 기존 `scripts/{preregister_t4_equal_plan_comparison,score_t4_equal_plan_comparison,t4_preregister_random_control}.py`와 당시 보고서·결과 파일은 **그대로 보존**, 새 G1 실험 근거·부모·기억·데이터 입력으로 **사용 금지**. 사용자 승인 [2026-11-10 신규 연구 초기화 ADR](../decisions/2026-11-10-quant-fresh-research-reset.md)을 우선한다.

**새로운 정책 파일:** [T4 fresh 동등 예산 프로토콜](quant-t4-fresh-three-arm-preregistration-20261110.json). SHA256 콘텐츠 해시 `45a446476150784b92da958ffb78f280d406fe12d5dafa1be82f1c0334695daa`는 코드의 불변 회귀 테스트와 함께 Git에 포함한다. 이 프로토콜만 현재 **사전등록 완료**. 실제 시장 데이터 원본·사용할 신규 코호트/3개 세션 ID·수정 평가기 버전/소스코드 해시는 현재 진본 확인되지 않아, **실행 매니페스트와 연구 결과는 아직 만들지 않았다**.

## 결과를 보기 전에 고정하는 세 비교군

| 군 | 방법 | 사전 고정된 동일 연구 기회 |
|---|---|---|
| A: GPT_S7_S8 | 새 ChatGPT MCP 연구 세션의 Plan→S2 비용 체결→Diagnosis→S7→S8, 이전 G150 기억 없음 | 후보 계획 10개·S7 10개·정본 백테스트 20회 |
| B: FIXED_RULE | 기존 고정 알고리즘 제안 규칙(결과 맞춤 튜닝 금지) | 동일 |
| C: RANDOM_SEEDED | 승인 지표 문법, 난수 시드 `20261110` 고정, 실험 후 재추첨 금지 | 동일 |

공통 계약: QQQ 단일 종목, **DEVELOPMENT 데이터만**, 동일 데이터 해시·명시한 날짜 시작/종료·피처 정책 해시·비용 정책 해시·평가기 버전·소스코드 해시, 동일 기본 롱/현금·다음 봉 시가 실행 모델, 허용 지표 및 레짐의 명시적 목록. 군별 **계획 시도 10, S7 시험 10, 백테스트 20**, 모델 호출 상한 20·토큰 합계 상한 200,000. 모델 API 호출은 A에만 필요할 수 있어 **실제 각 군의 모델 호출/입출력 토큰/경과시간을 별도 집계**하며 차이가 발생하면 `actual_model_budget_equalized=false`와 `statistical_superiority_established=false`를 기록한다. 상한이 같다는 사실이 자원 소비나 연구 우월성이 같음을 뜻하지 않는다. 같은 데이터의 1시드 10회는 통계적 유의성 확정 자료가 아니다.

실험 전 `freeze_fresh_manifest`로 실제 데이터 SHA256, 시장 날짜 구간, 신규 `quant-improved-evaluator-...` 버전, 비용·피처·소스 SHA, **세 개의 서로 다른 신규 세션 ID**를 결합해 `freeze_hash`로 고정한다. 과거 GPT 세션 ID 등은 거부한다. 서명이라 부르지만 본문 SHA는 **전자서명이 아니라 콘텐츠 체크섬**이며 사전등록 시점 자체는 외부 Git commit/append-only 원장으로 입증해야 한다.

## 제출과 점수 검증(사전등록과 분리)

- 각 군의 세대별 typed `AlgorithmPlan`, 해시·전략 해시·데이터·세션 ID는 **평가 전에** 제출 영수증으로 봉인하고, `receipts_hash`를 별도 변경 불가 저장소에 고정한다. 결과는 `observations_hash`로 봉인한다.
- `validate_fresh_equal_budget_score`는 세 개의 **외부 고정 SHA 인자** `expected_manifest_hash`, `expected_receipts_hash`, `expected_observations_hash` 없이는 실행되지 않는다. 세대 1~10의 슬롯 중복/누락, 데이터·구간·코드·평가 정책·전략/계획/증거 해시 불일치, 임의 수정·재해시, 군별 후보/S7/백테스트 시도 수 초과·누락, 모델 호출·토큰 예산 초과, 비정상 수익/낙폭/비용을 거부한다.
- 체결 목록의 신호 해시만 다른 동일 실행은 **같은 체결 trace**로 중복 제거. 신고된 비용은 개별 체결 비용 합계, 청산 횟수는 sell 체결 수, 실행 순서와 매매 금액은 체결 원시 항목과 내부 일치해야 한다. 점수 우선순위는 **비용 반영된 독립 체결 해시 및 위험 게이트(청산 ≥30, MDD ≤30%, 양수 순수익)**, 그 다음 S7 가설 방향 일치/실패/중복·선택 편향, 모델 호출·토큰·시간.
- **중요 한계:** 사후 입력이 체크섬과 자체 일치한다고 해서 정본 엔진/가격원장/실제 독립 GPT 호출이 확인되는 것은 아니다. 점수 출력은 무조건 `DESCRIPTIVE_NOT_INDEPENDENTLY_REPLAYED`, `canonical_replay_independently_verified=false`, `external_commit_timing_independently_verified=false`, `statistical_superiority_established=false`, `independent_oos_approved=false`를 유지한다. Task 10 이상에서 실제 모델/체결·시장 데이터·외부 원장의 종단 재현이 끝나기 전에는 **새 전략 우월성·실거래 승격 금지**.

## 실제 실행 명령(새 프로토콜만 현재 실행)

사전등록 정책 파일은 이미 다음 명령으로 **쓰기 전용(x mode)** 생성했고 Git에 동결했다. 같은 경로로 재실행하면 덮어쓰기 대신 실패한다.

```bash
python -m scripts.preregister_t4_equal_plan_comparison --fresh-protocol-output docs/operations/quant-t4-fresh-three-arm-preregistration-20261110.json
```

**추후 실제 새 자료/세션 확보 시에만** 데이터·평가기·코드/정책 진본 SHA와 세션 ID가 포함된 JSON 설정 파일을 만든 뒤:

```bash
python -m scripts.preregister_t4_equal_plan_comparison --fresh-manifest-config /safe/new-g1-config.json --fresh-manifest-output /safe/fresh-locked-manifest.json
python -m scripts.score_t4_equal_plan_comparison --fresh-manifest /safe/fresh-locked-manifest.json --fresh-receipts /safe/new-g1-submissions.json --fresh-observations /safe/new-g1-evidence.json --expected-manifest-hash <externally-fixed-hash> --expected-receipts-hash <externally-fixed-hash> --expected-observations-hash <externally-fixed-hash> --fresh-output /safe/new-g1-descriptive-score.json
```

실행 전 반드시 매니페스트 SHA를 Git 등 **별도 권한의 증거 저장소에 먼저 등록**하고, 각 제출도 체결 전에 별도 고정해야 한다. 임의 문자열 64자를 입력하는 것만으로 자료 원천 진실성이 인증되는 것은 아니다. 이 CLI는 실제 모형 호출·시세 다운로드·브로커·자동 세대 생성도 수행하지 않는다.

## 테스트와 완료/미완료

- TDD RED: 신규 프로토콜 ImportError, 점수 검증 함수 ImportError, 새 CLI 인식 실패를 각각 재현했다. GREEN: 신규/레거시 사전등록·점수 테스트 **58 PASS**, 여러 해시·구간·실험 정책·전략/계획·체결·위험/모델 예산 위반의 fail-closed 및 CLI 쓰기 전용 증거 보존 검증. 기존 2026-10-20 v1 문서/저장 보고서/함수·입력/출력 그대로 유지.
- **최종 관련 테스트:** 신규/역사적 T4 사전등록·점수 검증 **58 PASS**, S7/S8 연구메모리·부모 다양화·거버넌스 포함 확장 **111 PASS**. `ruff check .`, `mypy --follow-imports=silent scripts/preregister_t4_equal_plan_comparison.py scripts/score_t4_equal_plan_comparison.py`, `git diff --check` **PASS**.
- **전체 pytest:** `pytest -q -x -p no:cacheprovider` → **448 PASS, 1 FAIL 후 중단**. 앞선 단계에서도 동일하게 발생했던 `tests/dashboard/test_fresh_original_dashboard.py::test_readonly_sqlite_bridge_matches_original_contracts`에서 과거 `state/moon-http/fresh-20261021/session-id.txt` 미마운트로 `FileNotFoundError`. 전체 suite PASS가 아니며 이번 기능의 직접 실패로 판정하지 않는다.
- 실제 신규 G1 10세대·100세대 GPT 도구 연결/자료 접근·실시장 data SHA/기간, 실모델 호출·비용/체결 증거, 미사용 독립 OOS/PIT, 물리 과거 G150 원장 삭제, 서비스 배포/실거래, 별도 독립 리뷰 **NOT RUN**. 현재 Task 0의 실 운영 데이터 미마운트 **BLOCKED**가 해소된 것으로 주장하지 않는다.

**단계 판정:** [10/16] **사전등록 프로토콜·사후 입력 변조 방지 코드 및 합성 테스트 준비 완료**. 시장·세션 미확보로 실험 실행/최종 매니페스트는 **BLOCKED**. 다음 [11/16] Task 10 실제 모델 Plan→Diagnosis→S7 연속 10→100세대: 원본 데이터/인증이 준비되지 않으면 `BLOCKED`로 별도 보고, 모의 테스트를 실제 연구로 기록하지 않는다.
