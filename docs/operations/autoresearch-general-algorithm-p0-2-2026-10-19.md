# 범용 알고리즘 연구 엔진 P0-2 — 실제 LLM FeatureSelection→백테스트 검증

**2026-10-19 KST. 기술 하위 작업 P0-2: `COMPLETED_SCOPED`. P0 전체 감사: `PARTIAL`. 실운영 배포: `NOT_RUN`.**

## 근거·범위

- Q05/Q10/Q11/Q12/Q18. 목적: '등록'만 된 지표를 실제 연구 후보에서 실행 가능하다고 오해하지 않고, 사용자가 요청한 자유로운 알고리즘 설계 전에 `FeatureSelection → ResearchIntent → StrategyIR → canonical costed BacktestEngine` 경로를 실제로 검증한다.
- 기존 상위 로드맵 `V05 → T4 → V01~V04 → V06 → V07` 유지. T4 실제 GPT 자율 루프 증빙·신규 공식 세대 생성/장시간 실행은 이번 작업의 비목표.
- protected `core/backtest`, data/costs/integrity/evaluator/validation, OOS, 실주문, MCP URL/OAuth 불변. 기존 G350 연구 원장 변경 없음.

## 실제 변경

1. `research/llm/intent_bridge.py`: `FeatureSelection` 및 `ADD_FEATURE`(typed/legacy 경로)를 정식 실험 후보로 수락하기 전에 데이터 계약 검사. 현재 일반 OHLCV `BacktestEngine` 경로에 정렬된 피처 시계열을 공급할 수 없는 `profile`, `order_flow`, `session` 전문 데이터 계약은 `INTENT_FEATURE_NOT_EXECUTABLE` 오류로 즉시 거부. 신규 기능 검증·전문 bar adapter가 준비될 때만 별도 허가 검토. 명시적으로 `source_licenses`에 제한 조건(`BY-NC`, noncommercial, all rights reserved 등)이 기록된 출처는 `INTENT_FEATURE_LICENSE_REVIEW`로 차단. **출처 미기재가 곧 사용 허가를 뜻한다는 주장은 하지 않는다.** 기존 과거 저장된 IR을 변경하지 않음.
2. `application/catalog_service.py`: MCP `research_features()`의 기존 6개 필드·173개 listing을 하위호환 유지. 신규 읽기 전용 `capability_summary()`로 합성 데이터 프로브의 등록/계산/전문 입력/무출력 차이를 요약.
3. `application/research_service.py`: 기존 `feature_catalog`는 그대로 두고 `feature_capability_summary`를 GPT-facing 연구 문맥에 병기. LLM이 선언만 등록된 173개를 실행 가능 수로 과장하지 않도록 안내. **현재 일반 FeatureSelection 경로와 학술 `AlgorithmPlan` provider는 여전히 구분**.
4. `tests/research/test_capability_intent_bridge_p0.py`: 기본 `sma`와 외부 `vix_percentile`을 실물 StrategyIR에 반영하여 synthetic DEVELOPMENT / 비용 반영 백테스트. `VIX`의 늦게 공개된 값을 변경해도 기존 equity/trades 해시·거래가 불변인지 검증. 별도 전문 데이터 3종·제한 라이선스·typed ADD_FEATURE fail-closed, 6필드 MCP 호환성과 GPT 문맥 출처 설명 검증.

## 검증·한계

- 신규 P0-2 및 관련 IntentBridge/MCP/자율 연구 루프/ScopeLock 회귀 **66 Pytest PASS / 0 FAIL**.
- Ruff 저장소 전체 **PASS**, MyPy 저장소 전체 **281 sources PASS**, `git diff --check` **PASS**.
- **전체 Pytest NOT RUN**, 실제 GPT 연결 자동 10/100세대 실험 **NOT RUN**, 실 운영 cutover/roll-back/OAuth smoke **NOT RUN**, 별도 PIT/OOS/실전 수익·브로커 체결 정확도 **NOT RUN**. 이 작업은 연구용 안전성 개선이지 수익성 확인이 아니다.
- 샘플 E2E 두 종류가 성공했다고 173개 전체 정상 연결을 증명하지 않는다. 네이티브 일반 지표 전체의 `REGISTERED`에 대한 실행 적격성은 **P0-1 감사 결과대로 PARTIAL**. 신규 typed feature DSL/상태기계/동적 포지션 정책 미구현.
- 보호된 엔진은 건드리지 않았고 기존 Pine 코드를 연구 종족이나 전략 기본 프롬프트에 등록하지 않음.

## 코드·배포·다음

- 기능 커밋 **`0d776e0`**, 브랜치 `feat/quant-same-session-350-20261019`, `origin` Push **PASS**.
- 이번 원장/보고 변경은 별도 docs 커밋으로 기록.
- 다음: T4 실제 연결된 GPT 완결 연구의 효과 입증을 우선 유지하면서, 새 기능 개발 요청 시 **P1-1 bounded typed expression AST** 및 하위호환 v1 adapter 최소 구현을 별도 기술 작업으로 착수할 수 있다. P0의 개별 native feature 계산 parity·as-of/정렬 검증은 새로운 기능을 노출하는 시점에 계속 시행한다. 연구 원본 라이선스·OOS 게이트를 완화하지 않는다.
