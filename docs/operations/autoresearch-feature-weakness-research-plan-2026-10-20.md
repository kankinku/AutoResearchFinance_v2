# Quant AutoResearch — 지표 특성 분석과 전략 약점 보완 연구 계획 v1.0

작성일: 2026-10-20 KST
상태: F0_DONE / F1_DONE / F2_DEVELOPMENT_VERIFIED / F3_F5_PENDING — F2 후속 GPT 계획 문맥 연결·G350 읽기 전용 근거 분석 완료, 운영 배포·신규 세대 실행 없음.
범위: 기존 사용자 20문답 Q02/Q05/Q06/Q07/Q08/Q09/Q10/Q11/Q12/Q14/Q17/Q18/Q20에 따른 T4 연구 진화의 하위 개선. V05 → T4 → V01~V04 → V06 → V07 순서와 기존 MCP 주소/OAuth, 실주문 OFF 유지.

## 1. 목표

현재 부모 전략이 왜 손실을 내고 어떤 정보가 부족한지를 GPT가 정의한 뒤, 사용 가능한 지표들의 장점·단점과 이전 S7 검증 결과를 비교하고, 해당 부족함을 보완할 기존 지표·조건 수정·신규 수식·전략 단순화를 연구하게 만든다. 지표는 소재이고 진화 대상은 복합 알고리즘이다. 지표를 많이 추가하거나 특정 지표를 보편적 최고 지표로 선정하는 시스템을 만들지 않는다.

최종 연구 경로:
부모 StrategyIR → 관측된 실패 패턴 → 부족한 정보 기능 정의 → 관련 지표의 실증 특성·한계 비교 → GPT의 보완 수식/구조 가설 → 원본 부모 대비 실제 비용 반영 S7 통제 실험 → 승격/기각/미결 기록 → 다음 세대에 연구 기억·검증 부모 계승.

평가에서 현재 자료에 대해 조건부 관찰된 강점·약점을 시장 전체의 불변 법칙이나 인과 증명으로 다루지 않는다.

## 2. 이미 구현된 재사용 기능

| 기존 구현 | 이미 제공하는 것 | 추가로 연결해야 할 것 |
|---|---|---|
| research/llm/loss_attribution.py (P2-1) | 체결 당시 지표값, 손실 사건, 가설·대안의 관찰 코드 | 현재 부모의 약점 분류와 기능상 부족한 정보 요구 |
| research/llm/trade_cohort_review.py (P2-2) | 청산 거래 전체의 승·패, 국면별 빈도와 예시 쌍; 인과성 미확정 | 지표별 시장 상황·반례·거래하지 않은 판단·놓친 기회 |
| research/llm/experiment_learning.py, cross_generation_memory.py, economic_feedback.py | S7 실패/성과/중복·거래변화와 다음 가설 안내 | 특정 약점–지표/수식–실측 대조–계승 부모 증거의 연결 |
| research/indicator_engine/catalog.py 및 capability_audit.py | 지표 제안/검증/등록과 계산 가능·GPT 실행 가능 경계 | 수식 출처·시점·정량 장단점 증거를 동적 프로파일에 연결 |
| expression_ir.py, state_machine_ir.py, general_plan.py | 새 수학식과 상태전이의 typed 격리 구현 | 지표가 부족할 때 새로운 수식을 설계·시험하는 경로. 현재 운영 MCP 연동 미완 |
| controlled_experiments.py, inherited_experiments.py, lineage_selection.py | 기존 비용 모델 S7 및 부모/자식 증거 검증 | 왜 지표가 도움이 될 것으로 예상했는지, 실제 보완 효과 판정 |
| academic_checkpoint_service.py | P2-1/2, S7, 경제성 요약의 LLM 연구 문맥 전달 | 필요한 지표 프로파일·약점 매칭 결과를 근거와 함께 소량 전달 |

핵심 공백은 “실패를 관찰함 → 어떤 조건을 바꿈” 사이의 “어떤 정보가 부족하고, 어떤 지표/신규 계산식이 해당 부족함을 보완할 수 있는가”라는 연결이다. 기존 코어를 새로 만들지 않는다.

## 3. 순차 구현 계획

### F0 — 현재 데이터 계약과 부족한 연결 확인

현재 GPT 연구 문맥의 loss_attribution, trade_cohort_review, paired_s7_evidence_link, economic_feedback, feature capability 목록과 원장 증거 해시를 매핑한다. 지표 등록과 계산 가능·출처 허가·실제 연구에 사용 가능을 분리한다. G350과 대표 개발 부모의 정식 해시를 변경하지 않고 읽기 전용 기준 자료로 보존한다.

수락: 어디에 원인·지표·실험 결과가 저장되며 어떤 필드가 없어서 GPT가 단순 임계값 변경을 택하는지 확인. 기존 증거 재생과 테스트 불변.

### F1 — FeatureEvidenceProfile: 지표 장단점의 경험적 프로파일

현재 부모의 거래 추적과 사용 가능한 원시 지표 계산에서 필요한 후보만 프로파일링한다. 최초에는 서로 역할이 다른 verified 지표 3~5개를 대상으로 시작하고 전체 173개를 자동 분석하지 않는다.

프로파일 최소 필드:
- feature_id, parameter/formula/source hash, dataset/market/timeframe, observation/as-of 계약과 라이선스·실행 가능 상태
- 역할 가설: trend / momentum / volatility / reversal / custom (타입상 제한된 분류가 아니라 검색 용도)
- 조건부 관찰: 상승·하락·횡보, 고·저변동, 진입/청산 당시 신호 분포, 승리·손실·무거래 구간
- 지표 반응 지연, 노이즈/잦은 전환, 결측·불안정 구간, 다른 지표와 신호 일치·조건부 추가 정보
- 장점·단점의 근거가 된 trade/decision ID, 표본 수, 반례, 불확실성, evidence hash, OBSERVED_NOT_CAUSAL 표기

핵심: 단독 수익률 높은 지표가 아니라 부모의 특정 약점을 보완할 정보를 제공하는가를 측정한다. 청산된 거래만 보면 보이지 않는 NO_ENTRY_SIGNAL 판단도 포함한다. 거래 시점 이용 가능한 수치와 사후 결과 라벨(수익·손실·보유기간·미래 고가/저가)을 엄격히 분리한다.

수락: 동일 자료 재생 결정론, as-of/lag 불일치·사용 불가 기능·해시 변조·표본 부족은 안전 처리. 프로파일을 거래 신호로 직접 실행하거나 거래 권한을 주지 않음.

### F2 — WeaknessHypothesis + Weakness Matcher: 지표의 보완 적합성

기존 loss attribution 패턴을 현재 부모 전략에 필요한 정보 기능으로 변환한다.

예시 WeaknessHypothesis 필드:
- weakness_id, 부모/원본 evidence hash, 문제 거래·미진입 decision IDs
- 관측된 문제: false_entry, delayed_exit, regime_misclassification, missed_opportunity, excessive_turnover, drawdown_cluster 등
- 필요한 정보: 추세 지속 여부, 추세 전환 속도, 고변동 위험, 독립적 확인, 청산 조건 구분 등
- 반례 및 대안 설명, 근거 부족 여부, 예측 가능한 개선 지표, 해당 수정의 잠재 비용

Matcher는 “이 지표가 좋다”라고 랭킹만 내지 않고, 부모 전략에서 정보가 중복되는지, 후보가 이 문제를 해결한다는 증거가 있는지, 악화 사례도 있는지 요약한다. LLM은 후보를 거부하거나 전혀 다른 수식을 설계할 수 있다. AVAILABLE/INCONCLUSIVE/CONTRADICTED/MISSING_SOURCE/UNVERIFIED 상태를 노출한다.

수락: G262 부모에서 EMA=0이었던 손실 하나만 보고 EMA 필터를 자동으로 정답이라고 간주하지 않음. 해당 조건에서 수익 거래를 놓칠 가능성도 검증 제안에 포함. 지표를 제거하거나 부모 유지도 유효한 제안.

### F3 — 독립 통제 실험에서 보완 기여도 측정

기존 S7을 그대로 사용해 동일 시장·비용·원본 부모에서 선택된 대안을 비교한다. 원본 대조, 진입만 변경, 청산만 변경, 지표 제거/교체, 새로운 계산식 추가 등은 사전 고정된 실험 예산 안에서 선택한다.

GPT 가설은 weakness_id, candidate feature/formula hash, 필요 정보, 기대 거래/수익/MDD/노출/비용 변화, 반대 설명, 실패 시 다음 실험을 반드시 포함한다.

평가 항목: 실제 바뀐 decision/fill IDs, 부모 대비 비용 반영 총수익·MDD·Sharpe·시장 노출·거래수·QQQ 상대 성과, 국면별 반례, 제거된 손실 거래와 함께 놓친 수익 거래. 후자의 거래별 단순 PnL 합을 포트폴리오 이익으로 오인하지 않고 전체 지분·현금 경로를 기존 백테스트로 재계산한다.

복합 entry+exit 수정도 허용하지만 인과 설명은 JOINT; 단일 부위 통제 없이 “EMA 덕분에 성과 향상” 결론 금지. 수익 악화·MDD 악화·무거래 전략은 적절한 FAIL 또는 INCONCLUSIVE. 기존 parent selection 게이트 유지.

수락: 손실 일부를 막았으나 수익 기회 더 많이 놓친 필터를 성공으로 승격하지 않음. 같은 데이터와 비용에 대한 재생 해시/거래 변경 내역 검증.

### F4 — 결과 축적과 새로운 수식 창안

기존 experiment_learning/cross_generation_memory에 weakness_id → feature/formula identity → 가설·반례 → parent/child trade changes → S7 result hash → parent selection hash를 증거 연결로 보강한다. 성공뿐 아니라 실패와 미결도 기억하고 동일 실험 중복을 방지하되 다른 국면·다른 식의 재검증은 허용한다.

지표 후보가 해당 정보 기능을 충분히 제공하지 못하면 GPT가 기존 primitive의 조합으로 새로운 formula/condition/state를 제안한다. P1-1~P1-3의 typed Expression/StateMachine 및 ResearchCatalog PROPOSED/VERIFIED/QUARANTINED 계약을 재사용한다. 외부 Python/Pine 실행은 허용하지 않으며 미검증 계산식을 운영 지표나 브로커 신호로 등록하지 않는다.

연구 컨텍스트에는 현재 약점과 관련된 소수 프로파일·반례·최근 실험만 포함. 173개 장문 지표 문서를 매 세대 주입하지 않고 필요할 때만 추가 조사. 토큰/캐시/메모리 비용 계측.

수락: 다음 세대 GPT가 이전의 실패한 필터를 정확히 참고해 다른 접근을 선택하고, 새 수식을 제안하거나 전략을 단순화한 이유를 구체적으로 설명. 실제 거래와 원장 해시가 확인되기 전 “진화 완료” 선언 금지.

### F5 — 기존 자율 연구 T4 루프 내 E2E

1차: 연구원장 복제본에서 최소 3~5회 연속 “부모 → 지표·약점 분석 → GPT 실제 가설 → S2/S7 → 기억 → 부모 선택” 흐름. 유해한 지표 추가 거부, 신규 수식 1건, 지표 제거/단순화 1건, 같은 오류 재검증 방지 테스트 포함.

2차: 기존 인증 GPT/MCP에 opt-in으로 연결하여 최소 10세대의 실제 모델 연구를 수행. 기존 GPT 진단 흐름과 지표 약점 매칭을 추가한 흐름을 동일 데이터·부모·세대/백테스트 예산·토큰/시간을 최대한 맞춰 비교. 가설 근거 적합도, 무효/중복 실험 감소, 부모 대비 실측 개선 자식 비율, 연속 부모 계승률, S7 거래 변화, MDD·수익·비용을 함께 측정. 긍정적인 한 세대 결과만으로 우월 선언 금지.

3차: T4 100세대 진입은 실제 GPT, 중단·재개, 학습 기억, 동일 연구 원장 증거 검증 후. 독립 PIT/OOS는 V01~V04 별도 허가, paper/실거래 단계 임의 앞당기기 금지.

## 4. 단계별 산출물과 합격

| 단계 | 주요 결과물 | 수락 증거 |
|---|---|---|
| F0 | 기존 기능·데이터 계약 차이 표 | 중복 개발 제거, 기존 해시 불변 |
| F1 | 지표의 조건부 실증 프로파일 | 장점/단점/반례/표본·시점 검증 |
| F2 | 부모 약점과 정보 필요 매칭 | 왜 특정 지표·수식인지 근거 제출 |
| F3 | 실제 비용 반영 S7 보완 비교 | 놓친 수익·피한 손실·부모 전체 성과 동시 확인 |
| F4 | 지표/가설/결과의 세대 간 기억 | 같은 실패 재활용, 유효 정보 후속 활용 |
| F5 | 연속 GPT 연구/부모 계승 통합 테스트 | 실제 GPT 10세대 뒤 승인 T4 100세대 확대 |

## 5. 변경 금지·실패 방지

기존 source of truth는 typed StrategyIR과 append-only 증거 원장. core/data, core/backtest, core/evaluator, core/costs, core/validation, core/integrity, 봉인 OOS, 운영 OAuth/MCP URL, 실주문 OFF는 별도 승인 없이 변경하지 않음. 외부 데이터 발표 시점·라이선스 제약을 안전하게 처리. 신규 연구 코드 PASS는 GPT 자율성·미래 수익성을 증명하지 않는다.

이 계획은 기존 T4 연구 진화의 하위 개선 사항이다. **F0·F1·F2의 개발·검증 완료, F3~F5 미구현.** [F0/F1 실측 결과](autoresearch-feature-weakness-f0-f1-2026-10-20.md) · [F2 연결 결과](autoresearch-feature-weakness-f2-2026-10-20.md).

**다음 F3: 실제 GPT가 약점–지표 관찰 결과를 참고해 제안한 개선안을 기존 부모와 동일 비용·시장으로 S7 대조하며 피한 손실/놓친 수익을 함께 검증.** 기존 S7·부모 계승 운영 검증을 지연하지 않는다.
