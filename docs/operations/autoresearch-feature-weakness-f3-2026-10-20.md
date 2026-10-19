# Quant AutoResearch — F3 비용 반영 S7 기여도 분석 개발·실측

**2026-10-20 KST · F3 DEV_ONLY_VERIFIED / OPERATING_GPT_CONTEXT_NOT_WIRED**
**Q02/Q05/Q06/Q08/Q09/Q10/Q11/Q14/Q17/Q18/Q20** · [개선 계획](autoresearch-feature-weakness-research-plan-2026-10-20.md)

## 목적과 기존 엔진 재사용

사용자가 요청한 지표별 장단점 분석(F1)과 현재 부모 전략의 부족한 기능 매칭(F2) 다음 단계. **GPT가 제안한 지표/규칙 수정이 부모 전략을 실제로 보완했는지** 기존 비용 반영 S7과 연동해 검증한다.

기존 `ControlledExperimentReport`, `_execution_delta`, `_development_windows`, 정식 S2 `AcademicDecisionAudit` 및 canonical `audit_inherited_decisions`, 기존 QQQ 비용 반영 매수·보유 기준을 그대로 사용. protected backtest/cost/data/validation, 기존 S7 증거 포맷·부모 계승 규칙은 수정하지 않음.

새 코드 `research/llm/feature_contribution_f3.py`:

1. `build_costed_s7_contribution`: 부모/자식의 별개 재생된 canonical S2 audit + 원래 S7 보고서를 받으며, 동일 데이터·같은 초기 자본·표준 비용·실제 fill/equity 일치, S7 이벤트 차이 및 4개 개발 구간 재생 결과의 일치를 확인. 전체 누적수익·MDD·Sharpe·비용·청산 거래수·실현 시장 노출·QQQ 비용 반영 buy/hold 상대 차이를 산출한다.
2. 같은 **진입 실행 시각 기준**으로 부모에만 있었던 기존 청산 수익 거래/손실 거래, 자식에만 있었던 기존 청산 수익·손실 거래를 구분하고 소수 예시의 실제 trade/decision ID를 연결한다. **매칭하지 않은 거래의 원래 PnL은 참고할 수 있지만, 그것이 자식이 '피한 손실 금액' 또는 '놓친 이익 금액'과 같지는 않음**을 자료에 명시한다. 청산만 달라진 경우 등은 진입의 동일/다름과 별개로 `execution_delta`를 보고해야 한다.
3. `build_verified_s7_contribution_review`: 기존 parent/child StrategyIR을 **독립적으로 canonical 재생**, 바뀐 부위가 entry/exit/regime/risk/features인지 표시하고, 필요한 경우 F2 `guidance_hash`·`weakness_id`를 출처별로 검증해 어떤 문제에 대한 가설이었는지 연결. 부모와 자식의 데이터/feature replay/주문 권한이 다르면 거부한다. 프로파일/가설 연결도 인과 증명은 아니다.
4. 판단은 보수적임: 부모보다 수익 또는 MDD가 악화되면 `PARENT_REMAINS_BETTER_ON_RETURN_OR_RISK`, 거래 미변경·무거래는 `INCONCLUSIVE_DEVELOPMENT_ONLY`, 그렇지 않아도 `CANDIDATE_REQUIRES_INDEPENDENT_VALIDATION`. 자동 승격/실거래/OOS 승인 없음.

**F3를 새 S7 엔진으로 분기하지 않았다.** 기존 S7의 실제 체결·비용·원장 값을 사용하는 사후 연구 확장 계층이다.

## 공식 G350의 실데이터 읽기 전용 검증

- 공식 세대 350/350. 원본 G350 Evidence SHA: `26647e424913125cee1ec1dd6333538938237fb7205f7fc5147519b9c6cb725d`.
- 원본 결정 감사 SHA: `2edf373c4ff90aa45044102b3460a43199d6356f2bc4b181e7185cf05edc56f6`; QQQ 2020~2025 개발 자료, PIT/OOS 승인 없음.
- 기존 G350의 S7 실측 제안 `g350_policy_0_s7`에 대해 **원래 AlgorithmPlan·GPT 제출 가설·현행 S7 전체 재평가 후** 자식 typed StrategyIR을 재생해 F3 산출.

| 측정 | 기존 G350 부모 | 기존 G350 S7 자식 |
|---|---:|---:|
| 비용 반영 누적수익률 | **+78.9824%** | +76.8640% |
| 최대 낙폭 | 8.6677% | 8.6677% (거의 동률) |
| 청산 거래수 | 61 | 60 |
| 거래비용 | $1,362.16 | $1,328.57 |
| 시장 노출률 | 32.8467% | 33.0458% |
| 비용 반영 QQQ 매수보유 | +187.7724% | 같은 비교군 |

실제 관찰: 자식의 진입에서 제외된 **부모의 원래 손실 거래 1건**, 제외된 부모의 원래 수익 거래 0건. 그러나 전체 재생된 포트폴리오의 수익률은 **−2.1184%p**. 체결비용이 $33.59 절감됐고 청산 거래도 하나 줄었지만 이것은 부모 대비 개선이라는 증거가 아니다.

**F3 evidence SHA:** `65308f779b349a3044a0ebb2010fef323f8157910919872b8fe30c39c8a48f74`. 원본 `ControlledExperimentReport`와 다른 독립 파생 읽기 전용 evidence로만 저장. [기계 판독 요약](evidence/quant-validation-20261020/f3-g350-s7-parent-child-contribution-readonly.json).

## 검증 상태 / 미완료

- 새 테스트 `tests/research/test_feature_contribution_f3.py`: 실제 과거 계승 IR 기반 S7 parent/child, 전체 비용/QQQ·시장 노출·분할 기간, 부모/자식 단독 진입 관측 사례, S7 자산·감사 해시 위변조/불일치 차단, F2 weakness_id 근거 연결 및 조작 거부.
- 정식 S7 원장 `report.evidence_hash`나 GPT 계획 제출 형식을 수정하지 않았고 공식 G350 원장은 읽기 전용으로 보존했다.
- **운영 연결 한계:** 현재 F3는 개발 연구 분석 함수 및 G350 읽기 전용 실측까지 완료. 운영 GPT의 다음 계획 문맥에 이 F3 파생 보고서를 **자동 저장·주입하지는 않는다**. F4에서 기존 experiment_learning/cross_generation_memory의 데이터 계약에 연결해 실패/성공·반례·약점 ID를 과거 증거로 누적하고, F5에서 실제 연결 GPT 계승으로 검증한다.
- 전체 저장소 Pytest, 실연 GPT의 정식 F3 개선 루프, 외부 PIT/OOS, 독립 투자수익성 및 실주문: **NOT RUN**. 원래 MCP URL/OAuth·코어·주문 OFF·진행된 세대 해시 전부 불변.

**다음 우선 작업 F4:** 이번 F3의 '손실 하나 제거했지만 전체 수익 악화' 같은 지식과 F2 약점·지표 해시를 기존 S7 연구 기억에 안전하게 연결하여, 다음 GPT가 같은 근거 부족 변경을 반복하지 않도록 한다. 이후 F5 실제 인증 GPT 연속 연구 10세대 통합 검증. 상위 단계 V05→T4→V01~V04→V06→V07 유지.
