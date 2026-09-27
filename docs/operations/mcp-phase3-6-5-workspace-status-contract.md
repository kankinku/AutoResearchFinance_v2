# MCP Phase 3-6.5 — Workspace bootstrap/configuration status contract

## 목적

`get_workspace_status`를 일반적인 runtime status가 아니라
**bootstrap/configuration plane**의 장기 공개 Tool로 명확히 고정한다.

다음 Tool과 책임을 분리한다.

- `get_workspace_status` → 초기화/설정 상태
- `get_system_status` → managed runtime/control plane
- `get_dashboard_status` → 연구 결과/성과 data plane

Tool 이름과 empty input schema는 변경하지 않는다.

## Typed output

Application layer에 `WorkspaceStatusSnapshot`을 추가한다.

```text
schema_version = 1
plane = BOOTSTRAP_CONFIGURATION
```

Pydantic `extra=forbid`로 accidental output drift를 막는다.

## Status 의미

### NOT_INITIALIZED

5개 bootstrap state file이 하나도 존재하지 않는 상태.

대상:

- champion
- frontier
- knowledge
- rescue_pool
- mode

### PARTIAL

다음 중 하나라도 해당하면 PARTIAL이다.

- 일부 bootstrap file만 존재
- 존재하는 file 중 JSON/object 형식이 손상됨
- 전체 5개가 유효하게 준비되지 않음

### READY

5개 bootstrap component가 모두 유효한 JSON object로 존재한다.

이는 managed research process가 RUNNING이라는 뜻이 아니다.
실행 상태는 `get_system_status`에서 확인한다.

## Output fields

기존 의미를 유지하는 필드:

- `status`
- `champion`
- `frontier_families`
- `selected_mode`
- `orders_enabled`
- `audit_records`
- `validated_manifests`

추가된 계약 필드:

- `schema_version`
- `plane`
- `initialized_components`
- `missing_components`
- `invalid_components`
- `mode_configured`

## Mode 의미

state가 초기화되지 않은 경우에도 안전한 기본 표현으로:

```text
selected_mode = paper
mode_configured = false
```

를 반환한다.

유효한 `mode.json`에서 selected_mode가 paper/live 중 하나이면:

```text
mode_configured = true
```

가 된다.

`orders_enabled`는 workspace file 내용과 관계없이 public contract에서 항상 false다.

즉 legacy fixture나 외부 수정으로 mode.json 안에 `orders_enabled=true`가 있어도
MCP status가 주문 권한을 true로 표시하지 않는다.

## Corrupt state 처리

기존 status는 JSON parse 실패를 사실상 missing과 동일하게 처리했고,
일부 파일만 있어도 READY가 될 수 있었다.

현재는 file 존재 여부와 JSON validity를 분리한다.

예:

```text
champion.json = valid
mode.json = broken JSON
others = missing
```

이면:

```text
status = PARTIAL
initialized_components = [champion]
invalid_components = [mode]
missing_components = [frontier, knowledge, rescue_pool]
```

로 표시한다.

자동 수정은 수행하지 않는다.

## Pure-read

초기화되지 않은 workspace에서 `get_workspace_status`를 호출해도:

- state directory 생성 없음
- bootstrap file 생성 없음
- mode file 생성 없음
- audit append 없음

이다.

초기화 작업은 계속 `initialize_research_state`만 담당한다.

## MCP description

공개 Tool 설명도 역할을 명시한다.

- bootstrap/configuration 상태를 읽는 Tool임
- runtime health는 `get_system_status`
- performance data는 `get_dashboard_status`

이를 통해 AI client가 세 status Tool을 목적에 맞게 선택할 수 있게 한다.

## 안전 경계

변경하지 않은 것:

- get_workspace_status Tool name
- empty input schema
- initialize semantics
- set-mode legacy dispatch semantics
- orders_enabled=false
- live approval/order capability
- RuntimeSnapshot
- dashboard snapshot
- SystemController lifecycle

## 다음 단계

다음은 Phase 3-6.6이다.

장기 공개 13개 Tool을 대상으로 output contract/versioning을 강화한다.
이번 사용자 승인 범위는 3-6.5까지이므로 여기서 중단한다.
