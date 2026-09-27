# MCP Phase 3-6.1 — Tool surface inventory and classification

## 목적

현재 공개 MCP Tool 18개를 실제 코드·Application Service·CLI parity·호출 관계·
운영 안전 경계를 기준으로 전수 분류한다.

이번 단계에서는 Tool을 제거하거나 이름/schema를 바꾸지 않는다.

분류 결과의 machine-readable 정본은:

```text
docs/operations/mcp-phase3-6-1-tool-inventory.json
```

이다.

## 분류 기준

### PUBLIC_KEEP

현재 MCP 사용자가 직접 호출할 이유가 명확하고, 역할이 독립적이며,
canonical workflow와 충돌하지 않는 Tool.

### DUPLICATE_OR_OVERLAP

고유 정보가 일부 남아 있지만 다른 공개 Tool과 운영 목적이 상당 부분 겹치는 Tool.
즉시 삭제 대상은 아니며 다음 단계에서 통합 비용과 호환성을 비교한다.

### INTERNALIZE_CANDIDATE

Application Service/CLI/내부 primitive로는 가치가 있지만 기본 공개 MCP surface에
항상 노출할 필요가 낮은 Tool.

### DEPRECATE_CANDIDATE

현재 공개 호출의 결과가 canonical workflow에 연결되지 않거나 사용자에게 잘못된
기대를 만들 가능성이 높아, 호환 절차를 거쳐 공개 surface에서 제거할 후보.

## 전체 결과

| 분류 | 개수 |
| --- | ---: |
| PUBLIC_KEEP | 12 |
| DUPLICATE_OR_OVERLAP | 1 |
| INTERNALIZE_CANDIDATE | 4 |
| DEPRECATE_CANDIDATE | 1 |
| 합계 | 18 |

## PUBLIC_KEEP — 12개

### initialize_research_state

안전한 MCP bootstrap 역할이다.

- 기존 state 보존
- 누락 파일만 생성
- orders_enabled=false
- 새 workspace에서 start_system 전 준비에 직접 필요

CLI `init`보다 MCP 구현이 더 보수적이므로 public 유지가 적절하다.

### validate_strategy

외부 전략을 실행하지 않고 static normalize/validation만 수행한다.

평가나 import 전에 agent가 직접 안전하게 확인할 수 있는 명확한 경계이므로 유지한다.

### import_strategies

현재 canonical external strategy intake다.

- 기본 dry-run
- static analysis
- project-root 제한
- GitHub HTTPS/ref 제한
- imported Python 미실행
- order API 미호출

실제 catalog write가 가능하므로 state mutation Tool이지만 목적과 안전경계가 분명하다.

### list_strategies

import 결과를 filesystem 추측 없이 조회하는 독립 read capability다.

Dashboard strategy catalog와 목적은 유사하지만 MCP agent가 명시적으로 전략 catalog를
탐색하는 작은 인터페이스로 유지 가치가 있다.

### list_features

현재 허용되는 feature candidate를 직접 조회하는 작은 capability catalog다.

`get_research_context`에도 feature catalog가 포함되지만, feature만 요청할 때
대형 research context 전체를 반환할 이유가 없으므로 이 Tool을 canonical public read로
유지한다.

### get_research_evidence

immutable research evidence를 attributable하게 조회하는 정식 interface다.

Evidence integrity error 및 sealed OOS safety 의미가 이미 명확히 정의되어 있어 유지한다.

### get_dashboard_status

`get_system_status`와 역할을 구분한다.

```text
get_dashboard_status
  = 연구 결과 / 성과 / account snapshot / trend / strategy data plane

get_system_status
  = process / queue / research phase / Evidence / health control plane
```

따라서 단순 중복으로 보지 않는다.

### run_evaluation

한 번의 bounded evaluation을 실행하는 advanced primitive다.

`start_system`과 달리 multi-generation managed autoresearch를 시작하지 않고,
동일 canonical queued evaluator를 직접 사용한다.

수동 전략 검증/실험 용도로 독립적인 가치가 있다.

### check_system

`start_system`도 내부 preflight를 수행하지만, 실제 실행 전에 side-effect 없이
준비 상태만 확인할 수 있다는 점이 중요하다.

실행 비용이 있는 start와 read-only preflight는 분리 유지한다.

### start_system

현재 canonical managed research entrypoint다.

- Dashboard
- bounded autoresearch
- canonical evaluation backend
- lifecycle ownership
- recovery
- runtime observability

를 하나의 managed path로 연결한다.

공개 실행 Tool의 중심으로 유지한다.

### get_system_status

Phase 3-5에서 확정한 typed RuntimeSnapshot을 노출하는 canonical runtime status다.

active managed runtime에 대해서는 lifecycle reconciliation이 의도적으로 수행될 수
있으므로 단순 filesystem read와는 구분한다.

### stop_system

`start_system`과 반드시 짝을 이루는 lifecycle control이다.

owned process와 owned evaluation job만 종료하는 범위가 이미 검증되어 있으므로 유지한다.

## DUPLICATE_OR_OVERLAP — 1개

### get_workspace_status

현재 다음을 반환한다.

- initialized 여부
- champion 요약
- frontier family 수
- selected mode
- audit record 수
- manifest 수

문제는 일반적인 “현재 상태 확인”이라는 UX가 이미:

- `get_system_status`
- `get_dashboard_status`

와 겹친다는 점이다.

다만 audit/manifest/init/mode 정보는 아직 다른 단일 Tool에 완전히 포함되지 않는다.

따라서 즉시 제거하지 않고 3-6.2에서 두 선택지를 비교한다.

1. lightweight bootstrap/status Tool로 명확히 이름과 역할을 유지
2. 고유 필드만 canonical status 응답으로 통합한 뒤 deprecation

이번 단계에서는 기존 Tool/schema를 유지한다.

## INTERNALIZE_CANDIDATE — 4개

### set_research_mode

현재 MCP 서버는 paper research 전용이다.

이 Tool에서 `mode=live`를 선택해도:

```text
orders_enabled = false
```

이며 실제 live capability가 생기지 않는다.

더 중요한 점은 SystemController preflight가 `selected_mode=paper`만 허용하므로,
agent가 live를 선택하면 주문은 활성화되지 않으면서 managed research start만 막힌다.

따라서 “안전하지만 운영상 혼란을 만드는 public toggle”이다.

권장 방향:

- CLI/host operation에서는 유지
- public MCP에서는 internalize/deprecate 검토
- live deployment approval boundary와 절대 결합하지 않음

### validate_research_cache

이름과 달리 cache를 rebuild하지 않는다.

실제 기능은 manifest 파일 중 `experiment_hash`가 있는 JSON 개수를 세는 maintenance
validation이다.

운영 진단에는 유용하지만 일반 연구 agent에게 항상 노출할 핵심 capability는 아니다.

Service/CLI 유지 후 public surface에서는 숨길 후보로 분류한다.

### plan_generation

pure deterministic planner지만 production canonical loop는 이 Application Service를
호출하지 않는다.

실제 production caller는 MCP뿐이고, autoresearch는 내부 orchestration에서 자체 planning을
수행한다.

따라서 low-level planning primitive로 보존하되 public default surface에서는
internalize 후보가 적절하다.

### get_research_context

다음을 묶어 LLM prompt-friendly payload로 만든다.

- Champion
- 최근 observations
- failure knowledge
- feature catalog

하지만 이 Application Service의 production caller는 MCP 하나뿐이다.
canonical autoresearch는 runtime/evaluator에서 자신의 generation-specific context를
구성한다.

또한 public domain reads가 이미 분리되어 있다.

- features → `list_features`
- evidence → `get_research_evidence`
- performance → `get_dashboard_status`
- runtime → `get_system_status`

따라서 “사용자용 도메인 API”보다는 “LLM prompt context builder” 성격이 더 강하다.

내부 diagnostics/context-builder로 보존하고 public MCP에서 숨길 후보로 분류한다.

## DEPRECATE_CANDIDATE — 1개

### submit_research_intent

가장 강한 정리 대상이다.

현재 호출 흐름은:

```text
submit_research_intent
  → ResearchIntent validation
  → state/llm/intents.jsonl append
  → 종료
```

이다.

중요하게도 `intents.jsonl`을 읽어서 해당 외부 제출 intent를 다음 evaluation으로
실행하는 production consumer가 없다.

해당 journal은:

- autoresearch가 자신이 생성/repair한 intent를 기록하는 audit/supporting data
- RuntimeSnapshot에서는 current intent 정본으로 사용하지 않음

이다.

반면 canonical 실행은 이미:

```text
start_system
  → managed autoresearch
  → LLM proposal
  → validation/repair
  → evaluation
  → Evidence/state
```

로 연결되어 있다.

따라서 이름만 보면 “연구 intent를 제출하면 시스템이 수행할 것”처럼 보이지만 실제로는
기록만 하는 dead-end interface다.

### 권장 migration

사용 목적별로 다음으로 이동한다.

- 자동 연구를 시작하고 싶다 → `start_system`
- 특정 전략을 바로 평가하고 싶다 → `run_evaluation`
- 전략이 유효한지 확인하고 싶다 → `validate_strategy`
- 현재 research 상태를 보고 싶다 → `get_system_status`

3-6.2에서 compatibility/deprecation 방식을 설계한 뒤 제거 여부를 결정한다.

## Effect 분류

Tool은 운영 효과 기준으로도 나눴다.

### READ_ONLY

- get_workspace_status
- validate_research_cache
- validate_strategy
- plan_generation
- get_research_context
- list_features
- get_research_evidence
- get_dashboard_status
- check_system

### READ_WITH_RECONCILIATION

- get_system_status

active managed run에서는 기존 lifecycle recovery가 intentional mutation을 수행할 수 있다.

### STATE_MUTATION

- initialize_research_state
- set_research_mode
- import_strategies
- submit_research_intent

### EXECUTION_TRIGGER

- run_evaluation
- start_system

### LIFECYCLE_CONTROL

- stop_system

## Contract maturity

### STRONG

현재 typed output 또는 별도 schema/version semantics가 강하게 고정된 Tool:

- get_research_evidence
- get_dashboard_status
- start_system
- get_system_status

### MODERATE

input JSON schema와 regression test는 있으나 Application Service가 일반
`dict[str, object]`를 반환하여 output schema 자체가 독립 typed contract는 아닌 Tool.

나머지 14개가 여기에 해당한다.

3-6 이후 Tool surface를 줄이기 전에 PUBLIC_KEEP 중 장기 유지되는 Tool만 output contract를
추가로 강화하는 것이 효율적이다.

## 중요한 발견

### 1. 18개 모두 CLI parity 때문에 유지할 필요는 없다

Phase 4는 “CLI 기능을 MCP에서도 안전하게 사용할 수 있도록 하는 기능 보존”이 목적이었다.

Phase 3-6의 목적은 다르다.

이제 canonical managed workflow가 자리 잡았으므로 low-level CLI primitive까지 모두
공개 MCP에 남길 필요는 없다.

### 2. public Tool 수가 capability 품질과 같지는 않다

현재 18개 중 다음 5개는 정리 검토 가치가 높다.

```text
get_workspace_status
set_research_mode
validate_research_cache
plan_generation
get_research_context
```

그리고:

```text
submit_research_intent
```

는 가장 강한 deprecation 후보다.

### 3. 실행 Tool은 두 수준으로 정리 가능하다

```text
run_evaluation
  = 1회 deterministic evaluation

start_system
  = managed multi-generation autoresearch
```

이 구분은 유지하는 편이 명확하다.

### 4. 상태 Tool도 data/control plane으로 분리 가능하다

```text
get_dashboard_status
  = 결과·성과·account data plane

get_system_status
  = runtime/control plane
```

이 둘은 유지한다.

`get_workspace_status`만 bootstrap/configuration plane으로 별도 유지할 가치가 있는지
다음 단계에서 결정하면 된다.

## Phase 3-6 후속 세부 단계

### 3-6.2 — Public surface 목표안 설계

코드 변경 없이 다음을 확정한다.

- 최종 공개 Tool set
- compatibility period
- deprecation 방식
- get_workspace_status 통합 여부
- internalized Tool을 CLI/Application Service에 남기는 방법

### 3-6.3 — Dead-end Tool 정리

가장 먼저 `submit_research_intent`의 migration/deprecation을 구현한다.

원칙:

- 갑작스러운 silent removal 금지
- 명확한 replacement 안내
- intent journal 자체는 autoresearch audit 용도로 유지 가능
- canonical runtime에는 외부 journal consumer를 새로 만들지 않음

즉 “죽은 Tool을 살리기 위해 consumer를 추가”하는 방향이 아니라
canonical workflow로 사용자 경로를 수렴시킨다.

### 3-6.4 — Internalize 후보 정리

대상:

- set_research_mode
- validate_research_cache
- plan_generation
- get_research_context

각 Service/CLI는 필요한 범위에서 유지하되 default MCP tools/list에서 제거할지 결정한다.

### 3-6.5 — Status surface 정리

`get_workspace_status`의 고유 필드를 검토해:

- lightweight bootstrap tool로 유지하거나
- canonical status에 흡수하고 deprecate

한다.

`get_dashboard_status`와 `get_system_status`의 data/control plane 역할은 유지한다.

### 3-6.6 — 장기 Public Tool output contract 강화

최종 PUBLIC_KEEP Tool만 대상으로 typed output/version contract를 보강한다.

### 3-6.7 — Phase 3-6 final compatibility validation

- tools/list
- deprecated compatibility
- CLI parity
- security boundary
- README/operations docs
- real stdio acceptance

를 검증하고 Phase 3-6을 완료한다.

## 이번 단계에서 변경하지 않은 것

- MCP Tool 이름
- MCP Tool 수
- inputSchema
- dispatch
- Application Service 동작
- CLI
- RuntimeSnapshot
- KIS/live permission
- order capability
- evaluation/research execution

이번 단계는 inventory/classification만 고정한다.
