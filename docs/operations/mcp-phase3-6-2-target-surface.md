# MCP Phase 3-6.2 — Target public surface design

> **역사적 단계 문서:** 이 문서는 당시 전환 단계의 설계·검증 기록이다. 현재 운영 정본은 `mcp-current-state.md`이며, 이 문서의 Tool 수·transport 상태·shadow/canonical 표현을 현재 설정으로 해석하지 않는다.

## 목적

Phase 3-6.1에서 분류한 현재 18개 MCP Tool을 기준으로, 장기적으로 유지할 공개 surface와
호환성 전략을 확정한다.

이번 단계에서는 실제 `tools/list`, dispatch, Application Service, CLI 동작을 바꾸지 않는다.
즉 현재 공개 Tool은 여전히 18개다.

Machine-readable target contract:

```text
docs/operations/mcp-phase3-6-2-target-surface.json
```

## 최종 목표

장기 공개 MCP surface는 **13개**로 정한다.

### Bootstrap / configuration plane

- `initialize_research_state`
- `get_workspace_status`

### Catalog / validation plane

- `validate_strategy`
- `import_strategies`
- `list_strategies`
- `list_features`

### Evidence / status plane

- `get_research_evidence`
- `get_dashboard_status`
- `get_system_status`

### Execution / lifecycle plane

- `run_evaluation`
- `check_system`
- `start_system`
- `stop_system`

총 13개다.

## get_workspace_status 결정

Phase 3-6.1에서 이 Tool은 `DUPLICATE_OR_OVERLAP`로 분류됐다.

최종 결정은 **유지**다.

단, 일반적인 “시스템 상태” Tool로 설명하지 않고 다음 역할로 한정한다.

```text
get_workspace_status
  = bootstrap / configuration plane

get_dashboard_status
  = research result / performance data plane

get_system_status
  = managed runtime / control plane
```

### 유지 이유

`get_workspace_status`에는 현재 다음 정보가 있다.

- state 초기화 여부
- selected research mode
- audit record count
- manifest validation count
- lightweight Champion / Frontier bootstrap 요약

이 정보는 runtime process/queue 상태와 성격이 다르다.

이를 `get_system_status`에 합치면:

1. RuntimeSnapshot이 workspace bootstrap/configuration 상태까지 책임지게 되고
2. 상태 계약이 더 커지며
3. pure runtime observability와 초기화/configuration의 경계가 흐려진다.

따라서 Tool 수 1개를 줄이기 위해 서로 다른 책임을 억지로 합치지 않는다.

## 최종 공개에서 제외할 5개

### set_research_mode → INTERNALIZE

공개 MCP는 paper-research system이다.

`mode=live`를 선택해도:

```text
orders_enabled = false
```

이며 live trading capability는 생기지 않는다.

반대로 SystemController는 paper state만 시작할 수 있으므로 이 변경은 managed research를
막을 수 있다.

따라서 agent-facing public Tool로는 제거하고:

- `WorkspaceService.set_mode` 유지
- CLI `set-mode` 유지
- host/operator configuration으로 취급

한다.

현재 mode 확인은 `get_workspace_status`가 담당한다.

### validate_research_cache → INTERNALIZE

현재 기능은 cache rebuild가 아니라 manifest validation/count다.

Application Service와 CLI maintenance path는 유지하지만 default MCP public surface에서는
제외한다.

Replacement:

```text
CLI rebuild-cache
```

장기적으로 실제 cache repair/rebuild 기능이 생기더라도 별도 운영 capability로 다시
검토한다.

### plan_generation → INTERNALIZE

저수준 deterministic planning primitive다.

canonical `start_system` autoresearch는 자체 orchestration planning을 수행한다.

Application Service와 CLI는 실험/debugging 용도로 남기되 public MCP 기본 surface에서는
제외한다.

Replacement는 사용 목적에 따라:

- 자동 연구 → `start_system`
- 1회 평가 → `run_evaluation`
- 수동 계획 확인 → CLI `plan-generation`

이다.

### get_research_context → INTERNALIZE

이 Tool은 여러 domain 상태를 한 번에 합쳐 LLM prompt context로 만든다.

그러나 공개 MCP에는 이미 더 작고 명시적인 read가 있다.

- features → `list_features`
- evidence → `get_research_evidence`
- 결과/성과 → `get_dashboard_status`
- runtime → `get_system_status`

canonical autoresearch도 이 MCP Tool을 호출하지 않는다.

따라서 prompt-context helper는 내부 diagnostic/application primitive로 유지한다.

### submit_research_intent → DEPRECATE

가장 명확한 deprecation 대상이다.

현재 실제 동작:

```text
validate ResearchIntent
→ append intents.jsonl
→ return
```

외부에서 제출된 journal entry를 production runtime이 consume하지 않는다.

따라서 “submit”이라는 이름이 실제 실행을 암시하지만 실행되지 않는 문제가 있다.

Replacement:

- 자동 연구 → `start_system`
- 특정 전략 평가 → `run_evaluation`
- 전략 정적 검증 → `validate_strategy`
- 진행 상태 → `get_system_status`

이다.

새로운 intent consumer를 만드는 방식으로 dead-end interface를 살리지 않는다.

## 왜 새로운 alias를 만들지 않는가

새 alias를 만들지 않는다.

예를 들어:

```text
run_research -> start_system
evaluate_strategy -> run_evaluation
```

같은 alias를 추가하면 오히려 public surface가 다시 늘어나고 오래된 이름과 새 이름을
동시에 유지해야 한다.

현재 canonical replacement 이름은 이미 충분히 명확하다.

따라서:

```text
add_new_aliases = false
```

로 고정한다.

## Tool schema에 custom deprecation 필드를 넣지 않는 이유

현재 local MCP server는 Tool object에:

- name
- description
- inputSchema

를 사용하고 있다.

Phase 3-6 compatibility를 위해 별도의 비표준 top-level
`deprecated=true` 같은 custom field를 추가하지 않는다.

이유:

1. client별 unknown metadata 처리 차이를 만들 필요가 없음
2. 현재 contract test를 불필요하게 확장하지 않음
3. description과 call result의 additive compatibility metadata로 충분함

따라서:

```text
add_custom_tool_schema_metadata = false
```

로 정한다.

## Compatibility strategy

Tool을 한 번에 삭제하지 않는다.

### Stage A — Phase 3-6.3: soft deprecation

현재 18개를 모두 `tools/list`에 유지한다.

`submit_research_intent`만:

- description에 명시적 deprecated 문구 추가
- replacement 안내
- 기존 동작은 유지
- call result에 additive compatibility metadata 추가

한다.

기존 caller는 깨지지 않는다.

### Stage B — Phase 3-6.4: target public list 전환

`tools/list`를 13개 target surface로 변경한다.

목록에서 빠지는 Tool:

- set_research_mode
- validate_research_cache
- plan_generation
- get_research_context
- submit_research_intent

그러나 Phase 3-6 동안은 기존 이름을 아는 caller를 위해 legacy dispatch shim을 유지한다.

중요:

**tools/list에서 숨긴다고 security boundary가 되는 것은 아니다.**

legacy dispatch가 남아 있는 동안 해당 이름을 아는 client는 직접 호출할 수 있다.

이번 대상 Tool은 order/credential/live-account capability가 아니므로 compatibility를 위해
이 방식이 가능하다.

보안 capability였다면 hidden dispatch를 compatibility 수단으로 사용하지 않는다.

### Stage C — Phase 3-6.5~3-6.6

13개 공개 surface를 기준으로:

- workspace/bootstrap semantics
- output contract
- documentation
- acceptance tests

를 정리한다.

### Stage D — Phase 3-6.7

최종 검증 기준:

```text
tools/list = 13개
legacy dispatch = compatibility window 내 지원
CLI/Application Service = 필요 기능 유지
orders_enabled = false
```

를 검증한다.

## Legacy dispatch hard removal

Phase 3-6에서는 hidden legacy dispatch를 hard-remove하지 않는다.

Hard removal은:

```text
OUT_OF_PHASE_3_6_REQUIRES_EXPLICIT_LATER_APPROVAL
```

로 정한다.

즉 최소한 Phase 3-6.7까지:

- 이전 caller migration 가능
- replacement 문서 확인 가능
- stdio acceptance에서 target public surface 확인 가능

한 상태를 만든다.

이후 실제 dispatch 삭제는 별도 승인된 cleanup phase에서 수행한다.

## Compatibility result metadata

legacy Tool 호출 결과에 추가할 metadata는 기존 payload를 깨지 않는 additive field로 설계한다.

권장 형태:

```json
{
  "...existing fields...": "...",
  "_compatibility": {
    "status": "DEPRECATED",
    "replacement_tools": ["start_system", "run_evaluation"]
  }
}
```

원칙:

- raw internal detail 없음
- deadline 날짜를 임의로 만들지 않음
- replacement 이름만 제공
- 기존 필드 삭제/변경 없음

Internalize Tool은 필요하면:

```text
status = LEGACY_INTERNAL_TOOL
```

같은 compatibility marker를 사용할 수 있다.

구체 구현은 3-6.3/3-6.4에서 한다.

## Target 13개를 유지하는 이유

13개는 역할 기준으로 충분히 작으면서 핵심 capability를 잃지 않는다.

### 새로운 workspace

```text
initialize_research_state
get_workspace_status
```

### 사용 가능한 전략/feature 탐색

```text
validate_strategy
import_strategies
list_strategies
list_features
```

### 연구 결과 확인

```text
get_research_evidence
get_dashboard_status
get_system_status
```

### 실행

```text
run_evaluation
check_system
start_system
stop_system
```

agent가 실제 작업을 하기 위해 필요한 흐름이 이 네 plane 안에서 완결된다.

## Phase 3-6 후속 단계 확정

### 3-6.3 — submit_research_intent soft deprecation

- 18개 Tool 유지
- deprecated description
- replacement 안내
- additive compatibility result
- 기존 journal append 동작 유지

### 3-6.4 — 13개 target public surface 전환

`tools/list`에서 다음 5개 제거:

- set_research_mode
- validate_research_cache
- plan_generation
- get_research_context
- submit_research_intent

legacy direct dispatch는 Phase 3-6.7까지 유지한다.

### 3-6.5 — workspace/configuration plane 정리

`get_workspace_status`를 bootstrap/configuration Tool로 명확히 고정한다.

필요하면 output contract를 정리하되 `get_system_status`와 합치지 않는다.

### 3-6.6 — 장기 공개 13개 output contract 강화

PUBLIC target만 대상으로 typed/versioned output contract를 강화한다.

### 3-6.7 — 최종 compatibility / security / stdio 검증

- tools/list exact 13
- legacy calls migration metadata
- CLI 기능 유지
- security boundary 유지
- README/operations docs 일치
- real stdio acceptance
- release gate

를 검증한다.

## 이번 단계에서 변경하지 않은 것

- 현재 tools/list 18개
- Tool 이름
- inputSchema
- dispatch
- Service 동작
- CLI
- RuntimeSnapshot
- evaluation/research workflow
- KIS/live permission
- order capability

Phase 3-6.2는 target architecture와 migration policy만 고정한다.
