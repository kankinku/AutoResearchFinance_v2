# T4 P0-2B — 53세대 원본 기반 S7→손자→부모 선택→counted S2/S7 종단 간 격리 실증

기준 2026-10-19 KST · 기존 20문답 잠금 유지 · 개발 전용/기존 QQQ 비PIT 데이터만 재생 · 독립 OOS 미실행

## 1. 기존 구현 재사용 범위

- 출발 코드/문서: `76c67aa` (P0-2A), `docs/operations/quant-t4-existing-work-integration-plan-20261019.md`.
- 기존 `AcademicMCPCheckpointService.continue_verified_child` → `verified_child_successor`(해시·StrategyIR·체결·비용·최소 완료 거래 30쌍 확인) → `_selected_development_parent` / `choose_development_parent`(수익·MDD·거래·노출 게이트) → `_stage_inherited_plan`(`require_execution_change=True`) → `submit_diagnosis` → `compare_inherited_experiments` 경로를 변경 없이 사용.
- 새 백테스트 엔진, 새 부모 선택기, 새 계보 모델, 새 백그라운드 GPT/API 루프를 추가하지 않음. 기존 MCP URL·OAuth·32도구·실주문 OFF 설정·운영 서버 코드는 변경하지 않음.
- 원본 연구 DB `state/moon-http/research/academic-gpt-checkpoints/{cycles.sqlite,gateway.sqlite,catalog-s6-v2.sqlite}`를 SQLite online backup으로 각각 `tmp_path` 내로 격리하여 재생. 서버 코드의 project_root는 기존 읽기 전용 시장 데이터 입력만 참조. 원본 SQLite DB를 개발 테스트가 열어 쓰지 않음.

## 2. 실제 G25 기반 반복 가능한 Golden 검증

| 단계 | 실제 측정·해시/상태 | 판정 |
|---|---|---|
| 원본 세션 | `c1eadd67bad94d7ea182dc274224dbce`, 53/100, `AWAITING_PLAN`, S7 후보 7개 | PASS |
| G25 S7 자식 | hypothesis `t4_g025_s7_rule_structure`; 자식 전략 SHA `55b2f63f...`; 재생 수익 +28.7032%, MDD 7.6676% | PASS (개발용) |
| 손자 개발 | 자식의 exit vote `less_equal 0.78` 변경; 손자 SHA `5edeb732...`, 수익 +36.8800%, MDD 8.9094%, 체결 76 이벤트, 비용 포함 재생 | PASS (수익은 늘었지만 MDD 악화) |
| 최초 부모 선택 | `source_generation=25`, replay lineage report SHA `23366d34...`, selection SHA `7ee45568...`, 종료 거래 **38쌍**, 시장 노출 29.44%, `parent_selections` 저장 | PASS, OOS 불인증 |
| 중복/무효 입력 | 위조 child hash 거부, 동일 계보 요청 idempotent, exit threshold 0.75 변경은 `UNCHANGED_CANONICAL_FILLS`로 차단·세대 미소비 | PASS |
| 다음 정식 세대 S2 | 부모 StrategyIR의 exit vote 0.82로 실험, `require_execution_change=True`, 원본 부모 76체결 → 후보 80체결, `VERIFIED_DIFFERENT_COSTED_FILLS` | PASS |
| counted G54 | **격리 DB만** 53→54, G53 SHA 체인 계승 및 inherited source G25·parent selection SHA 일치, 비용 포함 감사 | PASS |
| G54 S7 | 가설 `t4_p0_2b_shadow_g54_exit`: 거래 수 증가 예상했으나 40→38로 **`DIRECTION_NOT_MATCHED_DEVELOPMENT_ONLY`**; 부정 가설/실측 S7 저장 | PASS (원하는 방향은 실패로 기록) |
| 다음 게이트 | shadow `parent_selections` 2건(54·55세대), `successor_lineages` 1건, `experiment_reports` 54건; 원본 운영세션 여전히 53/100 | PASS |

QQQ 동일 개발기간 단순보유 수익률은 약 +187.77%로, 손자 +36.88%는 초과 수익 아님. 후속 손자 개발기간 수익 개선은 다중실험·과적합 위험이 있으며 독립 OOS·PIT·실주문 승인 근거가 아니다. *실제 GPT의 매 세대 독립 사고/학습 및 외부 모델 출처 확인은 이번 검증의 대상이 아니다.*

## 3. 이 단계에서 발견한 재발의 정확한 조건

- 부모 계승기 자체는 운영 코드에서 재생 가능한 상태였다. **일반 AlgorithmPlan 53세대 세션에는 명시적 후속 `continuation_intent`를 넣어 검증된 `successor_lineages`를 만드는 첫 호출이 없었다**. 이 호출을 하지 않으면 부모 후보가 없어서 다음 연구가 계속 일반 계획으로만 진행된다.
- 새 P0-2A `verified_lineage_bootstrap`은 GPT에 S7 근거 후보를 표시하고 기존 호출 사용을 안내한다. P0-2B에서 해당 후속 호출과 단계 전환을 실증했다. 단, 이는 호출자가 바른 시점에 도구를 호출하는 경우이며 **자율 GPT 판단을 강제하거나 무인 47세대 진행을 보장하지 않는다**.
- S2 강제 체결변화 게이트는 정상적으로 동작한다. S7에서 기대한 방향과 실제 결과가 다를 때도 저장되어, ‘형식 통과 = 경제적 개선’이라는 오류를 피할 수 있다.

## 4. 코드·테스트 및 비목표

- 추가 코드: `tests/research/test_t4_p0_2b_shadow_e2e.py` — 실제 53세대 DB snapshot 기반 E2E golden, 위조 해시 거절, idempotence, strict-S2 무효체결 차단, 다음 counted 세대 S7 및 원본 53 evidence 불변을 검사.
- **실제 서비스 기능 변경 없음:** 기존 계승 함수들을 재사용하므로 로직 수정이 필요하지 않았음. 기존 P0-2A 브랜치와 배포 상태는 유지. 관련 57개 회귀 테스트 **57 PASS / 0 FAIL (105.92s)**, 저장소 전체 Ruff PASS, Mypy **277 source files PASS**. 전체 Pytest 1,700여 개는 이번 절편에서 재실행하지 않았으므로 전체 회귀 통과로 과장하지 않는다.
- 다음 P0-3은 별도 단계: 실제 GPT가 이전 진단/실측 결과를 읽어 자신의 다음 계획을 자유롭게 생성했는지를 증명하는 provenance·동일 예산 검증. GPT가 아닌 템플릿은 명확히 분류하고, 서버가 알지 못하는 모델 출처를 verified라고 표시하지 않는다.
- 다음 T4 연구 세대 47개는 이 격리 테스트에 포함되지 않으며, 기존 연결에서 실제 진행된 것으로 보고하지 않는다.

## 5. 배포 및 롤백 경계

개선 커밋은 `feat/quant-t4-p0-2b-20261019` 분리 브랜치에만 반영한다. P0-2B에서 **서비스 구현 로직 수정 0건**이며 golden 통합 테스트와 문서만 추가한다. 운영 MCP 소스 SHA `54a515f`, 기존 고정 배포 런처·OAuth·실거래 차단 및 원본 53세대 DB는 변경하지 않았다. 검증 실패 시 신규 브랜치의 테스트·문서만 되돌리면 되고 운영 재시작은 필요 없다.
