# Quant AutoResearch — T4 최초 S7→정식 부모 계승 연결

**2026-10-20 KST · Q02/Q06/Q07/Q08/Q09/Q10/Q17/Q18/Q20**
**개발 브랜치 구현 + 과거 격리 원장 검증. 운영 MCP 배포 NOT RUN.**

## 기존 시스템 진단

사용자가 확정한 목표는 LLM이 수식·지표·복합 알고리즘을 창안한 뒤 실패 분석, 통제 실험, 검증된 부모 계승을 **연속적으로 반복**하는 것이다. 기존 엔진은 typed StrategyIR, mutation, 173개 등록 FeatureSpec(모두 E2E 사용 가능하지는 않음), canonical backtest, 거래·비용 감사, S7 대조, 실패·실험 기억, 부모 재생·선정·정식 계승 코드를 이미 갖추고 있다. 개별 전략 GPT/Local/Random 10개를 독립 비교하는 것은 이 목표의 진화 효과 검증을 대체할 수 없다.

원래 350/350 세대 세션 `72495cc59fc147e08f4b433b98676fca`를 **실제 MCP와 읽기 전용 SQLite**로 확인:

| 증거 | 실측 |
|---|---|
| 정식 세대 | 350/350 COMPLETED |
| S7 측정 | 350건 |
| `inherited_parent`가 있는 정식 세대 | **0건** |
| 동일 세션 `successor_lineages` | **0건** |
| 동일 세션 `parent_selections` | **0건** |
| GPT 무인 자율성 / PIT 수익성 | 둘 다 미검증 |
| 실거래 권한 | OFF |

근본 단절은 **최초의 일반 AlgorithmPlan 세대에서 검증된 S7 자식을 바로 다음 정식 부모로 선정하는 bootstrap 경로가 없었다**는 점. 기존 `replay_counted_s7_child`는 `inherited_strategy_ir`가 이미 있는 정식 세대만 허용했다. 최초 진화에는 별도 `verified_child_successor` 사이드카(자식→손자)가 먼저 필요했고, 공식 350세대에는 이 사이드카가 없었다.

## 최소 기존 경로 연결 (신규 엔진 아님)

1. `research/llm/lineage_selection.py`: 기존 `replay_counted_s7_child`를 **일반 AlgorithmPlan의 S7 출처**도 받도록 확장. 일반 계획은 원본 typed Plan/해시→본래 audit/최종 equity→진단 원문과 정규화된 S7 전체 대조를 재계산한다. 기존 계승 IR 전용 경로는 그대로 두고, StrategyIR 변형·체결/수수료·최종 equity·해시를 재검증한다. 거래 변화 없는 자식, 거래 수나 MDD 등 현행 품질 정책을 통과하지 못한 자식은 그대로 거부한다.
2. `application/academic_checkpoint_service.py`: 이미 유효한 수동/계승 부모가 있으면 **기존 선정 결과를 유지**한다. 없을 때만 일반 연구 S7의 서명된 외곽 리포트 메타데이터를 전체 이전 세대에서 값싼 1차 후보 식별에 활용한다. 사전 필터는 부모 대비 순자산 개선, ≥60 fills, 변경된 거래, 활성 거래를 요구한다. 상위 **16개 origin**에 대해서만 전체 S2/S7→거래/비용→MDD/노출/QQQ 비교를 정식 재생한다. **1차 측정값 자체는 승격 증거가 아니다.**
3. 선정된 자식은 기존 `COUNTED_S7_CHILD` 증거·`_selected_ir` 재생, `_stage_inherited_plan`, `advance_inherited`을 그대로 통과한다. 이미 구현된 GPT `InheritedResearchIntent` 제안을 다음 세대 입력으로 사용한다. 임의 Python/Pine 코드 실행, 기존 핵심 backtest/fees/Data/OOS 변경 없음.
4. 구형 S7 v1 보고서는 종전대로 조회하지만, 현행 출처·시점·비용 증거가 없는 자료는 **부모 후보 자동 선정에서 제외**한다. 출처 참조가 변조된 현행 자료는 실패 처리한다.
5. 기존 선정 정책을 느슨하게 하지 않았다. 원래 요구한 30개 이상 청산 거래, 최소 노출, 부모보다 개선된 수익, MDD 제한, 독립 미승인 및 broker OFF가 유지된다. 단 한계는 **상위 16개 후보만 정밀 검증하므로 전수 탐색의 글로벌 최상위 선정을 보장하지 않는다**는 것. 새로운 수익 알파의 증거도 아니다.

## 실제 과거 원장 격리 검증

| 검증 | 판정 |
|---|---|
| 과거 G29 S7 원본 Plan → child StrategyIR/fills/cost/equity 실측 재생 | PASS |
| 보존된 G33 SQLite를 **복제**하고 초기 sidecar/selection을 제거한 뒤 부모 bootstrap | PASS |
| 그 검증된 부모를 상속해 실제 G34의 S2 + S7 + immutable generation hash로 완결 | PASS |
| 공식 G350 DB를 read-only SQLite backup으로 **별도 임시 디렉터리에 복제**, 테스트용 요청만 351로 확장 | PASS |
| 351세대 모델 컨텍스트 `InheritedResearchIntent` · 부모 선정 | PASS |
| G350 원본 불변/SHADOW 생성 351세대 0건/주문 허가 OFF | PASS |

**G350→G351 그림자 선정 원본 결과 (실제 복사본, 본 운영 DB 변경 없음):**
- 상태 `SHADOW_350_TO_351_PARENT_READY`.
- 1차 등록 S7에서 상위 16개 origin 심층 재생, 14개 품질 통과.
- 선정 부모 **G262의 S7 자식**. 이 결과는 '현재 전체 연구 최고 G178보다 수익이 높다'는 의미가 아니라 **재생·품질 요건을 통과한 S7 후속 부모 후보** 중의 선정이다.
- source Evidence SHA `bc3fccb5a9f6805ec44c81cfdef6ed1a83c01bfb5dfec46d1f882745231d3cb0`.
- 선택 부모 StrategyIR SHA `23f6365f34e8a34e5ff6884f05db0e2ef90e1f3b7367b5a192aaee1d1fc2070c`.
- 부모 선정 증거 SHA `1b0e217d66858bf6f320168cf990e785caf65bdb504e756af4429b8b87d4eddf`.
- `broker_executable=false`, `independent_oos_approved=false`, 원본 350 generation/마지막 Evidence 불변.

관련 테스트: `tests/research/test_p0_3b_bootstrap_plain_s7.py` (신규), 기존 `test_p0_3b_reinherit.py`, `test_lineage_parent_selection_p0_3b.py`, `test_p0_3b_inherited_audit.py`, `test_lineage_p0_3.py` 및 `test_academic_mcp_sessions.py`와 ScopeLock. 런타임 테스트·독립 PIT/OOS·실거래는 아직 실시/승인하지 않았다.

## 다음 단계

- 현재 코드는 **개발 브랜치**에만 있다. 운영 전 기존 원장 백업, 실제 배포 SHA와 호환성, MCP OAuth/32-tool 등록·회귀, 원래 `COMPLETED 350/350`을 안전하게 351+로 별도 확장하는 승인된 운영 절차 필요.
- 운영 GPT가 계승한 `InheritedResearchIntent`로 다음 정식 세대를 작성하고, 거래·비용 근거로 다시 S7 진단하여 그 자식을 또 계승하는지 **수 세대 연속 검증**. 100세대 완전 무인 자율성·새 P1-3 수식/상태기계 운영 연결은 여전히 별도 미완료.
- 기존 승인 제품 순서 **V05→T4→V01~V04→V06→V07** 유지. QQQ는 개발 초기 기준으로만 취급. 실거래 비활성 불변.
