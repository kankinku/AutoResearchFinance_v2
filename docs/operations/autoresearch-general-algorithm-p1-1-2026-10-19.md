# Quant AutoResearch P1-1 — 범용 Typed Expression IR 최소 구현

**2026-10-19 KST · P1-1 IMPLEMENTED (ISOLATED ONLY) · P1 전체 PARTIAL · T4 실제 GPT 장기 검증 미변경**

## 기존 목표 / 범위

20문답 Q05/Q10/Q11/Q12/Q18을 충족하기 위한 하위 기술 단계. Pine 전략 전문·지표 원본을 엔진에 넣거나 해당 전략을 기본으로 추천하지 않고, **새로운 계산식과 복잡한 조건을 LLM이 구조화된 데이터로 표현할 수 있는 연산 언어**의 최소형을 추가한다.

원래 제품 개발 순서는 **V05 → T4 → V01~V04 → V06 → V07** 불변. 350세대 기존 성과/원장 불변. protected core/data, backtest, evaluator, costs, integrity, validation, sealed OOS, OAuth/MCP URL, 실주문 OFF 불변.

## 구현된 코드 / 계약

- [`research/indicator_engine/expression_ir.py`](../../research/indicator_engine/expression_ir.py) — Pydantic typed recursive JSON expression tree + 고정 연산 whitelist: const, source, add/sub/mul/div, min/max, 숫자 비교(lt/le/gt/ge/eq), boolean and/or/not, if_else, lag(과거만), rolling_mean, cross_above/cross_below.
- 정적 타입 `number/boolean`; 선언된 source 외 참조 불가. 각 연산 arity/type 엄격 검사, if_else 두 분기 동일 타입, bool 숫자 암묵 혼용 거부. 숫자 문자열과 정수형 기간에 대한 위험한 암묵 변환 차단. 불필요 키/미등록 연산/Python 문자열 코드 거부. 타입이 다른 eq 차단.
- 제한: 최대 **64 노드, 8 중첩 단계, 누적 과거 500봉, 계산 대상 20,000봉, 32 source 선언**. 비정상/무한 숫자·불일치 길이·잘못된 series 타입·변조된 compiled fingerprint 거부. 0 나누기는 `None`, 결측을 매수 신호로 간주하지 않음. rolling_mean은 1봉당 증가 업데이트로 계산. 신호가 있는 봉은 **종가 확정 후 t+1 시가** 실행만 허용된다는 실행 계약을 기록(실제 거래는 호출하지 않음).
- `compile_expression`, `evaluate_expression`, `signal_vector` + `development_signal_vector` (US equities·일봉·단일 종목·DEVELOPMENT·OHLCV만). 외부 series·미검증 feature·PIT 불확실한 데이터는 해당 개발용 어댑터에서 거부. 별도로 자료가 주어진 이론상 계산 엔진 자체는 소스의 공개 시각을 인증하지 않으며, PIT 보장은 향후 검증된 data adapter의 책임.
- AST와 source 계약에서 정의 해시를 계산하고 재생 시 integrity 재확인. **기존 `AlgorithmPlan`/WeightedVote와 `StrategyIR v1`은 교체하지 않음.** 현재 자동 GPT/MCP 프롬프트/FeatureRegistry에 이 새 연산자를 활성화하지 않았음.

## 독립 검증

- [`tests/research/test_expression_ir_p1.py`](../../tests/research/test_expression_ir_p1.py) — 중첩 수학 조건, 과거 라그, 교차, if_else, rolling, 결측·0분모·NaN·외부 자료·변조·무한/깊이 입력의 fail-closed.
- 단순, 이동평균 기반, 중첩 논리/과거 비교, crossover 기반 **4개의 구성이 서로 다른 신호에 대해 prefix-by-prefix 비미래 참조 검사**. 마지막 봉 값 변경 시 이전 신호 불변.
- 연구 synthetic DEVELOPMENT에서 **새 expression의 boolean vector→기존 StrategyIR feature_values→canonical 비용 반영 BacktestEngine** 실험 경로 연결. 거래는 전부 이전 봉의 확정 신호에 따른 다음 봉 시가 체결; 해당 실험은 **테스트에만 존재**하고 새로운 전략 type이나 Registry를 영구 등록한 것은 아님.
- 표적 연구 IR·AcademicPlan·IntentBridge·P0·ScopeLock **75 Pytest PASS**, Ruff 관련 및 저장소 전체 **PASS**, MyPy 관련 PASS 및 저장소 전체 **282 sources PASS**. 기존 v1 해시 회귀는 P0 기준 검사에 포함.
- **전체 pytest NOT COMPLETED:** 시도했으나 약 100초 내 전체 실행 완료되지 않아 중단(상태 `INTERRUPTED`, 전체 PASS 주장 금지). 독립 GPT 자율 10/100, paper, PIT/OOS, 실거래 실행 **NOT RUN**.

## 결정 및 미완료

**이 단계는 표현식 엔진의 최소 구현으로 범위 제한.** `State/Event` 유한 상태기계와 별도 `Policy/Order` typed IR, LLM의 구조변경 mutation, verified feature registry 기반 자유 신규 공식의 운영 노출, 실제 연구 세대/성과 개선은 아직 미구현이다. 표현식 모듈 자체만으로 과최적화 감소, 실전 수익률, 완전 자율 GPT 연구 효과를 입증할 수 없다.

**다음 작업:** 본제품 T4 실제 GPT 완결 세대·동일 예산 무작위 대조 검증 우선은 그대로 유지한다. 범용 언어 확장 후속으로는 P1-2 상태기계/Typed 조건 블록 + 검증된 provider 연결의 최소 허가 경계를 별도 회귀·PIT 검증 후 고려. 출처 불명 원본 Pine 이식/전략 추천 편향/임의 Python eval 및 보호 코어 변경 금지.

## 코드

- 기술 기능 커밋 `879ae33` 및 타입 엄격화 후속 커밋은 Git history 참조.
- 문서 및 최종 마스터 원장 커밋은 별도로 반영한다.
