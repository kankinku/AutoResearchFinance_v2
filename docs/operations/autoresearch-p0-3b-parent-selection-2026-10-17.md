# P0-3B — 후속 StrategyIR 부모 자동 선택 / 정식 세대 계승 게이트

- 구현 브랜치: `feat/p0-3b-counted-parent-inheritance-20261017`
- 기존 MCP OAuth·URL·133세대 체크포인트: **변경 금지**. 운영 런처 커밋 PIN은 유지.
- 원본 연구 세션: `2ba41aaeacd547319cfbf7e6f266ad11` (로컬 33/100, 전역 133/300).
- 이번 변경의 범위: **부모 후보의 자동 선택 및 다음 세대용 고정**, 아직 실제 정식 세대의 부모 교체는 수행하지 않음.

## 구현된 기능

1. 기존 P0-3A S7 후속 보고서를 조회하며, 원본 세대 해시·S7 기록·자식 및 손자 StrategyIR·정확한 체결 수/거래비용/최종자산/자산곡선을 **독립 재생**하여 대조한다. LLM이 보고한 성과값만으로는 통과할 수 없다.
2. 수익률 상승, MDD 증가 제한(자식 대비 1.25배 이내), 최소 청산 완료 거래 30건, 유효한 시장 노출 등 개발데이터 한정 조건으로 부모 후보를 결정한다. 수익률과 MDD·거래 수·노출을 별도로 보존하며 QQQ 수수료 포함 매수 후 보유와 **사후 노출 비중 매칭**을 함께 표시한다.
3. `gateway.sqlite:parent_selections`에 차기 로컬 세대별 `selection_hash`와 원본 보고 해시를 기록하여 재시작/중복 `get`에서 후보를 바꾸지 않는다. 저장 후 해시/출처 검증 실패 시 다음 연구 문맥 반환을 거부한다.
4. MCP `get_algorithm_research.model_context.selected_development_parent`에 선택 결과를 제공한다. `counted_parent_inheritance_ready=false`를 명시한다. 기존 32개 도구와 `submit_algorithm_plan` 입력 형식은 변경하지 않는다.

## 기존 실제 증거의 읽기 전용 재생

G129(현재 세션 로컬 29) S7 자식으로부터 변형된 후속 전략을 원본 개발 데이터에서 정확 재생:

| 항목 | 후속 전략 |
|---|---:|
| 수익률 | +48.9465% |
| MDD | 16.6348% |
| 완료된 거래 | 48 |
| 실제 노출 추정 (시가 체결 기준 일별) | 44.1645% |
| QQQ 단순 보유 (동일 수수료 기준) | +187.7724% |
| QQQ 동일 최초 노출 비중 (사후 비교용) | +82.9287% |
| QQQ 단순 보유 대비 | -138.8259%p |
| QQQ 사후 노출 비중 비교군 대비 | -33.9821%p |

StrategyIR hash: `b7331a21c804eb2534faa0f3d3e6a16efec4f1fa3914b25834a2b9a591f6dda0`.
원본 lineage 보고: `9822931a599af246a5fa8f1b4daba0a351af9cf4a5b4e34c0c654f40e666036a`.

모든 비교는 2020–2025 개발 데이터 **재사용**이며 PIT/OOS·독립 수익성 검증이 아니다. 단순 보유의 배당 재투자·현금이자 제외. 정식 투자 승인/주문 권한 없음.

## 여전히 필수인 P0-3B 후속 — 미완료

- **B-2: 실제 정식 세대 엔진 연결.** 현재 `AlgorithmPlan` 컴파일 경로는 선택한 StrategyIR을 사용하지 않으며, 좁은 S2 거래 감사는 추가 진입 조건 등을 가진 후속 IR을 지원하지 않는다. 새 `AlgorithmPlan`에 부모 해시만 써넣으면 **가짜 계승**이 되므로 금지.
- 별도 연구 입력 계약(선택된 StrategyIR + 다음 유효 ResearchIntent), 실제 체결과 1:1 일치하는 S2 감사 확장, S7 대조 비교의 원본 타입 분기, 유효 신호 중복 방지, 체크포인트 중단/복구의 정확한 세대 커밋이 필요하다.
- **B-3: 반복 계승.** G134 S7 자식도 재생 검증해 G135의 정식 부모가 될 수 있도록 보편적 lineage 소스(기존 AlgorithmPlan 및 계승된 StrategyIR)를 지원해야 한다.
- B-2/B-3 완료 전에는 **133/300으로 유지**, 부모 선택은 `PARENT_SELECTED_NOT_COUNTED`로만 표시. 인증 MCP 운영본에 미검증 기능을 배포하지 않는다.

## 검증 요구

- 선택기 오류, 해시 변조, 저거래/비활동/손실/과도한 MDD, 순서 무관 결정성, 게이트웨이 idempotency 및 원장 위변조 검출 테스트.
- 관련 기존 MCP 세션/S7/중복 회귀 테스트 후 전체 pytest, Ruff, Mypy 진행.
- 실제 세대 증가 전 개발 복제 환경에서 G134 1세대의 완전한 예비 S2/S7/복구 검증 필요.


## P0-3B 복제본 통합 검증 (운영 원장 원본에 쓰기 없음)

운영 `gateway.sqlite`/`cycles.sqlite`/카탈로그를 SQLite backup API로 별도 임시 체크포인트에 복제하고 **개발 브랜치 코드**로 `get_algorithm_research` 두 차례 호출했다.

- 기존 현 세션 `completed_generations=33` 두 번 동일, 체크포인트 토큰 동일, 다음 전역 G134.
- `parent_selections.next_generation=34`에 G129에서 나온 `b7331a21...` 후속 StrategyIR 선택이 고정됐다.
- 선택 해시 `5cf3af798019413cc290587925bf89ccef1e558a75c36cc6e80e4bf4be50d7fa`가 두 조회에서 동일.
- `counted_parent_inheritance_ready=false`, 생성 카운터 변동 없음, 운영 URL/OAuth/실행 프로세스 변경 없음.

**중요:** 이 검증은 부모 후보 자동 선택·고정을 증명할 뿐, 정식 134세대 StrategyIR 실행·S2/S7 감사 계승을 증명하지 않는다.


## 최종 검증 기록 및 배포 판단

- 신규 선택/원본 계승·MCP stage/중복·복구·S7 실험·MCP 런처 연관 회귀: **53 passed**, 0 failed (`pytest -q`, 86.41초; 신규 검증 13건 포함).
- 프로젝트 전체 Ruff 검사: PASS. 프로젝트 전체 Mypy 검사: **262 source files PASS**.
- 별도 전체 pytest 1회는 새 워크트리의 `.venv` 링크가 준비되기 전에 시작하여 MCP launcher 환경 테스트 1개가 실패했다. 이후 동일 launcher 테스트는 가상환경 연결 후 **별도 PASS**, 관련 53개 묶음에도 포함. 이 전체 실행은 마지막 집계 직전 인터럽트되어 총 통과 건수는 미확정이다. **전체 스위트 완전 통과로 표기하지 않는다.**
- 개발 원장 복제본의 원본 G133 상태 보존·G134 부모 해시 고정·재조회 일치 검증 PASS. 운영 서비스 재시작/배포 없음.
- 프로덕션 승격 기준 **BLOCKED**: 정식 StrategyIR을 실행하는 counted S2/S7 경로와 재계승 기능이 미완료. 별도 기능 브랜치를 배포 브랜치로 합치거나 운영 런처 PIN을 바꾸지 않는다.

## 2026-10-17 P0-3B 후속: 정식 IR 감사 및 세대 원장 내부 실행 경로

변경 범위 (독립 개발 브랜치 전용; 운영 런처와 기존 133세대 원장은 수정하지 않음):

- `research/indicator_engine/inherited_decision_audit.py`: 2개 이상의 실제 StrategyIR 진입/청산 조건을 사용하여 정식 백테스터가 생성한 다음날 시가 체결·거래비용·손익을 S2 의사결정 ID와 연결. 기존 AlgorithmPlan 감사의 해시/로직 수정 없음. 주문 및 검증 OOS 승인 없음.
- `research/indicator_engine/inherited_experiments.py`: 서명된 S2 진단 응답을 원본 부모와 구조 변형 자식에 대해 동일 데이터/비용 기준 S7 실험 비교. S7 결과는 개발 데이터 대조일 뿐 인과 증거 아님.
- `research/llm/autonomous_cycle.py`: 선택한 실제 StrategyIR 부모와 별도 GPT ResearchIntent가 만들어낸 자식을 그대로 실행해 기존 `cycles.sqlite` 해시 체인에 단일 정식 세대로 기록하는 `advance_inherited` 추가. 부모IR/자식IR/원본 알고리즘/인텐트/원본 source-generation evidence hash를 모두 검증하고 내부 중복 세대 판정을 실행.

### 이 작업의 범위와 미완료

신규 백엔드 정식 세대 원장 API가 구현되어도 **MCP 플랜 제출/진단 승인/중단 복구/자동 S7 기록 경로에서 아직 호출하지 않음**. 따라서 현 133/300 상태를 134로 올렸다는 뜻이 아니며, 반복 승계가 가동됐다는 뜻도 아님.

다음 순서: 운영 SQLite 원장 복제본에서 MCP `get_algorithm_research`의 부모 선택을 ResearchIntent 플랜 문맥에 연결 → `submit_algorithm_plan`에 자식 StrategyIR/소스 증거 고정 → `submit_algorithm_diagnosis`에서 정확한 `advance_inherited` 호출 → 자동 S7/재실행 receipt/인터럽트 복구 및 부모 후보 재선정(G135) 확인 → 인증 MCP 배포 판단. 구 경로의 AlgorithmPlan/33세대 증거는 유지.

실제 서브시스템 API 수준 신규 테스트: 계승 G129 후속 전략의 S2 감사 97체결/48완료 거래, S7 대조·위변조 거절, 원본 `cycles.sqlite` 복제본의 **33→34세대 가상 커밋 및 해시 연결·중복 거절**.


## 2026-10-17 P0-3B — MCP 정식 134세대 경로 통합 (독립 개발 브랜치)

**구현 확인:** 선택된 G129의 실측 S7 후속 StrategyIR을 MCP `get_algorithm_research`에 `InheritedResearchIntent` 계획 계약으로 노출. `submit_algorithm_plan`은 그 실물 부모를 재생하고 새 ResearchIntent를 적용하여 복수 진입 조건을 보존한 정식 자식 StrategyIR을 S2 감사 상태로 저장한다. `submit_algorithm_diagnosis`는 `AcademicCycleService.advance_inherited`를 호출해 기존 해시 원장에 새 counted generation을 기록한다. S7은 계승 전략에 대한 별도 실측 대조 엔진을 사용한다. 기존 일반 AlgorithmPlan 경로 및 인증 URL/32개 도구 수 유지.

**복제 검증:** 원본 133/300세대 `gateway.sqlite`/`cycles.sqlite`와 카탈로그들을 SQLite 백업으로 별도 임시 폴더에 복제하여 계획 제출 → S2 진단 → 정식 로컬 34/100 = 전역 G134 → S7 결과 보존을 통합 테스트로 수행했다. 체크포인트 재호출 시 같은 증거 해시를 반환하고 추가 세대 증가 없음. 실거래/OOS 모두 거부. 원본 운영 원장에는 새 세대 기록하지 않음.

**범위 제한 / 반드시 후속 처리:** G135를 만들 때 지금은 검증된 예전 G129 챔피언에 다시 변형을 적용할 수 있지만, **G134의 개선된 S7 자식이 자동으로 부모 후보 풀에 편입되는 재계승 루프는 아직 미완료**. 다음 작업은 `source_generation=34` 타입의 체결 검증 S7 자식을 동적 후보로 재구성 → risk/return/노출/QQQ 기준으로 기존 챔피언과 비교 → 채택·미채택 이유 저장 → 복구/중복 방지·2세대 연속 통합 테스트. 이는 134세대 성공을 실거래 수익성 또는 독립 OOS로 승인하는 기능이 아니다. 운영 서비스에 배포하지 않고 계속 133/300 유지.

## 후속 검증 요약 (2026-10-17)

- 개발 브랜치에서 MCP 계획 제출 → G134 S2 진단 → 정식 세대 카운트 → S7 측정 및 중복 호출 재생 통합 시험 PASS.
- Ruff 전체 PASS, Mypy 264개 소스 PASS, 관련 회귀 79 passed.
- G134 검증은 독립 SQLite 복제본에서만 수행. 운영 연구 133/300 유지, 기존 인증 MCP 배포 변경 없음.
- 후속 필수 항목: G134의 성과가 개선된 S7 자식을 G135 후보 풀로 자동 등록하고 QQQ·MDD·거래 수·노출 등과 비교해 승계 여부 결정. 전체 pytest 미집계.
