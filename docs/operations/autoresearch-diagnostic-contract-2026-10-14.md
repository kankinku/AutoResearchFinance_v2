# S2 1차 — 거래 근거에 결박된 LLM 원인 분석·실험 제안 계약

기준: 2026-10-14. [20문답](../decisions/2026-10-14-autoresearch-interview-20q.md) 6·8·9·11·14·17·18번, [전체 로드맵](autoresearch-implementation-roadmap-2026-10-14.md). **계약/사전검증 완료**, 실제 모델을 포함한 자율 세대 실행은 **아직 미구현**.

## 실제 구현 (개발 브랜치)

- `research/indicator_engine/decision_audit.py`: 기존 `core.backtest` 결과·전략·지표·체결·거래 손익·LLM용 객관적 평가 패킷을 결합한 **강화된 감사 해시**. 전체 의사결정 조건·지표값·체결 수량/비용·평가값·예시를 포함한 기록의 변조를 검출한다. 원장 해시는 로컬 재현성 체크섬이며 외부 금융데이터의 진위 검증이나 서명은 아니다.
- `research/llm/diagnostic_research.py`: `build_diagnostic_context(...)`가 검증된 감사 데이터에서 제한된 측정 컨텍스트를 구축. `diagnose_with_provider(...)`는 공급자가 `propose(context)`를 호출하여 구조화 답변을 받을 때 한 번의 검증 가능한 연구 체크포인트를 제공. `approve_diagnostic_plan(...)`에서 LLM 출력 Pydantic schema와 기존 `ResearchIntent`·`intent_bridge.apply_intent`를 사전검증한다.
- `DiagnosticResponse → ExperimentHypothesis`: 원본 감사/context/전략/데이터 해시, 실제 제시된 거래/체결/판단 ID, 원인 **가설**, 반대 설명, 예상 측정 지표와 방향, 대조군, 구조화된 수정 지시를 분리한다.
- `ValidatedDiagnosticPlan`: 설명/대안 가설/관측 ID/기준 전략/후속 Child StrategyIR와 의미 해시를 보존한다. 후속 자율 오케스트레이터가 다음 실험으로 편성하는 **제안**에 한하며 바로 평가 실행·OOS 승인·주문하지 않는다.

## 거부하는 입력 및 안전장치

- 현재 입력 컨텍스트에 없었던 ID, 다른 실행/전략/데이터에 속한 해시, 잘못된 감사 패킷, 변경된 손익·지표값, 허위 '원인 입증' 상태, 잘못된 대조군.
- 검증되지 않은 indicator/primitive, LLM Python/evaluator 패치, 존재하지 않는 IR 경로, 실행 불가능한 전략 수정, 부모/후보 semantic hash 기준 변경 없는 수정 또는 중복 후보.
- 연구 결과는 개발 데이터 반복 평가만 허용한다. 구조화된 LLM 가설은 **`UNTESTED_HYPOTHESIS`**, 독립 OOS에서의 경제적 성과는 `NOT_MEASURED`, `independent_oos_approved=false`, `broker_executable=false`.
- 검증 과정에서 공급자에게 전달하는 컨텍스트는 deep-copy로 전달한다. 원본 컨텍스트와 승인 직전 감사 원장의 해시를 재검증한다.

## 실제 데이터 기반 연결 검증

Tiingo QQQ 2020-01-02~2025-12-31의 원시 1,508개 일봉에서 학술 검증된 두 지표 `time_series_momentum`, `sma_direction`를 적용해 **판단 1,508개, 체결 11건, 청산된 왕복 거래 5건**의 원장을 다시 생성했다. 거래 ID를 근거로 '레짐 필터를 제외해 보는 대조 실험'을 제안하는 **테스트용 구조화 응답**을 주입했다. 원장·전략·데이터·context 해시가 일치하고, 변경된 Child StrategyIR가 기존 mutation validator를 통과할 때만 `VALIDATED_PROPOSAL_REQUIRES_EXPERIMENT`가 반환된다.

검증용 감사 해시: `59cd471bbcb280a06ccca7f582a72aa869f043fea10506688f07567c388d9d41`. 이는 이전 S1 원장 해시보다 해싱에 포함하는 근거 필드가 많아져 바뀐 것이다. **실제 외부 LLM API 호출, 후속 후보의 백테스트 평가, 수익 개선 및 원인 입증은 이 테스트에서 수행하지 않았다.**

## 다음 순서

1. **S2 잔여:** 손실·낙폭 에피소드별 최소 충분 통계, 감사 원장 검색/재생 API 및 연구 메모리 Evidence 저장소 연동(이번 기능은 메모리 영속화까지 연결되지 않음).
2. **S3:** 검증된 인디케이터 조합식·레짐 분기·가중치를 표현하는 타입드 `AlgorithmPlan → StrategyIR` 확대. 기본 시장 조건을 손으로 고정하지 않고 LLM이 설계하게 한다.
3. **S4:** 실제 인증된 LLM 공급자, 내구성 있는 세대 제어기, `실험→분석→후속 실험` 반복 및 중단/재개를 일관되게 연결하고 다세대 수락 테스트. 단순 mocked provider는 자율 연구 완성 증거가 아니다.

이 단계에서 보호된 core, KIS 주문, Sealed OOS, 운영 브랜치, 복구 기준점은 수정하지 않는다.


## 최종 자동 검증

- 신규 진단 계약 포함 집중 테스트: **23/23 통과** (전략 분석과 감사 기록 관련 테스트).
- 저장소 전체 회귀: `pytest -q -p no:cacheprovider` **1,308 passed, 0 failed**, 399.00초.
- `ruff check .`: 통과. `mypy .`: 통과 (**220 source files**).
- 응답 제공자(mock)의 실제 실행 검증은 1회 호출 계약·출력 게이트에 국한한다. **실제 LLM 모델을 호출해 경제적 효과나 장기 실행 성공을 증명한 것은 아니다**.
