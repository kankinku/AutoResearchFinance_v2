# Quant AutoResearch F0/F1 — 지표 경험적 특성 분석 구현 보고

2026-10-20 KST. 상태: F0 조사 완료 · F1 연구용 지표 관측 프로파일 구현 및 검증 완료 · F2~F5 미시작 · 운영 배포 없음.

## 목적과 기존 구현 재사용

원본 사용자 20문답 Q02/Q05/Q06/Q08/Q09/Q10/Q11/Q12/Q14/Q17/Q18/Q20의 목표는 GPT가 기존 알고리즘의 실패를 분석하고, 지표 특성을 이해해 현재 부모를 보완하며, 효과가 검증된 자식만 계승하는 것이다.

기존 loss_attribution.py(P2-1)는 실제 손실 거래와 당시 지표값을 기록한다. trade_cohort_review.py(P2-2)는 전체 청산거래의 국면·승패를 대조한다. experiment_learning.py와 cross_generation_memory.py는 S7 실험 성공·실패·중복 기록을 보유한다. academic_checkpoint_service.py는 이 증거를 GPT의 계획 문맥에 전달한다. 이 기능들을 재작성하지 않았다.

**F0에서 확인한 공백:** 현재 감사 스냅샷에는 plan_entry, plan_vote_score 같은 복합 신호가 있어도 원본 지표의 개별 특성은 항상 제공되지 않는다. 지표별 어떤 국면에서 장점·단점이 나타났는지, 수익 거래를 놓칠 위험이 무엇인지 정리하고 부모 전략의 부족한 기능과 연결하는 별도 근거가 필요하다.

현재 등록 지표 173개 전체가 검증된 것은 아니다. G350 당시의 학술 ResearchCatalog에서 VERIFIED 지표 8개를 확인했으며 F1은 이 VERIFIED 범위 중 필요한 지표 1~5개만 사용한다.

## F1 실제 구현

새 파일: research/llm/feature_evidence_profile.py

- build_feature_evidence_profiles: canonical audit에 이미 기록된 관찰 시계열을 직접 비교한다.
- build_verified_catalog_feature_profiles: 학술 카탈로그에서 VERIFIED, single_asset, 일봉 범위인 지표를 완료된 OHLCV 자료에서 계산하고, 감사된 원본 거래·비진입 판단과 연결한다.
- 과거 시점의 지표 계산과 실제 감사에서 기록한 계산이 중복되면 정확히 맞는지 확인한다. 대표 시점 prefix 계산을 통해 미래 봉으로 과거 계산이 바뀌지 않는지도 확인한다.
- 지표별 profile: 공식/후보 identity hash, 시장·시간축·자료/감사 hash, 결측과 표본 수, 신호 전환, 수익·손실·무진입 당시 값, 국면별 조건부 신호 관찰 및 반례, 다른 이진 지표와의 신호 일치율.
- 연속 수치 지표는 0.5 임계값으로 임의 이진화하지 않는다. 약점에 대한 인과적 효용, 진입 규칙 추천, 포트폴리오 수익률 우위는 이 모듈이 선언하지 않는다.
- 결과 상태는 DEVELOPMENT_ONLY, NOT_ESTABLISHED_CAUSALITY, OOS_NOT_APPROVED, BROKER_DISABLED에 해당하는 읽기 전용 증거다. 지표 자동 등록·원장 승격·주문은 하지 않는다.

## 실제 기존 G350 읽기 전용 평가

- 공식 세대 350/350 및 마지막 evidence hash 26647e424913125cee1ec1dd6333538938237fb7205f7fc5147519b9c6cb725d 확인.
- QQQ RAW 개발 dataset hash 328f1cbd8ac5bf754de6aa2f21f580f68cfa8ea1511ae84bce77efe924a0b1f6.
- 원본 G350을 기존 AlgorithmPlan 경로로 재컴파일한 감사 hash 2edf373c4ff90aa45044102b3460a43199d6356f2bc4b181e7185cf05edc56f6 일치.
- F1 프로파일 hash bb0da9822b73e720f80ae47ddb0b143c828bcb9efc6ffe3bc4fc46a3f3c8e6bf.
- EMA 20, SMA 방향, Parkinson 변동성의 유효 관측은 각각 1,489봉, 초기 warmup 결측 19봉. 전체 청산 거래 승리 41건/손실 20건, 무진입 또는 국면 제외 판단 700건.
- EMA가 양수인 진입 승리 29/손실 17, 양수가 아닌 진입 승리 12/손실 3. 따라서 EMA가 비활성일 때 발생한 개별 손실만 이유로 무조건 EMA를 추가할 근거는 부족하다.
- SMA 양수인 진입 승리 23/손실 15, 비양수인 진입 승리 18/손실 5.
- EMA/SMA의 동시 관측 1,489봉 중 이진 신호 일치율은 96.17%. 정보 중복 가능성은 조사 대상이나 제거·교체의 유효성은 S7 실험이 필요하다.
- Parkinson 변동성은 연속값 지표이며 방향 신호처럼 positive/negative 평가하지 않는다.

읽기 전용 요약: evidence/quant-validation-20261020/f1-g350-feature-observation-summary.json. 위 수치는 반복된 동일 개발 기간의 기술 통계이며 인과 효과나 투자 수익성 입증이 아니다.

## 검증과 남은 개발

- 신규 F1 테스트: tests/research/test_feature_evidence_profile_f1.py.
- 관련 P2-1/P2-2, ScopeLock 회귀 및 전체 정적검사를 실행했다. 테스트/코드 SHA는 master-progress 원장에 별도 기재한다.
- F1 연구 함수는 현재 독립 호출 가능하지만 실제 운영 GPT 연구 문맥이나 정식 진화 세대에는 **아직 연결되지 않았다**. F2에서 WeaknessHypothesis / Weakness Matcher를 통해 현재 부모의 부족한 정보 기능과 이 프로파일의 장단점·반례를 GPT에 전달한다. F3는 기존 S7 비용 반영 부모 대조, F4는 증거 기반 기억, F5는 실제 GPT 연속 연구 검증이다.
- 운영 OAuth/MCP URL, 실주문 OFF, 핵심 데이터/체결/비용/평가/검증 코어, 봉인 OOS, 공식 350세대 원장은 변경하지 않았다.
