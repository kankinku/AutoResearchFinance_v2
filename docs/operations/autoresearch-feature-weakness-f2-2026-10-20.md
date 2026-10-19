# Quant AutoResearch — F2 약점·지표 실증 근거 매칭 완료

2026-10-20 KST · **F2 DEV_IMPLEMENTED / MCP_CONTEXT_TESTED / PRODUCTION_NOT_DEPLOYED**
원본 20문답 Q02/Q05/Q06/Q08/Q09/Q10/Q11/Q12/Q14/Q17/Q18/Q20 및 [F0~F5 계획](autoresearch-feature-weakness-research-plan-2026-10-20.md) 범위 내 구현.

## 사용자 목표

GPT의 기존 연구 루프(부모 전략 → 손실 거래·원인 *가설* → 알고리즘 수정 → 비용 반영 S2/S7 → 연구 기억 및 우수 부모 계승)에서 **손실 한 건을 보고 지표를 무작정 추가하는 문제**를 줄인다.

이번 F2는 **무엇이 부족한지(정보 기능) → 해당 문제에 연결되는 실증 지표 특성·반례 → 기존 지표 추가/제거 또는 신규 수식 제안의 조건**을 GPT의 *다음 연구계획 문맥*에 보존한다. GPT가 직접 가설을 작성하고 S7이 검증해야 하며, 기계가 특정 변경을 강요하지 않는다.

## 기존 기능 재사용과 실제 변경

| 코드 | F2 작업 |
|---|---|
| research/llm/loss_attribution.py | 기존 P2-1 손실 패턴 코드·실제 거래 IDs·대안 설명 재사용; 출처 SHA 검사 |
| research/llm/feature_evidence_profile.py | F1 Verified 학술 calculator·동일 canonical 진입/승패/비진입 및 신호 일치 계산 재사용 |
| **research/llm/weakness_feature_matcher.py (신규)** | loss/report와 F1 관측을 전략·자료·audit hash로 검증, 1~4개 관찰 약점을 정보 요구 가설로 설명, verified 지표 1~3개(상한 5개)에 후보 역할·조건부 승패·반례·표본 불충분 표시 |
| **application/academic_checkpoint_service.py (연결)** | 이미 서명된 S2 수정 없이 후속 `_context`에 `feature_weakness_guidance` 추가. 원래 세대 evidence SHA·generation도 포함해 guidance hash 계산 |
| tests/research/test_weakness_feature_matcher_f2.py (신규) | 실제 fixture GPT/MCP 1세대 종료 후 다음 계획 문맥 F2 존재, hash 원장 일치·위변조 차단·근거 없는 자동 수정 없음·미완성 표본을 만들어내지 않음 검사 |

### 증거 계약

- F2 guidance는 **기존 동일 전략 SHA/데이터 SHA/결정 감사 SHA**와 F1 각 지표 자체 profile SHA, P2-1 손실 observation hash를 검사한다.
- `weakness_id`: 이전 실패 패턴 코드 + 관찰 거래 IDs + 부족한 정보 + 다른 가능한 설명 및 NOT_RUN.
- `feature_id`: verified calculator 수식 SHA, 표본 수, 긍정·부정 신호에서 실제 WIN/LOSS·국면별 표본, 무진입 상황, blanket 필터를 적용하면 놓칠 수도 있는 **기존 수익 거래 반례**.
- 표본 부족·미관찰 상황에서는 관측했다고 꾸미지 않는다. 강점/약점은 **가능성 및 예비 근거**로 표시하고 예측·인과효과는 UNKNOWN.
- `recommended_auto_mutations=[]`, `causal_status=NOT_ESTABLISHED`, `broker_executable=false`, `independent_oos_approved=false`. 기존 부모 그대로, 지표 제거, 대체, 새 수식 창안, 변경하지 않기 모두 가능. 후속 F3 **비용 반영 전체 포트폴리오 S7** 없이는 성공/승격 판단 불가.
- 기존 173개 등록 지표 전체나 미검증 외부 데이터를 GPT에 대량 주입하지 않는다. 실제 academic catalog에서 적합한 verified 1~3개만 결합; source license/인과성/PIT 이외의 보증을 하지 않는다.

## 실제 기존 G350 읽기 전용 근거

- 공식 원장 350/350 및 G350 Evidence SHA `26647e424913125cee1ec1dd6333538938237fb7205f7fc5147519b9c6cb725d` 그대로 보존.
- G350 감사 SHA `2edf373c4ff90aa45044102b3460a43199d6356f2bc4b181e7185cf05edc56f6`; 데이터 SHA `328f1cbd8ac5bf754de6aa2f21f580f68cfa8ea1511ae84bce77efe924a0b1f6`.
- **4개 관찰 약점**: EMA가 청산 당시 꺼진 사례, 돌파조건 없는 진입, 보유기간 고저 범위 변동성 상승, 관측된 최고 종가에서 청산 시점까지 하락. 이들은 확정된 손실 원인이 아닌 시험할 수 있는 가설.
- **3개 관련 후보**: EMA 20, previous_range_breakout, Parkinson variance; 전략 문제의 source indicator/metric과 검증된 feature identity로 연결.
- EMA=0인 진입에서 **수익 12, 손실 3**이 존재. 양수인 진입도 수익 29, 손실 17이므로 임의 EMA 필터가 나쁜 매매만 제거한다는 결론은 금지.
- Breakout=0 진입에서 **수익 37, 손실 20**, Breakout=1에서 수익 4, 손실 0. 후자의 손실 0건은 표본 4건으로 부족하므로 새로운 전략 보완 성공의 근거가 아니다.
- Parkinson variance는 연속값이므로 단순 0.5 이진 긍정 신호로 바꾸거나 원인이라고 판정하지 않는다.
- 재현 guidance SHA `ce8349a7cfa50c8a432ad427ec590cc4cafd8516aab4d81ce4efb3c9ae354ffb`.
- [G350 요약 JSON](evidence/quant-validation-20261020/f2-g350-weakness-matcher-readonly.json). 실제 수익성·인과성 입증 없음.

## 다음 개선 및 보존 경계

**F2 실제 GPT 연구계획 문맥 코드 연결 완료이지만 운영 서버에 배포하지 않았다.** 신규 정식 세대 0, GPT가 F2를 읽고 제안한 후속 세대 실제 실행 NOT RUN.

**다음 F3:** 기존 부모 동일 데이터·동일 비용에서 지표 추가/제거, 진입/청산 한 부위, 새로운 계산식을 대조하고, 방지한 손실과 놓친 수익(전체 거래·equity 경로)을 분석. 효율 저하·무거래·MDD 악화를 개선으로 승인하지 않음. F4는 지표/약점/실험 결과의 세대 기억, F5는 실제 GPT 다세대 연속 진화 증거.

기존 G350 원장, 실거래 OFF, 원래 MCP OAuth/URL, protected core 및 봉인 OOS, V05→T4→V01~V04→V06→V07 단계 잠금 불변. 전체 Pytest 및 실제 GPT 운영 검증은 별도 명시적으로 수행하기 전까지 완료라고 주장하지 않는다.
