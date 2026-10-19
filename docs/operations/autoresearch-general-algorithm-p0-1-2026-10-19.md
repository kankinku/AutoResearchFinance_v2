# 범용 알고리즘 연구 엔진 P0-1 — 기능 선언·계산·LLM 노출 구분

**2026-10-19 KST / P0-1 COMPLETED · P0 전체 PARTIAL · T4 기존 순서 불변**

## 수행 범위

- 기존 `research/indicator_engine/algorithm_plan.py`의 검증된 학술 지표 → LLM provider context → typed `AlgorithmPlan` → 체결/비용 백테스트 경로는 **기존 기능**으로 확인. 신규 구현이 아니라 통합 회귀 검사.
- `research/indicator_engine/capability_audit.py`에 읽기 전용 P0 감사 코드 추가. **두 종류 표면을 혼동하지 않도록 분리**:
  1. `research_feature_specs()`의 일반 FeatureSpec 등록 선언 및 560봉 synthetic 계산 프로브
  2. 별도 `ResearchCatalog`에서 실제 `build_algorithm_plan_context()`가 노출하는 VERIFIED academic signal과 650봉 synthetic 개발 데이터의 실행값
- `tests/research/test_capability_audit_p0.py`: 선언만 REGISTERED인 기능의 전수 허위 '전략 실행 가능' 판정 방지, 별도 profile/orderflow 입력·외부 시계열 분리, 제한 라이선스와 미지원 연산 실패 격리, 미검증 academic signal의 노출 거부. 추가로 기존 provider를 통과하는 3가지 단순/가중/2국면 계획의 비용 백테스트 재생, **기존 연구 계약의 정식 이전 해시** 보존.
- 상세 machine-readable 근거: `docs/operations/evidence/quant-validation-20261019/p0-capability-audit.json`.

## 측정 결과 (반드시 맥락과 함께 해석)

| 구분 | 결과 | 의미 |
|---|---:|---|
| 일반 FeatureSpec 선언 | **173 REGISTERED** | 'LLM에서 모두 실행 가능'이 **아님** |
| 일반 OHLCV synthetic 값 관측 | **135** | 로컬 수치 계산 부분 점검일 뿐, 레지스트리→GPT→체결 E2E 아님 |
| 전부 None | **12** | 이 샘플에서 유효 출력 미관측; 실제 결함/초기화/데이터 형태는 **추가 분석 필요** |
| 외부 series 데이터 필요 | **14** | 현재 OHLCV-only 프로브 대상 아님; 별도 as-of 검증 필요 |
| specialized profile/orderflow/session | **12** | 별도 자료 계약·bar alignment 필요; 여기서 실행 완료로 표기 금지 |
| 학술 카탈로그 synthetic fixture | **7 중 VERIFIED 3개** | 3개만 temp DB에 검증 등록한 **독립 fixture**, 실제 운영 등록 수가 아님 |
| academic provider 실행 적격 | **3개** | 위 임시 VERIFIED 3개 모두 계산 관측; 타 후보 4개는 미노출 |
| 타입 기반 plan E2E 변형 | **3/3 PASS** | 3개의 계획을 provider→IR→costed replay까지 실행, 성과 향상 주장은 하지 않음 |

**주의:** native 행의 `llm_exposed=false`는 **해당 감사 대상 학술 `AlgorithmPlan` provider의 노출과 연결되지 않았다**는 뜻일 뿐, `research/llm/intent_bridge.py`의 다른 변이·FeatureSelection 경로에서 어떤 기능도 선택하지 못한다는 전역 판정이 아니다. 후자의 진짜 `FeatureSpec → Intent → canonical backtest` 경로는 **P0-2 확인 대상**이다. synthetic 가격이 실제 PIT/독립 데이터 신뢰도를 증명하지도 않는다.

기존 synthetic academic plan 고정 해시(코드 변경 전 확보)를 `test_existing_typed_plan_baseline_hashes_remain_identical`에서 비교: plan `da5fcf07...`, strategy `34d07083...`, replay `1e79ec6a...`, equity `e89d510c...`, 거래 4회. **회귀 PASS**. 이는 이전 생산 G350 전략 원장의 검증을 대신하지 않는다.

## 구현·검증·배포

- 기능 Git SHA `e66a660`, `feat/quant-same-session-350-20261019`, GitHub origin **PUSH 확인**.
- 표적 Pytest **34 PASS**(P0+AcademicPlan+FeatureCatalog+ScopeLock), 신규 초기 RED→GREEN 확인.
- Ruff 전체 **PASS**, MyPy 전체 **281 소스 PASS**. `git diff --check` **PASS**.
- 전체 저장소 pytest **NOT RUN**; 실제 GPT 자동 10/100 루프 **NOT RUN**; 외부 PIT/OOS·TradingView parity·실거래 **NOT RUN**.
- 코드 변경은 `research/indicator_engine/capability_audit.py`, 테스트 1개, synthetic 감사 evidence 1개뿐. 운영 서버 restart, OAuth, 기존 MCP URL, 보호 core, 세대·원장, 실주문 권한 변경 **없음**. 새로운 공식 세대 **0**.

## 후속 필수 작업

1. **P0-2**: `research/llm/intent_bridge.py` / `FeatureSelection` / `BacktestRequest` 경로의 실제 LLM 노출·타입 검증·런타임 사용 가능 행렬 확인. 표시와 실행이 엇갈리는 기능만 증거 기반으로 분리/차단. P0-1의 173개 모두를 재등록하거나 임의 승격 금지.
2. P0 전체 수락 기준 확인 후 작은 `P1-1` typed 연산 노드/정적 범위·시간 검증. `AlgorithmPlan` 기존 분기·가중치 중복 구현 금지.
3. **제품 단계 고정:** V05 완료(개발 진단) → **T4 실제 연결 GPT 자율 연구 검증 계속** → V01~V04 → V06 → V07. 범용 표현력 작업으로 T4 완료를 임의 지연하지 말 것.

**비목표:** Pine 직접 이식, 임의 Python 실행, 스키마 v2 활성화, 거래소 주문, 브로커 실행, sealed OOS 접근, 수익률 개선 주장.
