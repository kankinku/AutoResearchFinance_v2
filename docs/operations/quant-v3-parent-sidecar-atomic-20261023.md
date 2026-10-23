# Quant AutoResearch V3 — 독립 연구 부모 선택 Sidecar 첫 구현 (2026-10-23 KST)

**판정: 개발 전용 연구 원장의 트랜잭션·멱등성·체인 무결성 검증 완료. 정식 학술 세대 계승·실제 GPT 자율 판단·PIT/OOS·투자 성과 개선은 NOT DONE.**

## 범위 잠금과 가치
- Stage: Q05/Q07/Q08/Q09/Q14/Q17의 **T4 자율 진화 연구원장 필수 종속 연결**. 기존 우선순위 **V05 → T4 실제 연결된 GPT 10→100세대 → V01~V04 → V06 paper → V07 GO/NO-GO** 유지.
- 기존 `state/moon-http/fresh-20261021` **G452** 증거, 분리된 `quant-moon-bounded-100-20261023` **G552** 증거, ChatGPT↔MCP OAuth/URL, 기존 대시보드, 실거래 OFF·봉인 OOS 보호. 원본 학술 체크포인트의 스키마/세대 수/해시는 변경하지 않음.
- 사용자의 실제 목표는 변형 횟수 늘리기가 아닌 **실측된 후보가 이전 부모보다 정말 새로운 경제적 행동을 낳았는지 분석·저장하고 다음 연구에 계승**하는 것. 이번 단계는 모델 없는 사전 연구 후보 판단 경로만 구현했고 1세대 완료로 집계하지 않는다.

## 변경 사항
- 신규 `research/llm/v3_parent_sidecar.py`: `ResearchParentSidecar`, `SidecarRecord`, `adjudicate_candidate`. 부모 후보 그룹 고정 `source_ledger_head`, `dataset_hash`, 초기 champion 전략 해시와 원본 세대 번호를 별도 versioned manifest에 저장. 트랜잭션 `BEGIN IMMEDIATE`를 사용한 **후보 1건 = 순차 SHA 연결 레코드 1건** 기록. `event_hash = content_hash(event)`, 매 기록 전에 기존 사건/이전 부모 해시/선택 결과/순서/경제적 중복 상태 전체 감사.
- 재시작·재제출: 같은 proposal ID와 동일 입력은 기록을 추가하지 않고 기존 결과 반환. 같은 ID에 달라진 본문은 `conflicting replay`로 차단. 다른 StrategyIR이지만 동일 costed `economic_fingerprint`(전체 equity hash + 실제 fills hash)를 가지면 `REJECT_PRIOR_CANDIDATE_DUPLICATE`. 기존 원본 부모와 같은 실행은 `REJECT_ECONOMIC_DUPLICATE`.
- 리스크 불합격 `REJECT_RISK`, S7 미실시 `REJECT_MISSING_S7`, S7 관측 효과 없음·불리함 `REJECT_S7_UNFAVORABLE_OR_NO_EFFECT`; 개발 후보가 P2 기준과 실체결 신규성 및 긍정 S7 대조 가설을 **모두** 만족한 경우에 한해 `SELECT_RESEARCH_PARENT_CANDIDATE`로 **연구용 잠정 부모**를 갱신하는 코드 경로 및 synthetic 회귀 검증. **원장에 실려 오는 '검증 완료' 문자열·해시만으로 정식 GPT 세대/독립 투자 인증을 얻는 것이 아님**.
- 신규 `scripts/run_v3_parent_sidecar.py`: 기존 G452 원장을 임시 SQLite 파일로 복사하고, 실제 G68/G192/G248의 각 S7·세대 원장을 `checkout_counted_donors`로 재검증. 6개 교배의 **실제 costed S2 체결·MDD·비용·거래 수·P2 위험·경제적 중복 판정**을 다시 계산하고 기존 6-way 보고서와 대조한 뒤, 지정된 개발-only 별도 SQLite에 순차 기록. 외부 LLM 호출 0건, 원장 세대 커밋 0건.

## 실제 측정 결과
- QQQ 기존 1,508개 개발 봉 재사용. G68/G192/G248 세 부모의 6개 조합을 전수 검사.
- 기록한 6개: 위험 탈락 **3**, 부모 동일 경제 결과 **2**, 이전 후보와 경제 결과 중복 **1**, 독립된 신규 적격 **0**.
- 초깃값 **G192**를 연구 부모로 유지; 마지막 체인 SHA **`0306222f9bc442fbd6bec3aaeb9ee404621beb51f003a633f972f14464ab9ce7`**.
- 동일 `run_v3_parent_sidecar.py` **2회 실행**: DB 이벤트는 6→6건, 마지막 SHA/선택 부모 불변. SQLite `PRAGMA integrity_check = ok`.
- 데이터 격리 경로: `state/moon-http/quant-v3-parent-sidecar-20261023/v3-research-parent-candidates.sqlite`. Git ignored 연구 산출물이므로 내부 경로만 기록하며 민감 원본 DB나 개인정보 데이터는 Git에 추가하지 않음.
- 시험: 신규 sidecar 5 PASS, C+D/P2/parent/governance 전체 **42 PASS**, Ruff PASS, 신규 모듈 Mypy PASS, source Git diff check PASS. Full repository pytest/Mypy **NOT RUN**. 가짜/예시 GPT 모델 인증으로 성공을 주장하지 않는다.

## 제한 및 다음 게이트
1. **중요 신뢰 경계:** sidecar 입력은 `COSTED_S2_DEVELOPMENT_REPLAY`라는 **로컬 컨트롤러 선언**이며, 원장 자체가 매번 모든 donor SQLite에 접근해 독립 공급자 증명을 하지는 않는다. 실제 6건은 예시 스크립트가 공식 재생 경로로 다시 검증했지만, 임의 외부 프로세스가 직접 제출한 가짜 JSON까지 암호학적으로 막는 것은 아님. 자체 SHA 체인은 **로컬 일관성**을 보여주며 파일 쓰기 권한을 가진 공격자가 원장을 전체 재작성하는 공격에 대한 별도 외부 고정 공증은 없다.
2. `SELECT_RESEARCH_PARENT_CANDIDATE`는 **잠정 개발 부모**. 정식 `AcademicMCPCheckpointService` 세대 승격에 연결되지 않았고, 실제 GPT Plan→S2→P2→S7→후속 가설·계획을 마친 세대 증거가 없는 경우 공식 completed generation **0개**.
3. 후속은 원장 서명/결과와 **실제 출처 검증을 구조적으로 강제하는 gateway** 및 C+D route 내 실제 ETF 1,508개 봉 실측 → GPT 실제 모델 출처 확인으로 확장. 실측 유효 개선이 없다면 자동 탐색 다양성을 바꾸되 부모를 강제 승격하지 말 것.
4. V05→T4→V01~V04→V06→V07 잠금 유지; 모델/구독·주문·OOS 권한 변경 없음.
