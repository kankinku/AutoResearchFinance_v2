# Quant AutoResearch — 범용 알고리즘 연구 엔진 개선계획 v1.0

**날짜:** 2026-10-19 KST
**상태:** `P0_1_P0_2_DONE; P0_OVERALL_PARTIAL; P1_1_P1_2_DONE; P1_3_OPT_IN_PROVIDER_DONE; P1_OVERALL_PARTIAL; P2_P5_PROPOSED` — 기능 표현 언어 IR v2 / 주문 계층 **미구현**, 신규 공식 연구 세대 **0**, 운영 배포 **0**. P0-1·P0-2는 [각 보고서](autoresearch-general-algorithm-p0-2-2026-10-19.md)에 별도 기록.
**근거:** 기존 사용자의 20문답 Q02/Q05/Q06/Q07/Q08/Q09/Q10/Q11/Q12/Q14/Q17/Q18/Q19/Q20, 2026-10-16 확정 범위 잠금, Pine 11개 *일회성 외부 사례*.
**최상위 목표:** 기존 전략 목록을 점점 늘리는 것이 아니라 LLM이 독자적으로 새로운 계산과 판단·상태·실행 정책을 표현, 실험, 수정, 검증하는 **범용 자율 연구 엔진**.

## 0. 변경·비범위 통제

- 기존 원본 20문답 및 [확정 순서](../decisions/2026-10-16-autoresearch-20q-scope-lock-v1.md) `V05 → T4 → V01~V04 → V06 → V07`을 **변경하지 않는다**. 현재 V05는 개발 진단 완료, T4는 공식 350세대 연구 결과가 있으나 독립 GPT 자율 연구 검증과 완전한 모델 진화 효과 검증이 아직 미완료.
- 아래 P 단계는 **S3/S6/S7/S9와 T4의 미해결 Q05/Q10/Q11/Q12/Q18 하위 기능 의존성**으로 제안한 기술 단계이지 확정 제품 로드맵을 대체할 새 상위 프로젝트나 선행 요건이 아님. T4 실제 GPT 10/100세대를 임의로 미루지 않는다. 큰 범위 추가/기존 순서 변경·핵심 protected core 수정은 사용자 명시 승인 후 **신규 ADR**로만 실행한다.
- 기존 `core/data`, `core/backtest`, `core/evaluator`, `core/validation`, `core/costs`, `core/integrity`, 봉인 OOS, OAuth, MCP 기존 URL, 실주문 OFF 유지. 연구용 격리 시뮬레이터가 실주문 권한을 암묵적으로 얻지 못하도록 한다.
- LLM은 임의 Python/Pine, eval, 동적 import, 셸, 네트워크를 실행하지 않는다. 전략의 source of truth는 Typed Algorithm/Strategy IR; 출력 Python은 검증된 생성물일 뿐. Pine 전략이나 특정 지표 유형을 기본 선호도에 주입하지 않는다.
- Pine 11개는 기능 누락 탐지용 **일시적 conformance 입력**; 라이선스/저작권 기록은 유지하고 Pine 전용 importer·원본·홍보 카탈로그는 범용 도구로 치환 후 런타임에서 제거한다. 직접 파생 코드라면 저작권 고지, 배포 조건을 충족한 상태로 유지. 미확인/비상업적 허가는 별도 격리.
- 알고리즘의 복잡도는 사용 가능한 상한 내 **선택 사항**. 복잡함 자체에 가산점 부여 금지, 유의미한 개선이 없으면 단순화 허용.

## 1. 실측 기반 중복 방지 — 범용화 이전에 현재 구조의 실제 한계 확정

| 현재 코드 | 이미 존재하는 능력 | 이번 계획에서 추가할 것 |
|---|---|---|
| `strategy_ir/schema.py`, `validator.py` | 단일 레벨 AND/OR, cross/comparison, feature ref, 기본 퍼센트 risk | 중첩 수식/논리, typed state/event/risk/order policy |
| `research/indicator_engine/algorithm_plan.py` | 우선순위 있는 RegimeCase + WeightedVote, 검증된 binary indicator 기반 | 연속 수치/변형 지표, 조건 트리, 상태 전이, 국면별 다른 policy |
| `research/indicator_engine/catalog.py`, `signals.py` 및 `core/features/registry.py` | 제안→검증·등록 흐름, whitelist의 검증된 수학 계산 | LLM이 새 함수를 구성/제안해 검증 후 사용하도록 연결; 두 레지스트리의 identity·capability 정리 |
| `research/llm/intent_bridge.py`, `mutation` | typed 파라미터·조건·기능선택 변이 | AST 삽입/삭제/교체, 구조적 계승·결정 trace |
| `research/indicator_engine/strategy_adapter.py` | 개발 데이터 전략과 canonical 일봉 체결·비용 기록 | 복합 state/order의 격리 시뮬레이션, 단 현재 보호된 canonical engine 자동 변경 금지 |
| `core/features/pine_liquidity_levels.py`, `pine_cash_risk.py` | 독립 계산 부품 2개; 14개 관련 검증 이력 | 종속성을 제거하고 재사용 가능·동등한 일반 feature/policy로 연결하는 것은 추후 단계 |
| 이전 ALMA 변환 | 로컬 파일 두 개 제작 이력 | 정식 repo/Registry 등록이나 TradingView 동등성 **미확인**, '기능 완료'로 계산하지 않음 |

## 2. 기술 단계와 수락 테스트

### P0: Capability Gap Matrix / 안전한 베이스라인 (가장 먼저, 작은 범위)

**구현:** 현재 FeatureSpec→연산기→StrategyIR→T4 LLM proposal→백테스트의 실제 호출 연결도를 생성. 등록은 됐지만 계산이 연결 안 된 함수, 연구 카탈로그와 runtime registry의 중복을 상태별로 분류. 각각 `SUPPORTED_AND_EXECUTABLE` / `PARTIAL` / `MISSING` / `BLOCKED_LICENSE` 명시. 기초 벤치마크(다른 규칙 3~5개), 성능·메모리·기존 세대 해시 고정.

**합격:** 실제 LLM-facing capability 목록의 항목을 1건씩 생성→검증→컴파일→시계열 값까지 실재 테스트. 표시만 된 카탈로그 항목 실행 거부. 구 버전 재실행 결과 동일.

**비범위:** Pine 소스 port, 새 자산/데이터 조달, StrategyIR 대수술.

### P1: 타입 기반 Algorithm Expression IR v2 (작은 표면부터 순차 도입)

**구현:** 기존 AlgorithmPlan의 순서형 분기·가중 투표는 재사용. IR v1 호환 어댑터 유지. 새로운 **bounded, 순수 데이터 AST** 표현:
- `Series[float|bool]`, `Scalar`, `Event`, `State`, `Decision`, `Policy` 정적 타입과 값의 관측 가능 시각.
- 상수·OHLCV·등록 지표·사칙·min/max·normalization·rolling, shift/lag(과거만), cross, 비교, 중첩 AND/OR/NOT, 조건부 case, weighted combination.
- 상태기계는 유한 state, 명시적 initial/reset/expiry/transition 및 과거에 관측 가능한 event만 허용.
- LLM의 새 계산식은 검증된 원시 연산을 **조합**해 제안하고, 신규 외부 구현은 별도 검증/등록 후 참조. 임의 코드 문자열 평가 금지.
- 타입 불일치, 시계열 granularity/asset mismatch, lookahead, 비정상 숫자, deep tree, 무한 반복, 과도한 계산 비용은 compile-time fail-closed.
- **최소 범용성:** 동일 문법으로 모멘텀/평균회귀/국면 정책/상태 대기 전환을 작성하고, 수학식은 특정 Pine 레이블과 무관.

**합격:** 합성 가격에서 4개 이질적 알고리즘을 작성(하나는 과거 이벤트를 기다리는 상태기계, 하나는 중첩 분기, 하나는 새 지표 공식, 하나는 매우 단순한 전략). 모두 실제 `t`까지의 데이터만 관측; `t+1` 이후부터 체결. 동일 계산을 prefix-by-prefix 재생해 출력 hash 일치. 이전 IR v1 신호·거래·수익 해시 회귀 불변.

**비범위:** 미검증 live strategy migration, 무제한 Turing-complete DSL, 표본 내 성과 보장.

### P2: 범용 Feature Verification / Capability Discovery

**구현:** 사용 가능한 base operator와 검증된 feature의 input, unit, lookback, observation_ts, publication/as-of, required calendar/timeframe, parameter schema, output shape/type, license provenance, causal delay, cost 등을 기계 판독 가능한 capability manifest로 노출. `ResearchCatalog`의 `PROPOSED → VERIFIED/QUARANTINED`를 활용하되 runtime `FeatureRegistry`와 중복 구현/이름 충돌을 정리.
- LLM은 검증된 feature를 결합해 새로운 수식을 작성할 수 있음; 제안 생성과 연구용 실행 승격은 분리.
- 누락·연결 안 됨·permission 미충족 기능은 노출하지 않거나 실패 사유를 명시.
- 새 공식의 독립 reference, 여러 시퀀스/난수 seed, missing/zero volume/constant, prefix-independence, time alignment, resource bounds 테스트.

**합격:** LLM이 직접 구성한 신규 지표 1개를 격리 검증→등록→새로운 조합 전략 실험에 연결. 미검증 신규 지표는 정식 후보 실행 불가. 기존 연구 memory/source hash 변경 감지.

**비범위:** 특정 Pine 코드 이름에 의존한 엔진 기능.

### P3: 연구용 Policy·Order IR (필요성 확인 후 점진 도입)

**구현:** signal, order intent, fill, risk/position policy를 분리. 처음엔 1d + 롱/관망 + 0–100% cash-only 노출 정책으로 개발; 15m·long/short·stop/limit·OCA·분할/역방향 주문·ATR/cash/R 다중 청산은 각 기능의 체결 정확도를 검증할 수 있을 때만 별도 격리 어댑터로 확장. *기본 IR 표현력 개선이 장중 브로커 에뮬레이터 전체 재구현을 뜻하지 않는다.*
- 시간대와 DST, 미완성 봉, gap/동봉 high-low ambiguity, tick/pointvalue/currency, commission/spread/slippage, margin, max exposure/turnover, trade cooldown, risk budget 등을 타입과 이벤트로 정의.
- 동일 bar에서 stop/target 충돌 시 정보 부족을 드러내고 정책/하한·상한을 기록; 낙관적 임의 순서로 수익을 꾸미지 않음.
- 기준 일봉 canonical evaluator와 isolated 15m simulator의 결과를 섞어서 비교하지 않음; 비용·시장 정의 동일할 때만 비교.

**합격:** 합성 15m 가격에서 양방향 대기 주문의 OCA, 세션별 1회 거래, 강제 종료, gap/slippage, 포지션 크기 테스트. 기존 연구 메인 경로 불변 검증. 주문 송신 기능 0건. 원본 TradingView parity는 권한과 원본 채결 데이터가 확보된 경우 별도 검증.

**비범위:** 실거래 브로커 연결, protected engine 변경, 복잡한 주문 지원을 필수 전제 삼아 자율 GPT T4를 지연.

### P4: LLM 구조 진화 + 원인 가설·반증

**구현:** LLM은 feature selection/threshold patch 외에 typed subtree 생성/교체, 규칙 추가·삭제, phase transition 수정, 국면별 policy 배치, 가중치 및 산술식 변경, **전략 단순화**를 후보 작업으로 제출. 작업 내역에 parent vs child 알고리즘 AST diff, 의도, 어떤 거래 패턴을 바꾸려 했는지, 기대 변화, 측정된 거래 차이를 함께 기록.
- 동일 비용·데이터·research budget을 사용하는 random/local/GPT 대조군을 사전 고정. 중복/무효 변이는 진화로 셈하지 않음.
- 현실 목표: '항상 최고 성과 경신'이 아닌 이전보다 새로운 가설을 더 정확히 검증하고 다양한 유효 후보를 발견하는 능력. 수익, MDD, turnover, exposure, trade count, net of costs, market-relative metrics과 과적합/복잡성 예산을 함께 판단.
- 세대 생성→canonical 체결→LLM failure hypothesis→다음 실험 설계→불변 evidence 기록까지 1세대.

**합격:** 엔진이 ① 단순 전략 생성 ② 복잡한 새로운 구조 생성 ③ 실패 근거에서 분기/상태 수정 ④ 불필요한 복잡성 제거를 각각 **실제 거래 벡터 변화**와 함께 재현. 동일 예산 GPT 대조 및 중단·복구 후 전체 연구 연쇄 무결성 확인. 10세대 → 100세대 전환은 기존 T4 성공조건에 종속.

**비범위:** 1회 개선 관측으로 독립 OOS 수익성/GPT 우월성 선언.

### P5: Pine 제거·내재화 종료

- 초기 Pine 11개에서 얻은 **표현 요구**만 범용 conformance 테스트로 변환: 가격 레벨과 피벗 확정 지연, 유한 상태 방문 기억, 시장 국면별 규칙 변화, 정책별 손절/수량, 오더 이벤트. 테스트는 Pine 네임스페이스·특정 스크립트 계산식에 의존하지 않음.
- Pine source_gate, Pine 전용 카탈로그/importer, 전용 프롬프트는 범용 기능과 generic source/legal audit에 실제로 대체된 것이 확인된 경우 **런타임 경로에서 제거**. 미이식 아이디어/권리 문제가 남은 소스는 격리 기록으로 남기거나 정리한다. 법률상 필요한 MPL attribution, CC BY-NC-SA notices, 테스트 재현 근거는 보존한다.
- 잔여 사용자 요청/검증 재현에 필요한 실제 원본은 적용 라이선스와 보관 정책에 따라 별도 접근 통제한 증거로 보존할 수 있다. 원본 전략을 LLM 프롬프트의 기본 예시·우선 종족·전략 선택 편향에 포함하지 않는다.

**합격:** Pine 관련 런타임 패키지가 없어도 범용 LLM 후보 4유형 end-to-end 통과, 이전 v1 회귀 불변, 권리 고지/출처 누락 0건, source-specific preference prompt 없음. 폐기 시기 전까지 원본 삭제 금지.

## 3. 선행 게이트 / 현실적 진행 순서

**승인된 제품 단계(절대 변경 없음):**
`V05 (완료: 개발 진단) → T4 실제 모델 자율 10/100 검증 → V01~V04 외부 PIT/OOS → V06 paper-only → V07 GO/NO-GO`.

**이번 개선계획의 하위 기술 단계:**
- **착수 가능:** P0 baseline/중복분석 + T4의 필수 기존 기능 정합성 점검. 현재 T4의 실제 자율 연구 입증을 연기하지 않는 범위.
- **P1 최소형 → P2 최소형:** Q05/Q10/Q11/Q12 직접 기능 gap을 T4 연구에서 재현 가능하게 하는 최소 안전 표현 능력만 구현. 크게 확장해야 하는 항목은 근거·비용/회귀 위험을 별도 표기.
- **P3:** P1/P2의 한계를 실제 실험에서 관측했을 때 사용 사례별 확장하고, 바-내 체결이나 외부 브로커 모델 개입은 별도 승인.
- **P4:** 이미 존재하는 S7/T4 루프와 연결해 구조 진화 검증. 첫 통합부터 동일 예산 random/local 대조, 실패 분석 반증을 동봉.
- **P5:** 실제 엔드투엔드 동작 이후에만 Pine 임시 잔재 정리.

**중단/롤백:** 어떤 기능이든 기존 v1의 replay/equity/hash 결과를 변경하거나 T4 완료율을 훼손하면 기능 플래그 OFF/롤백. 이전 증거 해시 덮어쓰기 금지. 지속 테스트 결과 `PASS/FAIL/BLOCKED/NOT_RUN` 구분.

## 4. 성공 지표 (목표값 제안 · 자동 성공 주장 금지)

| 계층 | 성공 증거 |
|---|---|
| 기능 사용성 | LLM capability manifest에 표시된 선택지가 실제 end-to-end 평가될 것; 제안/등록/실행 상태 서로 일치 |
| 자유도 | 단순·중첩 분기·유한 상태·새 수식·국면별 정책의 서로 다른 알고리즘 생성; 유효한 구조 변형 뒤 결정/거래 변화 확인 |
| 계산 무결성 | prefix-by-prefix 동일, 1-bar confirmed event lag, 미래정보·미완성 봉 참조 거부, 타입/자원 제한 우회 거부 |
| 실행 정확도 | 고정 seed 비용/체결 정책 재현, 동일 bar 충돌/gap/OCA 위험 명시, 주문 capability는 격리 |
| 하위호환 | 이전 알고리즘·성과/원장 SHA 불변, v1→v2 번역 선택 시 동일 시계열·거래 관측 |
| 자율 효과 | 실제 connected GPT 10→100 완결 연구와 구조 변형·가설/통제실험·다음 계획 원장; 동일 예산 random/local과 구별 |
| 수익성 | 비용 차감 QQQ/다자산 비교와 독립 PIT/OOS 및 V06 검증은 기존 단계에서 별도 판정. 연구 기능 완성과 혼동하지 않음 |
| Pine 내재화 | Pine 런타임 의존 0, 특정 Pine 소스에 대한 기본 LLM 편향 0, attribution/라이선스 문제 없음 |

## 5. 첫 실제 구현 후보 (승인 범위 확인 후)

**P0-1 'LLM이 쓸 수 있는 것 vs 표기만 된 것' 자동 검사**를 우선 진행. 실험 생성기→선택 후보 식별자→register/verify→signal replay→분석 원장 간 하나의 기능 계약을 검증하는 작은 통합 테스트를 작성한다. 이는 보호 core·실거래·기존 StrategyIR 스키마 변경 없이 가능하다. 통과 후 **P1-1 최소 typed expression node**(binary mathematical/boolean, explicit lag)로 넘어간다. 실제 주문·Pine 원본을 이식하는 작업으로 출발하지 않는다.

다음 고정 제품 단계는 여전히 T4 실제 GPT 진단/진화 반복 검증이다.
