# Quant AutoResearch — P1-3 범용 전략 제안→비용 반영 백테스트 연결

**2026-10-20 KST · P1-3 `ISOLATED_OPT_IN_PROVIDER_PASS` · P1 통합 전체 `PARTIAL` · 실운영 `NOT_DEPLOYED`**

## 이번 작업 계약

| 항목 | 근거 / 실제 수행 |
|---|---|
| 단계·기원 | P1-3; 원래 사용자 Q05/Q06/Q10/Q11/Q12/Q18, T4(S4/S5) 개발 의존 |
| 사용자 가치 | Pine 기반 특정 전략을 따라 하는 대신 LLM이 수학 표현식과 유한 상태기계를 독창적으로 조합한 **진입과 청산 계획을 타입 기반 제안**할 수 있음 |
| 변경 경계 | 독립 `research/indicator_engine/general_plan.py` + 테스트만. 기존 StrategyIR/AlgorithmPlan/Backtest/Costs/Data/Integrity/OOS 수정 없음 |
| 수락 기준 | 샘플 공급자가 typed Plan 생성→인과성·형식 검사→실제 StrategyIR v1 생성→기존 비용 포함 일봉 백테스트. 상태 trace·전략·데이터·리플레이 재검증. 기존 S3 제공자 회귀 보존 |
| 금지 | Pine 원본 실행·복사, 임의 Python/DSL eval, 원본 350세대 원장 변경, 실거래, 봉인 OOS, 운영 MCP URL/OAuth/32 tools 변경 |

## 구현 상세

**기능 코드:** [`general_plan.py`](../../research/indicator_engine/general_plan.py) — 기존 [P1-1 Expression](../../research/indicator_engine/expression_ir.py)과 [P1-2 State Machine](../../research/indicator_engine/state_machine_ir.py), 기존 [AcademicStrategyAdapter](../../research/indicator_engine/strategy_adapter.py)를 재사용.

1. `GeneralResearchPlan`: `entry`, `exit` 각각 독립적으로 `expression` 또는 `state_machine`를 선택할 수 있는 `SignalDefinition`. 새 수학·중첩 논리, 조건 뒤 대기·상태 전환 모두 동일 인터페이스. 포지션은 아직 **100% cash-only long/flat**; 새 주문 정책·동적 사이징 미지원.
2. `build_general_plan_context` + `compile_provider_general_plan`: **명시적으로 호출한 경우에 한해** 외부 구조화 계획 공급자에게 JSON 스키마, 일반 연산 기능, 원시 OHLCV source명, 범위 제한을 안내하고 JSON 구조를 검증. 원시 가격/OOS/비밀키를 공급자에게 전송하지 않음. 특정 Pine 전략 추천 목록 없음.
3. `compile_general_research_plan`: 개발전용 1d 미국 주식·단일 자산·최대 20,000봉 범위. 검증된 수식·상태기계가 각 봉 종료에 계산한 신호를 `plan_entry/plan_exit` 이진 시계열로 내리고, 기존 StrategyIR v1의 `feature_values`에 정합 매핑. 기존 backtester가 **다음 봉 시가**에 주문하는 계약을 재사용. P1-1/2 source whitelist·타입·복잡도·비인과 데이터 거부를 재사용.
4. `CompiledGeneralResearchPlan`과 `ResearchSignalReplay`: plan/definition/state trace/data/시계열/decision_timestamps/next-open 실행 계약 해시 보존. 실행 전에 원본 plan+market으로 재컴파일·검증하여 호출자가 바꾼 신호/정책/데이터를 거부. 기존 `evaluate_compiled_development`에서 같은 비용 모델로 기존 백테스트를 실행.
5. `AcademicDevelopmentResult`는 비PIT 연구용이며 브로커 주문/임의 후보 자동 승격/OOS 승인 불가. 이 기능을 operational GPT director/MCP toolchain, 실제 GPT 10/100세대, Feature Registry 또는 기존 `AlgorithmPlan` provider의 기본 구현으로 등록하지 않았다. 따라서 **'LLM 호출 준비가 된 opt-in 구조'이지 운영 GPT 자율 진화 경로에 실제 배포/사용된 것은 아님.**

## 통과한 증거

**테스트:** [`test_general_plan_provider_p1.py`](../../tests/research/test_general_plan_provider_p1.py)

- 실제 API 모형 제공자가 중첩 연산·교차·rolling 조건식으로 진입하고 별도 종료식을 만드는 전략을 제안; 비용 반영 canonical replay 실행.
- 상태기계 진입 + 수식 청산, 또는 **상태기계 진입 + 독립 상태기계 청산**을 모두 실행. 상태 trace hash 정합 확인.
- 모든 실행 거래의 시가가 **이전 확정봉 신호 이후**인지 검사. 동일 데이터 재생 equity hash/trades 결정론 유지.
- 미래 최종봉 변경은 이전 봉 신호를 수정하지 않음. 개발 자료 해시 변경/plan hash·벡터 변경/비허가 데이터·속임수 모델 복사/미검증 feature/허가 범위 초과/Python 코드 injection 거부.
- 기존 S3 `AlgorithmPlan` 코드와 실행 경로의 재생 및 ScopeLock 회귀도 통과.

**검증:** 신규+관련 테스트 **137 Pytest PASS / 0 FAIL**, 전체 Ruff **PASS**, 전체 MyPy **284 source PASS**, `git diff --check` **PASS**. 전체 저장소 Pytest **NOT RUN**; 독립 실제 GPT 연구, 실운영 HTTP OAuth cutover·roll-back, 봉인 OOS/벤더 PIT/실거래/수익성 검증 **NOT RUN**.

**기능 Git SHA:** `2da18dc`, 브랜치 `feat/quant-same-session-350-20261019`, GitHub origin **PUSH PASS**. 별도 작업 기록 문서/원장은 추가 후속 커밋에 기록.

## 남은 작업 / 다음 우선순위

- **P1 범용 구조 기능은 'opt-in 개발판 연결'까지 확인**, 실제 연결된 ChatGPT MCP 자율 연구가 이 새 모듈의 전략 계획을 제출·학습·변형·상속·실험하도록 하는 운영 경로는 미구현. 새 지표 자동 검증/승격(P2), 주문·위험 정책(P3), 구조적 자율 진화(P4), Pine 흔적 제거(P5)도 미착수.
- **고정 제품 단계 우선:** V05→**T4 실제 연결 GPT 10→100세대 및 동예산 대조/중단 재개 증거**→V01~V04→V06→V07. 신규 개발만 반복해 T4 진화 검증을 무한정 미루지 않는다.
- 후속 기술 작업은 P2 검증된 신규 계산식 source 계약 노출 또는 P4 LLM 구조 Mutation 도입이지만, 실제 모델 T4 운영 검증 상태를 확인하고 필요한 최소 범위로만 수행. 실거래 OFF 불변.

**성과 수익/알파 개선 주장 없음. 신규 공식 세대 0.**
