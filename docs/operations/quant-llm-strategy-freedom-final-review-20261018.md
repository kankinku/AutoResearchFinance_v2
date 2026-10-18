# Quant AutoResearch — F0~F7 최종 기술평가와 현실적 수정안

기준일 2026-10-18 KST. 결과: **방향은 조건부 채택, 기존의 F0→F7 대형 순차 개발은 수정 권고**. 본 문서는 리뷰 및 후속 권고이며 제품 코드/세대/실주문/OOS 상태를 변경하지 않는다. 원래 20문답 Q05, Q07, Q10, Q11, Q17, Q20과 scope lock을 유지한다. 직전 전수조사 원본은 quant-llm-strategy-freedom-full-audit-plan-20261018.md.

## 현실적인 목표 판정

1. LLM이 지표를 구성요소로 사용해 자유형 알고리즘을 새로 만들고, 전략·규칙·가중치·위험관리·비중을 변경하는 연구 엔진은 **구현 가능**.
2. 한 모델이 100세대 이상 계획·백테스트·원인 분석·대조실험·계승을 연속 수행하는 시스템은 **조건부 가능**. 기존 GPT↔MCP에서는 ChatGPT 호출자가 있어야 실행되므로 서버 단독 무인 추론/지속 스케줄링을 자동 달성했다고 주장할 수 없다. 서버 무인 실행은 별도 허가된 제공자/호출·예산 모델이 필요하며 기존 설정은 변경하지 않는다.
3. 시장에서 실현 가능한 순수익 알고리즘 발견은 **불확실**. 2020~2025 QQQ 비PIT 개발 반복, 복합지표 수 증가, GPT 자율 연구 구조는 수익성을 보장하지 않으며 독립 OOS/PIT 및 실체결 순수익 검증 전에는 경제적 GO 금지.

## 먼저 수정할 핵심 결함

| 문제 | 실제 근거 | 필수 수정 |
|---|---|---|
| 정책 표현과 실제 체결의 불연속 | core/backtest/engine.py의 단일 자산 정책은 pending entry/exit와 정적 risk.position_size_pct만 사용하고 목표 비중으로의 부분 리밸런스 의도가 없다. strategy_ir/compiler.py의 생성 코드는 유효한 동적 실행기가 아님. | F2 새 AST에 앞서 **정식 실행 계약** 정의: 장마감 기준 시각, 거래 가능 다음 시각, 종목, 목표 비중, policy ID, 의사결정 근거 해시를 가진 typed PolicyDecision. 다음 시가에 cash/holdings와 목표치 차이만 비용 포함 체결하는 versioned canonical evaluator가 필요. v1 기존 체결·비용·equity golden 동일성 필수. |
| 지표 173개=173개 검증완료 오판 | 실제 QQQ 1508봉 계산: 135 실값, 12 전부 None, 5 일반 계산 예외, 21 별도 입력. 전부 등록됐어도 독립 수치·prefix·시점 검증 완료 아님. 특수 지표 day_of_week의 구현이 row index modulo 7이라 실제 요일을 계산하지 못함. | 173개마다 READY/수치검토/데이터부족/격리 상태 공개. 초기 Slice에서 실제 검증된 소수 지표부터 연결; 12개 계산 결함, 특수 input adapter, macro/as-of 데이터는 순차 해결. 외부 원본 없는 지표를 임의 데이터로 대체하지 말 것. |
| 전기능 선행 구현 시 scope creep | 기존 F1 all indicators→F2 거대 AST→F3 executor→F4 GPT 구도는 통합 버그를 늦게 찾음. | 초기 몇 지표 + 몇 연산자 + target position + 실제 S2/S7 **종단간 vertical slice**를 먼저 완성, 그 후 표현력 확장. |
| 중복 실험·세션 경계 | 67개 계승세대가 같은 feature set을 사용; 새 signal vector 미지원. S7 중복 매매 신호는 뒤늦게 INTERRUPTED, 100세대 한도 뒤 부모/기억 이월 인증 부재. | GPT 시범 테스트 이전에 feature recompute/replay, duplicate preflight 비중단·세대미소모, 소스 세션 StrategyIR/S7/기억 해시 계승 구현. |
| 다양성 탐색이 뒤로 밀림 | 최고 부모 근처 반복/임계값 튜닝으로 겉보기 세대 숫자는 커져도 새 알고리즘 family 부재. | 초기부터 from-scratch(신규 알고리즘) / inherited mutation / 가설 반증 arm을 분리·집계, 행동 다양성은 실제 거래와 indicator dependency 그래프로 판단, 단순 family label이나 IR hash만으로 평가 금지. |
| 누출·과최적화 제어가 뒤쪽 | 일반화 전제 없는 100+ 개발 실험에서 최고 수익률만 선택하면 탐색이 많을수록 편향 상승. | prefix/holdout/warmup/typed unit/next-open leakage tests 및 전체 후보·실패·미계상 S7 원장을 GPT 첫 연구 전 도입. 통계 보정(DSR/PBO)은 시도수/수익배열 등 충분한 입력 있을 때만 계산, 최종 OOS를 반복 탐색에 사용 금지. |
| GPT의 실제 효용 입증과 기능 시연 혼동 | 10가지 IR 예제를 생성한다고 실제 서로 다른 경제적 전략·실측 개선을 입증하지 않음. | 표현 범위, 실제 다른 executions, 후속 가설 대응, 비용·risk-aware benchmark, 동 예산 random/local 비교, 독립 PIT/OOS와 분리된 성공 단계 운영. |

## 수정된 실행 순서 (F0~F7 범위 유지)

| Gate | 작업 | GO 조건 |
|---|---|---|
| G0 / F0 | 기존 실행 및 증거 SHA golden 고정, v1 schema/수수료/매매원장 replay, canonical target-position Decision 계약 정의 | 이전 G100 local S7 100개/체결/비용 변경 0, MCP/OAuth/실주문 off 보존 |
| G1 / F1 일부+F2 일부+F3 일부 | 계산값을 독립적으로 점검한 소수 feature + 타입형 비교/AND/OR/전략 Switch/WeightedBlend + 안전 비중 변경 + next-open canonical 체결 이어 붙이기 | 현재 v1 0%/100% 재현, target 25%→65% 리밸런스·전환 때 부분 매매/현금/비용/시가/정책 근거 재현, 불완전 시점 데이터 fail-closed |
| G2 / F4 일부+F5 최소+F6 필수 | GPT from-scratch 구조 설계, 지표 교체, 다른 exit/위험 정책, trace 기반 진단/S7과 다음 설계, duplicate preflight·세션 계승 최소 구현 | 실제 GPT 1개 신규 지표를 기존 부모 signal 벡터와 다르게 계산→새 체결→S7→다음 계획, 독립적인 작동 기제의 전략 3가지, 먼저 5~10 진짜 GPT 세대 성공, 실험 중 중복·재시작으로 잘못 늘어난 세대 0 |
| G3 / F1 나머지+F2/F3 확장 | 12 null 수치 검증/교정, 5 specialized, 21 missing external as-of/availability 분기, expression operators와 추가 PolicyNode/PortfolioNode, data 허용 시 multiasset | 173개 각각 독립 참조·자료·법적 이용·시점 및 계산/격리 상태 명시; 외부 미확보 입력은 BLOCKED 처리. 동적 sizing·hold 상태 전략 변경·다수 정책/자산별 비용 정합성 |
| G4 / F5+F6 전체 | 품질다양성 archive, 실패 기억, bounded 탐색 예산·arm 배분, 회귀·상관/타임윈도 분석, feature/version/as-of cache, 강건 비용·복수 비교 통계 | 원래 우수 부모 외 후보 계열이 실제 생성, 유효 트레이드 변동 관찰, cold/warm cache bitwise parity, 총 시도 원장 완결, 100세대 세션 rollover 해시 유지 |
| G5 / F7 | stage/rollback 전수 후 20→100 세대 확대, dashboard에 전략 AST 종류·지표실행률·family·효과·MDD·거래수·QQQ 같은 위험/노출 비교 표시 | 각 세대 ChatGPT plan, canonical fill, 모델 diagnosis, S7, evidence hash 100% 기록; 실질 모델 우월성은 대조시험으로 별도 확인. PIT/OOS/실수익·무인 서버 모델 호출은 별도 승인·검증 |

최상위 승인 단계 V05→T4→V01~V04→V06→V07은 변경하지 않는다. 보호 코어에 대한 LLM 쓰기는 계속 금지한다. 다만 필요 시 **엔지니어가 검증된 새 버전의 canonical target-position 경로를 개발**할 수 있어야 하며, 기존 evaluator를 별도 임의 벤치마커로 교체하는 것은 금지한다.

## GO/NO-GO 정의

- 표현만 자유로워지는 작업은 **NO-GO**. 반드시 새로운 지표/조건/목표 비중이 실제 다음 시가 체결·비용·PnL에 영향을 준 것을 실 GPT와 S7로 증명해야 한다.
- 173개 카탈로그 수가 실제 계산검증과 증거 확보를 의미하지 않는다. 비계산/데이터없음은 정식 사유로 거절하면 정상.
- 같은 데이터를 반복해서 높은 수익이 나와도 과적합 가능성이 더 높아질 수 있다. GPT > 동일 예산 랜덤/local 우월성, QQQ 위험조정 초과성과, 반복 독립 OOS 실수익은 각각 **별개의 미증명 목표**.
- 완전 무인 실행은 현재 ChatGPT MCP alone으로 불가능. 호출 주체, 자격·예산·재기동·이전 context 제공의 현실적인 외부 실행 지원이 확인되지 않으면 UNATTENDED_NOT_VERIFIED.
- 사용자가 제시한 if(A,B)→전략 전환은 한 예시만 제공. Switch/WeightedBlend/RiskOverlay/StateTransitions/부분 목표 변경/새 합성 지표·새로 도출한 policy를 모두 같은 typed engine에서 자유롭게 결합하는 것이 목적.
- 임의 Python/네트워크/OS 코드를 LLM에게 실행시키지 않으며, 데이터/가격/비용/evaluator/키/주문권한 수정 불가.

## 검토에 사용한 외부 자료

- QuantConnect LEAN algorithm framework의 PortfolioTarget 계약과 alpha/portfolio/risk/execution 분리: https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview
- Freqtrade lookahead/recursive analysis: https://docs.freqtrade.io/en/stable/lookahead-analysis/ 및 https://www.freqtrade.io/en/stable/recursive-analysis/ . 재귀적 EMA 등은 시작 길이에 따른 초기 잔차가 생길 수 있어 항상 0오차를 강제하지 않고 허용 오차/워밍업을 정의.
- Microsoft Qlib feature-expression cache: https://github.com/microsoft/qlib/blob/main/docs/component/data.rst
- Selection-bias DSR: https://doi.org/10.3905/jpm.2014.40.5.094 ; PBO: https://escholarship.org/uc/item/4w1110bb

## 리뷰 실행·다음 단계

읽기 전용 저장소 소스, 기존 사용자 20문답/범위잠금, 직전 QQQ 173개 전수 계산 결과와 공식 외부자료 대조. **제품 코드 미변경, 신규 백테스트 세대 0, GPT 실제 전략 개발 0, 전체 pytest/OOS·운영 배포 NOT_RUN**. 다음 작업은 goldens + typed PolicyDecision interface로 시작하는 **G0→G1 vertical slice**; 진짜 GPT S2/S7 한 회를 통과하기 전 F1 173개 전부 연결과 거대한 범용 인프라 개발을 선행하지 않는다.
